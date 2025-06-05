from transformers import AutoModelForCausalLM, AutoProcessor, GenerationConfig, set_seed
import torch
from host.imagecache import ImageFile
from .backend import CaptionBackend
from .devmap import DevMap
from .quant import Quantization


class MolmoBackend(CaptionBackend):
    def __init__(self, config):
        modelPath: str = config["model_path"]
        self.generationConfig = GenerationConfig.from_pretrained(modelPath)

        devmap = self.makeDeviceMap(modelPath, config["gpu_layers"], config["vis_gpu_layers"])
        quant = Quantization.getQuantConfig(config["quantization"], devmap.hasCpuLayers)

        self.model = AutoModelForCausalLM.from_pretrained(
            modelPath,
            torch_dtype=torch.bfloat16,
            #attn_implementation=devmap.attention, # ValueError: MolmoForCausalLM does not support Flash Attention 2.0 yet.
            device_map=devmap.deviceMap,
            quantization_config=quant,
            trust_remote_code=True
        )

        self.processor = AutoProcessor.from_pretrained(
            modelPath,
            torch_dtype=torch.bfloat16,
            device_map='auto',
            trust_remote_code=True
        )

        # https://huggingface.co/docs/transformers/main/perf_torch_compile
        # https://pytorch.org/get-started/pytorch-2.0/#user-experience
        #self.model = torch.compile(self.model, mode="max-autotune") # modes: max-autotune, reduce-overhead
        super().__init__(config)


    def setConfig(self, config: dict):
        super().setConfig(config)
        self.stop = ["<|endoftext|>"]

        self.generationConfig.max_new_tokens    = self.config.get("max_tokens")
        self.generationConfig.stop_strings      = (self.stop if self.stop else None)
        self.generationConfig.use_cache         = True

        # Enabling sampling causes RuntimeError: CUDA error: device-side assert triggered
        self.generationConfig.do_sample         = False

        # https://huggingface.co/docs/transformers/main_classes/text_generation
        # self.generationConfig = GenerationConfig(
        #     max_new_tokens=self.config.get("max_tokens"),
        #     stop_strings=self.stop,


        #     do_sample=False,
        #     # temperature=self.config.get("temperature"),
        #     # top_k=self.config.get("top_k"),
        #     # top_p=self.config.get("top_p"),
        #     # min_p=self.config.get("min_p"),
        #     # typical_p=self.config.get("typical_p"),
        #     # repetition_penalty=self.config.get("repeat_penalty"),

        #     use_cache=True
        # )


    def caption(self, imgFile: ImageFile, prompts: list[dict[str, str]], systemPrompt: str = None) -> dict[str, str]:
        image = imgFile.openPIL()
        answers = dict()

        set_seed(self.randomSeed())

        for conversation in prompts:
            messages = self.formatMessage("system", systemPrompt) if systemPrompt else ""

            for name, prompt in conversation.items():
                messages += self.formatMessage("user", prompt)

                with torch.inference_mode():
                    generatedText = self._caption(messages, image)
                    generatedText = generatedText.strip()

                messages += self.formatMessage("assistant", generatedText)
                answers[name] = generatedText

        return answers


    # TODO: Only encode image once during first iteration?
    def _caption(self, messages: str, image) -> str:
        messages += "<|im_start|>assistant\n"
        tokens = self.processor.get_tokens_input(messages, None, False)
        inputs = self.processor.process(images=[image], tokens=tokens)
        inputs["images"] = inputs["images"].to(torch.bfloat16)

        # move inputs to the correct device and make a batch of size 1
        inputs = {k: v.to(self.model.device).unsqueeze(0) for k, v in inputs.items()}

        #with torch.inference_mode(), torch.autocast("cuda", enabled=True, dtype=torch.bfloat16):
        output = self.model.generate_from_batch(
            inputs,
            self.generationConfig,
            tokenizer=self.processor.tokenizer
        )

        # only get generated tokens; decode them to text
        generatedTokens = output[0, inputs['input_ids'].size(1):]
        return self.processor.tokenizer.decode(generatedTokens, skip_special_tokens=True)


    @staticmethod
    def formatMessage(role: str, message) -> str:
        return f"<|im_start|>{role}\n{message}<|im_end|>\n"


    @staticmethod
    def makeDeviceMap(modelPath, llmGpuLayers: int, visGpuLayers: int) -> DevMap:
        devmap = DevMap.fromConfig(
            modelPath,
            "num_hidden_layers"
        )
        devmap.maxLayerVis = 22

        devmap.setCudaLayer("model.transformer")
        devmap.setCudaLayer("model.transformer.ff_out")
        devmap.setCudaLayer("model.transformer.ln_f")
        devmap.setCudaLayer("model.transformer.wte")
        devmap.setLLMLayers("model.transformer.blocks", llmGpuLayers)

        # devmap.setCudaLayer("model.vision_backbone")
        # devmap.setCudaLayer("model.vision_backbone.image_pooling_2d")
        # devmap.setCudaLayer("model.vision_backbone.image_projector")
        # devmap.setCudaLayer("model.vision_backbone.pad_embed")

        # devmap.setCudaLayer("model.vision_backbone.image_vit")
        # devmap.setCudaLayer("model.vision_backbone.image_vit.class_embedding")
        # devmap.setCudaLayer("model.vision_backbone.image_vit.patch_embedding")
        # devmap.setCudaLayer("model.vision_backbone.image_vit.positional_embedding")
        # devmap.setCudaLayer("model.vision_backbone.image_vit.pre_ln")
        # devmap.setCudaLayer("model.vision_backbone.image_vit.positional_embedding")

        if visGpuLayers == 0:
            devmap.setCpuLayer("model.vision_backbone")
            devmap.setCpuLayer("model.vision_backbone.image_vit.transformer.resblocks")
        else:
            devmap.setCudaLayer("model.vision_backbone")
            devmap.setVisLayers("model.vision_backbone.image_vit.transformer.resblocks", visGpuLayers)

        return devmap
