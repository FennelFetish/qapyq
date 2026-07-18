from transformers import LlavaForConditionalGeneration, AutoProcessor, GenerationConfig, set_seed
import torch
from host.imagecache import ImageFile
from infer.backend import CaptionBackend
from infer.prompt_struct import Conversation
from infer.devmap import DevMap
from infer.quant import Quantization


class JoyCaptionBackend(CaptionBackend):
    def __init__(self, config: dict):
        modelPath = config.get("model_path")
        self.generationConfig = GenerationConfig.from_pretrained(modelPath)

        super().__init__(config)

        self.device, self.dtype = DevMap.getTorchDeviceDtype()
        devmap = self.makeDeviceMap(modelPath, self.device, config.get("gpu_layers"), config.get("vis_gpu_layers"))

        skipModules = ["vision_tower", "multi_modal_projector"]
        quant = Quantization.getQuantConfig(config.get("quantization"), devmap.hasCpuLayers, skipModules)

        self.model = LlavaForConditionalGeneration.from_pretrained(
            modelPath,
            torch_dtype=self.dtype,
            device_map=devmap.deviceMap,
            attn_implementation=devmap.attention,
            quantization_config=quant,
        ).eval()

        self.processor = AutoProcessor.from_pretrained(modelPath)


    def setConfig(self, config: dict):
        super().setConfig(config)

        self.generationConfig.max_new_tokens     = self.config.get("max_tokens")
        self.generationConfig.stop_strings       = (self.stop if self.stop else None)
        self.generationConfig.do_sample          = True

        self.generationConfig.temperature        = self.config.get("temperature")
        self.generationConfig.top_k              = self.config.get("top_k")
        self.generationConfig.top_p              = self.config.get("top_p")
        self.generationConfig.min_p              = self.config.get("min_p")
        self.generationConfig.typical_p          = self.config.get("typical_p")
        self.generationConfig.repetition_penalty = self.config.get("repeat_penalty")

        if self.generationConfig.pad_token_id is None:
            self.generationConfig.pad_token_id = 128001


    def caption(self, imgFile: ImageFile, prompts: list[Conversation], systemPrompt: str = None) -> dict[str, str]:
        image = imgFile.openPIL(forceRGB=True)
        answers = dict()

        set_seed(self.randomSeed())

        for conversation in prompts:
            messages = []
            if systemPrompt:
                messages.append( {"role": "system", "content": systemPrompt.strip()} )

            for prompt in conversation:
                messages.append( {"role": "user", "content": prompt.prompt.strip()} )
                inputText = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

                inputs = self.processor(text=[inputText], images=[image], return_tensors="pt")
                inputs = inputs.to(self.device)
                inputs['pixel_values'] = inputs['pixel_values'].to(self.dtype)

                with torch.inference_mode():
                    generatedIDs = self.model.generate(**inputs, generation_config=self.generationConfig)[0]
                    generatedIDs = generatedIDs[inputs['input_ids'].shape[1]:]
                    outputText = self.processor.tokenizer.decode(generatedIDs, skip_special_tokens=True, clean_up_tokenization_spaces=False)

                answer = outputText.strip()
                messages.append( {"role": "assistant", "content": answer} )
                answers[prompt.name] = answer

        return answers


# /mnt/firlefanz/dev-Tools/qapyq/.venv/lib/python3.10/site-packages/accelerate/utils/modeling.py:1614:
# UserWarning: The following device_map keys do not match any submodules in the model:
# ['language_model', 'language_model.lm_head', 'language_model.model.embed_tokens', 'language_model.model.norm.weight', 'language_model.model.layers',
# 'vision_tower', 'vision_tower.vision_model.embeddings', 'vision_tower.vision_model.post_layernorm', 'vision_tower.vision_model.head',
# 'vision_tower.vision_model.encoder.layers', 'multi_modal_projector']

    @staticmethod
    def makeDeviceMap(modelPath, device, llmGpuLayers: int, visGpuLayers: int) -> DevMap:
        devmap = DevMap.fromConfig(
            modelPath,
            "-",
            "vision_config.num_hidden_layers"
        )

        devmap.maxLayerLLM = 31
        devmap.setDevice(device)

        devmap.setCudaLayer("")
        devmap.setCudaLayer("language_model")
        devmap.setCudaLayer("language_model.lm_head")
        devmap.setCudaLayer("language_model.model.embed_tokens")
        devmap.setCudaLayer("language_model.model.norm.weight")
        devmap.setLLMLayers("language_model.model.layers", llmGpuLayers)

        # Device mismatch with 0 GPU layers
        visGpuLayers = max(visGpuLayers, 1)

        devmap.setCudaLayer("vision_tower")
        devmap.setCudaLayer("vision_tower.vision_model.embeddings")
        devmap.setCudaLayer("vision_tower.vision_model.post_layernorm")
        devmap.setCudaLayer("vision_tower.vision_model.head")
        devmap.setVisLayers("vision_tower.vision_model.encoder.layers", visGpuLayers)

        devmap.setCudaLayer("multi_modal_projector")
        return devmap
