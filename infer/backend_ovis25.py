from transformers import AutoModelForCausalLM, set_seed
import torch
from host.imagecache import ImageFile
from .backend import CaptionBackend
from .devmap import DevMap
from .quant import Quantization


class Ovis25Backend(CaptionBackend):
    def __init__(self, config: dict):
        modelPath = config.get("model_path")

        self.device, self.dtype = DevMap.getTorchDeviceDtype(half=True)
        devmap = self.makeDeviceMap(modelPath, self.device, config.get("gpu_layers"), config.get("vis_gpu_layers"))
        quant = Quantization.getQuantConfig(config.get("quantization"), devmap.hasCpuLayers)

        self.model = AutoModelForCausalLM.from_pretrained(
            modelPath,
            torch_dtype=self.dtype,
            attn_implementation=devmap.attention,
            device_map=devmap.deviceMap,
            quantization_config=quant,
            trust_remote_code=True
        ).eval()

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

            "enable_thinking": False,
            "enable_thinking_budget": True,
            "thinking_budget": 2048,

            "pad_token_id": 151643
        }


    def caption(self, imgFile: ImageFile, prompts: list[dict[str, str]], systemPrompt: str = None) -> dict[str, str]:
        image = imgFile.openPIL()
        answers = dict()

        set_seed(self.randomSeed())

        for conversation in prompts:
            messages = []
            if systemPrompt:
                messages.append( {"role": "system", "content": systemPrompt} )

            for i, (name, prompt) in enumerate(conversation.items()):
                if i == 0:
                    messages.append({
                        "role": "user",
                        "content": [
                            {"type": "image", "image": image},
                            {"type": "text", "text": prompt.strip()}
                        ]
                    })
                else:
                    messages.append( {"role": "user", "content": prompt.strip()} )

                answer = self._caption(messages)
                answer = answer.strip()
                messages.append( {"role": "assistant", "content": answer} )
                answers[name] = answer

        return answers


    def _caption(self, messages) -> str:
        input_ids, pixel_values, grid_thws = self.model.preprocess_inputs(
            messages=messages,
            add_generation_prompt=True,
            enable_thinking=self.genArgs["enable_thinking"]
        )

        input_ids = input_ids.to(self.device)
        if pixel_values is not None:
            pixel_values = pixel_values.to(self.device)
        if grid_thws is not None:
            grid_thws = grid_thws.to(self.device)

        # generate output
        with torch.inference_mode():
            outputs = self.model.generate(inputs=input_ids, pixel_values=pixel_values, grid_thws=grid_thws, **self.genArgs)
            return self.model.text_tokenizer.decode(outputs[0], skip_special_tokens=True)


    @staticmethod
    def makeDeviceMap(modelPath, device, llmGpuLayers: int, visGpuLayers: int) -> DevMap:
        devmap = DevMap.fromConfig(
            modelPath,
            "llm_config.num_hidden_layers",
            "vit_config.num_hidden_layers"
        )

        devmap.setDevice(device)

        devmap.setCudaLayer("")
        devmap.setCudaLayer("llm")
        devmap.setCudaLayer("llm.lm_head")
        devmap.setCudaLayer("llm.model.embed_tokens")
        devmap.setCudaLayer("llm.model.norm")
        devmap.setLLMLayers("llm.model.layers", llmGpuLayers)

        devmap.setCudaLayer("visual_tokenizer")
        devmap.setCudaLayer("visual_tokenizer.head")
        devmap.setCudaLayer("visual_tokenizer.vit.vision_model.embeddings")
        devmap.setCudaLayer("visual_tokenizer.vit.vision_model.post_layernorm")
        devmap.setVisLayers("visual_tokenizer.vit.vision_model.encoder.layers", visGpuLayers)

        devmap.setCudaLayer("vte")
        return devmap
