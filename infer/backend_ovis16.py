from transformers import AutoModelForCausalLM, set_seed
from PIL import Image
import torch
from typing import List, Dict
from .backend import InferenceBackend
from .devmap import DevMap
from .quant import Quantization


class Ovis16Backend(InferenceBackend):
    def __init__(self, config: dict):
        modelPath = config.get("model_path")

        devmap = self.makeDeviceMap(modelPath, config.get("gpu_layers"), config.get("vis_gpu_layers"))
        quant = Quantization.getQuantConfig(config.get("quantization"), devmap.hasCpuLayers)

        # Quantization doesnt work: self and mat2 must have the same dtype, but got BFloat16 and Byte
        #   File "/home/rem/.cache/huggingface/modules/transformers_modules/modeling_ovis.py", line 196, in encode
        #     output = self.backbone(pixel_values, output_hidden_states=True, return_dict=True)
        # Maybe try putting the whole encoder to CPU (NF4 quant uses float32 @ cpu)?
        # Or set dtype in backbone config?
        # --> Or try BitsAndBytesConfig.llm_int8_skip_modules (takes a list of layers that are excluded from quantization)

        self.model = AutoModelForCausalLM.from_pretrained(
            modelPath,
            torch_dtype=torch.bfloat16,
            multimodal_max_length=8192,
            #attn_implementation='flash_attention_2',
            device_map=devmap.deviceMap,
            quantization_config=quant,
            trust_remote_code=True
        )

        self.text_tokenizer = self.model.get_text_tokenizer()
        self.visual_tokenizer = self.model.get_visual_tokenizer()

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


    def caption(self, imgPath: str, prompts: List[Dict[str, str]], systemPrompt: str = None) -> Dict[str, str]:
        prompts = self.preparePrompts(prompts, systemPrompt)
        image = Image.open(imgPath)
        answers = dict()

        set_seed(self.randomSeed())

        for conversation in prompts:
            messages = []

            for name, prompt in conversation.items():
                messages.append( {"from": "human", "value": prompt.strip()} )

                answer = self._caption(messages, image)
                answer = answer.strip()
                messages.append( {"from": "gpt", "value": answer} )
                answers[name] = answer

        return answers


    # TODO: Only encode image once during first iteration?
    def _caption(self, messages, image) -> str:
        prompt, input_ids, pixel_values = self.model.preprocess_inputs(messages, [image])
        attention_mask = torch.ne(input_ids, self.text_tokenizer.pad_token_id)
        input_ids = input_ids.unsqueeze(0).to(device=self.model.device)
        attention_mask = attention_mask.unsqueeze(0).to(device=self.model.device)
        pixel_values = [pixel_values.to(dtype=self.visual_tokenizer.dtype, device=self.visual_tokenizer.device)]

        with torch.inference_mode():
            output_ids = self.model.generate(input_ids, pixel_values=pixel_values, attention_mask=attention_mask, **self.genArgs)[0]
            return self.text_tokenizer.decode(output_ids, skip_special_tokens=True)


    def preparePrompts(self, prompts: List[Dict[str, str]], systemPrompt: str) -> List[Dict[str, str]]:
        if systemPrompt:
            prompts = self.mergeSystemPrompt(prompts, systemPrompt)
        
        for conv in prompts:
            name, prompt  = next(iter(conv.items())) # First entry
            conv[name] = f'<image>\n{prompt}'
        return prompts


    @staticmethod
    def makeDeviceMap(modelPath, llmGpuLayers: int, visGpuLayers: int) -> DevMap:
        devmap = DevMap.fromConfig(
            modelPath, 
            "llm_config.num_hidden_layers",
            "visual_tokenizer_config.backbone_config.num_hidden_layers"
        )

        devmap.setCudaLayer("llm")
        devmap.setCudaLayer("llm.lm_head")
        devmap.setCudaLayer("llm.model.embed_tokens")
        devmap.setCudaLayer("llm.model.norm")
        devmap.setLLMLayers("llm.model.layers", llmGpuLayers)
        
        devmap.setCudaLayer("visual_tokenizer")
        devmap.setCudaLayer("visual_tokenizer.head")
        devmap.setCudaLayer("visual_tokenizer.backbone.vision_model.embeddings")
        devmap.setCudaLayer("visual_tokenizer.backbone.vision_model.head")

        if visGpuLayers == 0:
            devmap.setCpuLayer("visual_tokenizer.backbone.vision_model.post_layernorm")
            devmap.setCpuLayer("visual_tokenizer.backbone.vision_model.encoder.layers")
        else:
            devmap.setCudaLayer("visual_tokenizer.backbone.vision_model.post_layernorm")
            devmap.setVisLayers("visual_tokenizer.backbone.vision_model.encoder.layers", visGpuLayers)

        devmap.setCudaLayer("vte")
        return devmap
