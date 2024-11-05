from transformers import AutoModelForCausalLM, AutoProcessor, set_seed
import torch, re
from PIL import Image
from typing import List, Dict
from .backend import InferenceBackend
from .devmap import DevMap
from .quant import Quantization


class Florence2Backend(InferenceBackend):
    def __init__(self, config: dict):
        super().__init__(config)
        modelPath = config.get("model_path")
        self.tagPattern = re.compile(r'<[^>]*>')

        if torch.cuda.is_available():
            self.device = "cuda:0"
            self.dtype = torch.bfloat16
        else:
            self.device = "cpu"
            self.dtype = torch.float32

        devmap = self.makeDeviceMap(modelPath, config.get("gpu_layers"), config.get("vis_gpu_layers"))
        quant = Quantization.getQuantConfig(config.get("quantization"), devmap.hasCpuLayers)

        self.model = AutoModelForCausalLM.from_pretrained(
            modelPath,
            torch_dtype=self.dtype,
            device_map=devmap.deviceMap,
            attn_implementation=devmap.attention,
            quantization_config=quant,
            trust_remote_code=True
        )#.to(self.device)

        self.processor = AutoProcessor.from_pretrained(
            modelPath,
            trust_remote_code=True
        )

    
    def setConfig(self, config: dict):
        super().setConfig(config)

        self.genArgs = {
            "max_new_tokens": self.config.get("max_tokens"),
            "stop_strings": (self.stop if self.stop else None),
            "do_sample": self.config.get("temperature") > 0.01,

            "temperature": self.config.get("temperature"),
            "top_k": self.config.get("top_k"),
            "top_p": self.config.get("top_p"),
            "min_p": self.config.get("min_p"),
            "typical_p": self.config.get("typical_p"),
            "repetition_penalty": self.config.get("repeat_penalty"),

            "num_beams": 3
        }


    def caption(self, imgPath: str, prompts: List[Dict[str, str]], systemPrompt: str = None) -> Dict[str, str]:
        image = Image.open(imgPath)
        answers = dict()

        set_seed(self.randomSeed())

        for conversation in prompts:
            for name, prompt in conversation.items():
                tags = self.tagPattern.findall(prompt)
                task = tags[0].upper() if tags else "<DETAILED_CAPTION>"

                prompt = self.tagPattern.sub("", prompt)
                prompt = prompt.strip()

                with torch.inference_mode():
                    answers[name] = self.runTask(image, task, prompt)

        return answers

    def runTask(self, image, task, prompt=None):
        if prompt and task == "<CAPTION_TO_PHRASE_GROUNDING>":
            prompt = task + prompt
        else:
            prompt = task

        inputs = self.processor(text=prompt, images=image, return_tensors="pt").to(self.device, self.dtype)
        generated_ids = self.model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            **self.genArgs
        )

        generated_text = self.processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        parsed_answer = self.processor.post_process_generation(generated_text, task=task, image_size=(image.width, image.height))
        return str(parsed_answer.get(task))


    @staticmethod
    def makeDeviceMap(modelPath, llmGpuLayers: int, visGpuLayers: int) -> DevMap:
        devmap = DevMap.fromConfig(
            modelPath, 
            "text_config.num_hidden_layers"
        )
        devmap.maxLayerVis = 3

        devmap.setCudaLayer("language_model")
        devmap.setCudaLayer("language_model.lm_head")
        devmap.setCudaLayer("language_model.model.shared")

        devmap.setCudaLayer("language_model.model.encoder.embed_positions")
        devmap.setCudaLayer("language_model.model.encoder.layernorm_embedding")
        devmap.setLLMLayers("language_model.model.encoder.layers", llmGpuLayers)

        devmap.setCudaLayer("language_model.model.decoder.embed_positions")
        devmap.setCudaLayer("language_model.model.decoder.layernorm_embedding")
        devmap.setLLMLayers("language_model.model.decoder.layers", llmGpuLayers)
        
        if visGpuLayers == 0:
            devmap.setCpuLayer("image_projection")
            devmap.setCpuLayer("image_proj_norm")
            devmap.setCpuLayer("image_pos_embed")
            devmap.setCpuLayer("visual_temporal_embed") # Not printed with DevMap.printDeviceMap()

            devmap.setCpuLayer("vision_tower")
            devmap.setCpuLayer("vision_tower.convs")
            devmap.setCpuLayer("vision_tower.blocks")
        else:
            devmap.setCudaLayer("image_projection")
            devmap.setCudaLayer("image_proj_norm")
            devmap.setCudaLayer("image_pos_embed")
            devmap.setCudaLayer("visual_temporal_embed") # Not printed with DevMap.printDeviceMap()

            devmap.setCudaLayer("vision_tower")
            devmap.setCudaLayer("vision_tower.convs")
            devmap.setVisLayers("vision_tower.blocks", visGpuLayers)

        return devmap
