from transformers import AutoModelForCausalLM, set_seed
import torch
from host.imagecache import ImageFile
from .backend import CaptionBackend
from .devmap import DevMap
from .quant import Quantization


class Ovis2Backend(CaptionBackend):
    def __init__(self, config: dict):
        modelPath = config.get("model_path")

        self.device, self.dtype = DevMap.getTorchDeviceDtype()
        devmap = self.makeDeviceMap(modelPath, self.device, config.get("gpu_layers"), config.get("vis_gpu_layers"))
        quant = Quantization.getQuantConfig(config.get("quantization"), devmap.hasCpuLayers)

        self.model = AutoModelForCausalLM.from_pretrained(
            modelPath,
            torch_dtype=self.dtype,
            multimodal_max_length=32768,
            #attn_implementation=devmap.attention,
            device_map=devmap.deviceMap,
            quantization_config=quant,
            trust_remote_code=True
        ).eval()

        self.text_tokenizer = self.model.get_text_tokenizer()
        self.visual_tokenizer = self.model.get_visual_tokenizer().eval()

        self.maxPartition = 9
        super().__init__(config)


    def setConfig(self, config: dict):
        super().setConfig(config)

        self.genArgs = {
            "max_new_tokens": self.config.get("max_tokens"),
            "stop_strings": (self.stop if self.stop else None),
            "do_sample": True,

            "temperature": self.config.get("temperature"),
            "top_k": self.config.get("top_k"),
            "top_p": self.config.get("top_p"),
            "min_p": self.config.get("min_p"),
            "typical_p": self.config.get("typical_p"),
            "repetition_penalty": self.config.get("repeat_penalty"),

            "eos_token_id": self.model.generation_config.eos_token_id,
            "pad_token_id": self.text_tokenizer.pad_token_id,
            "use_cache": True
        }


    def caption(self, imgFile: ImageFile, prompts: list[dict[str, str]], systemPrompt: str = None) -> dict[str, str]:
        image = imgFile.openPIL()
        answers = dict()

        set_seed(self.randomSeed())

        for conversation in prompts:
            messages = []
            if systemPrompt:
                messages.append( {"from": "system", "value": systemPrompt} )

            for i, (name, prompt) in enumerate(conversation.items()):
                if i == 0:
                    messages.append( {"from": "human", "value": "<image>\n"+prompt.strip()} )
                else:
                    messages.append( {"from": "human", "value": prompt.strip()} )

                answer = self._caption(messages, image)
                answer = answer.strip()
                messages.append( {"from": "gpt", "value": answer} )
                answers[name] = answer

        return answers


    def _caption(self, messages, image) -> str:
        prompt, input_ids, pixel_values = self.model.preprocess_inputs(messages, [image], max_partition=self.maxPartition)
        attention_mask = torch.ne(input_ids, self.text_tokenizer.pad_token_id)
        input_ids = input_ids.unsqueeze(0).to(self.device)
        attention_mask = attention_mask.unsqueeze(0).to(self.device)

        if pixel_values is not None:
            pixel_values = pixel_values.to(dtype=self.visual_tokenizer.dtype, device=self.visual_tokenizer.device)
        pixel_values = [pixel_values]

        # generate output
        with torch.inference_mode():
            output_ids = self.model.generate(input_ids, pixel_values=pixel_values, attention_mask=attention_mask, **self.genArgs)[0]
            output = self.text_tokenizer.decode(output_ids, skip_special_tokens=True)
            return output


    @staticmethod
    def makeDeviceMap(modelPath, device, llmGpuLayers: int, visGpuLayers: int) -> DevMap:
        devmap = DevMap.fromConfig(
            modelPath,
            "llm_config.num_hidden_layers",
            "visual_tokenizer_config.backbone_config.num_hidden_layers"
        )

        devmap.setDevice(device)

        devmap.setCudaLayer("")
        devmap.setCudaLayer("llm")
        devmap.setCudaLayer("llm.lm_head")
        devmap.setCudaLayer("llm.model.embed_tokens")
        devmap.setCudaLayer("llm.model.norm")
        devmap.setLLMLayers("llm.model.layers", llmGpuLayers)

        visGpuLayers = max(visGpuLayers, 1)
        devmap.setCudaLayer("visual_tokenizer")
        devmap.setCudaLayer("visual_tokenizer.backbone.preprocessor")
        devmap.setCudaLayer("visual_tokenizer.head")
        devmap.setCudaLayer("visual_tokenizer.backbone.trunk.post_trunk_norm")
        devmap.setVisLayers("visual_tokenizer.backbone.trunk.blocks", visGpuLayers)

        devmap.setCudaLayer("vte")
        return devmap
