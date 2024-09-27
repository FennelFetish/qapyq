from transformers import AutoModelForCausalLM, set_seed
from PIL import Image
import torch
from .backend import InferenceBackend


class Ovis16Backend(InferenceBackend):
    def __init__(self, config: dict):
        modelPath = config.get("model_path")

        self.model = AutoModelForCausalLM.from_pretrained(
            modelPath,
            torch_dtype=torch.bfloat16,
            multimodal_max_length=8192,
            #attn_implementation='flash_attention_2',
            device_map=self.makeDeviceMap(41, 6),
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


    def caption(self, imgPath: str, prompts: dict[str, str], systemPrompt: str = None, rounds=1) -> dict:
        prompts = self.preparePrompts(prompts, systemPrompt)
        image = Image.open(imgPath)
        answers = dict()

        set_seed(self.randomSeed())

        for r in range(rounds):
            messages = []

            for i, (name, prompt) in enumerate(prompts.items()):
                messages.append( {"from": "human", "value": prompt.strip()} )

                answer = self._caption(messages, image)
                answer = answer.strip()
                messages.append( {"from": "gpt", "value": answer} )

                if r > 0:
                    name = f"{name}_round{r}"
                answers[name] = answer

        return answers


    # TODO: Only encode image once during first iteration?
    def _caption(self, conversation, image) -> str:
        prompt, input_ids, pixel_values = self.model.preprocess_inputs(conversation, [image])
        attention_mask = torch.ne(input_ids, self.text_tokenizer.pad_token_id)
        input_ids = input_ids.unsqueeze(0).to(device=self.model.device)
        attention_mask = attention_mask.unsqueeze(0).to(device=self.model.device)
        pixel_values = [pixel_values.to(dtype=self.visual_tokenizer.dtype, device=self.visual_tokenizer.device)]

        with torch.inference_mode():
            output_ids = self.model.generate(input_ids, pixel_values=pixel_values, attention_mask=attention_mask, **self.genArgs)[0]
            return self.text_tokenizer.decode(output_ids, skip_special_tokens=True)


    def preparePrompts(self, prompts: dict, systemPrompt: str) -> dict:
        if systemPrompt:
            prompts = self.mergeSystemPrompt(prompts, systemPrompt)
        
        name, prompt  = next(iter(prompts.items())) # First entry
        prompts[name] = f'<image>\n{prompt}'
        return prompts


    @staticmethod
    def makeDeviceMap(llmGpuLayers: int, visGpuLayers: int) -> dict:
        llmGpuLayers = min(llmGpuLayers, 41)
        visGpuLayers = min(visGpuLayers, 26)

        deviceMap = dict()
        cpu = "cpu"
        cuda = 0

        deviceMap["llm.model.embed_tokens"] = cuda
        deviceMap["llm.model.norm"] = cuda
        deviceMap["llm.lm_head.weight"] = cuda
        deviceMap["vte.weight"] = cuda

        deviceMap["llm.model.layers.0"] = cuda
        for l in range(1, llmGpuLayers):
            deviceMap[f"llm.model.layers.{l}"] = cuda
        for l in range(llmGpuLayers, 41):
            deviceMap[f"llm.model.layers.{l}"] = cpu
        deviceMap["llm.model.layers.41"] = cuda

        deviceMap["visual_tokenizer"] = cuda
        deviceMap["visual_tokenizer.backbone.vision_model.encoder.layers.0"] = cuda
        for l in range(1, visGpuLayers):
            deviceMap[f"visual_tokenizer.backbone.vision_model.encoder.layers.{l}"] = cuda
        for l in range(visGpuLayers, 26):
            deviceMap[f"visual_tokenizer.backbone.vision_model.encoder.layers.{l}"] = cpu
        deviceMap["visual_tokenizer.backbone.vision_model.encoder.layers.26"] = cuda

        # print("mkDeviceMap:")
        # for k, v in device_map.items():
        #     print(f"{k} -> {v}")

        return deviceMap
