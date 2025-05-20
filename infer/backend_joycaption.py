from transformers import LlavaForConditionalGeneration, AutoProcessor, GenerationConfig, set_seed
import torch
from PIL import Image
from .backend import InferenceBackend
from .devmap import DevMap
from .quant import Quantization


class JoyCaptionBackend(InferenceBackend):
    def __init__(self, config: dict):
        modelPath = config.get("model_path")
        self.generationConfig = GenerationConfig.from_pretrained(modelPath)

        super().__init__(config)

        skipModules = ["vision_tower", "multi_modal_projector"]
        devmap = self.makeDeviceMap(modelPath, config.get("gpu_layers"), config.get("vis_gpu_layers"))
        quant = Quantization.getQuantConfig(config.get("quantization"), devmap.hasCpuLayers, skipModules)

        self.model = LlavaForConditionalGeneration.from_pretrained(
            modelPath,
            torch_dtype=torch.bfloat16,
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


    def caption(self, imgPath: str, prompts: list[dict[str, str]], systemPrompt: str = None) -> dict[str, str]:
        image = Image.open(imgPath)
        answers = dict()

        set_seed(self.randomSeed())

        for conversation in prompts:
            messages = []
            if systemPrompt:
                messages.append( {"role": "system", "content": systemPrompt.strip()} )

            for name, prompt in conversation.items():
                messages.append( {"role": "user", "content": prompt.strip()} )
                inputText = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

                inputs = self.processor(text=[inputText], images=[image], return_tensors="pt")
                inputs = inputs.to("cuda")
                inputs['pixel_values'] = inputs['pixel_values'].to(torch.bfloat16)

                with torch.inference_mode():
                    generatedIDs = self.model.generate(**inputs, generation_config=self.generationConfig)[0]
                    generatedIDs = generatedIDs[inputs['input_ids'].shape[1]:]
                    outputText = self.processor.tokenizer.decode(generatedIDs, skip_special_tokens=True, clean_up_tokenization_spaces=False)

                answer = outputText.strip()
                messages.append( {"role": "assistant", "content": answer} )
                answers[name] = answer

        return answers


    @staticmethod
    def makeDeviceMap(modelPath, llmGpuLayers: int, visGpuLayers: int) -> DevMap:
        devmap = DevMap.fromConfig(
            modelPath,
            "-",
            "vision_config.num_hidden_layers"
        )
        devmap.maxLayerLLM = 31

        devmap.setCudaLayer("language_model")
        devmap.setCudaLayer("language_model.lm_head")
        devmap.setCudaLayer("language_model.model.embed_tokens")
        devmap.setCudaLayer("language_model.model.norm.weight")
        devmap.setLLMLayers("language_model.model.layers", llmGpuLayers)

        # Device mismatch with 0 GPU layers
        visGpuLayers = max(visGpuLayers, 1)

        if visGpuLayers == 0:
            devmap.setCpuLayer("vision_tower")
        else:
            devmap.setCudaLayer("vision_tower")
            devmap.setCudaLayer("vision_tower.vision_model.embeddings")
            devmap.setCudaLayer("vision_tower.vision_model.post_layernorm")
            devmap.setCudaLayer("vision_tower.vision_model.head")
            devmap.setVisLayers("vision_tower.vision_model.encoder.layers", visGpuLayers)

        devmap.setCudaLayer("multi_modal_projector")
        return devmap
