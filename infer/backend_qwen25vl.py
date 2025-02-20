from typing import Any
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor, GenerationConfig, set_seed
import torch, json, math
from PIL import Image
from .backend import InferenceBackend
from .devmap import DevMap
from .quant import Quantization


class Qwen25VLBackend(InferenceBackend):
    DETECT_SYSPROMPT = "You are a helpful assistant"
    DETECT_PROMPT    = "Outline the position of the requested elements and output coordinates in JSON format.\nRequested elements: "


    def __init__(self, config: dict[str, Any]):
        modelPath: str = config["model_path"]
        self.generationConfig = GenerationConfig.from_pretrained(modelPath)

        super().__init__(config)

        devmap = self.makeDeviceMap(modelPath, config.get("gpu_layers", 100), config.get("vis_gpu_layers", 100))
        quant = Quantization.getQuantConfig(config.get("quantization", "none"), devmap.hasCpuLayers)

        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            modelPath,
            torch_dtype=torch.bfloat16,
            device_map=devmap.deviceMap,
            attn_implementation=devmap.attention,
            quantization_config=quant,
        )

        #minPx = 256 * 28 * 28
        #maxPx = 5120 * 28 * 28
        self.processor = AutoProcessor.from_pretrained(modelPath) #, min_pixels=minPx, max_pixels=maxPx)


    def setConfig(self, config: dict):
        super().setConfig(config)

        # No sampling in detection mode
        if "classes" in config:
            self.generationConfig.max_new_tokens     = 16384
            self.generationConfig.do_sample          = False
            self.generationConfig.temperature        = None
            self.generationConfig.top_k              = None
            self.generationConfig.top_p              = None
            self.generationConfig.min_p              = None
            self.generationConfig.typical_p          = None
            self.generationConfig.repetition_penalty = None

        else:
            self.generationConfig.max_new_tokens     = self.config.get("max_tokens")
            self.generationConfig.do_sample          = True
            self.generationConfig.temperature        = self.config.get("temperature")
            self.generationConfig.top_k              = self.config.get("top_k")
            self.generationConfig.top_p              = self.config.get("top_p")
            self.generationConfig.min_p              = self.config.get("min_p")
            self.generationConfig.typical_p          = self.config.get("typical_p")
            self.generationConfig.repetition_penalty = self.config.get("repeat_penalty")

        self.generationConfig.stop_strings = (self.stop if self.stop else None)


    def getClassNames(self) -> list[str]:
        return []


    @torch.inference_mode()
    def _runTask(self, image: Image.Image, messages) -> str:
        inputText = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

        inputs = self.processor(
            text=[inputText],
            images=[image],
            videos=None,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to("cuda")

        generatedIDs = self.model.generate(**inputs, generation_config=self.generationConfig)
        generatedIDsTrimmed = [ out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generatedIDs) ]
        outputText = self.processor.batch_decode(generatedIDsTrimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)

        return outputText[0].strip()


    def caption(self, imgPath: str, prompts: list[dict[str, str]], systemPrompt: str = None) -> dict[str, str]:
        image = Image.open(imgPath)
        image = self.downscaleImage(image)

        answers = dict()
        set_seed(self.randomSeed())

        for conversation in prompts:
            messages = []
            if systemPrompt:
                messages.append( {"role": "system", "content": systemPrompt.strip()} )

            for i, (name, prompt) in enumerate(conversation.items()):
                messages.append( {"role": "user", "content": self._getUserContent(prompt, i, imgPath)} )
                answer = self._runTask(image, messages)
                messages.append( {"role": "assistant", "content": answer} )
                answers[name] = answer

        return answers


    def detectBoxes(self, imgPath: str, classes: list[str]):
        image = Image.open(imgPath)
        image = self.downscaleImage(image)
        w, h = image.size

        prompt = self.DETECT_PROMPT + ", ".join(classes)
        messages = [
            {"role": "system", "content": self.DETECT_SYSPROMPT},
            {"role": "user", "content": self._getUserContent(prompt, 0, imgPath)}
        ]

        results = []

        answer = self._runTask(image, messages)
        answer = answer.strip("`")
        if not answer.startswith("json"):
            return results

        answer = answer[len("json"):]
        detections: list[dict[str, Any]] = json.loads(answer)
        for det in detections:
            coords: list[int] = det["bbox_2d"]
            label: str = det["label"]

            p0x, p0y, p1x, p1y = coords
            results.append({
                "name": label,
                "confidence": 1.0,
                "p0": (p0x/w, p0y/h),
                "p1": (p1x/w, p1y/h)
            })

        return results


    def _getUserContent(self, prompt: str, index: int, imgPath: str):
        if index == 0:
            return [
                {
                    "type": "image",
                    "image": f"file://{imgPath}"
                },
                {
                    "type": "text",
                    "text": prompt.strip()
                }
            ]
        else:
            return prompt.strip()


    def downscaleImage(self, image: Image.Image):
        width, height = image.size
        pixels = width * height
        maxPixels = 2048*2048

        scale = math.sqrt(maxPixels / pixels)
        if scale >= 1.0:
            return image

        newWidth  = round(width * scale)
        newHeight = round(height * scale)
        return image.resize((newWidth, newHeight), resample=Image.Resampling.BOX)


    @staticmethod
    def makeDeviceMap(modelPath, llmGpuLayers: int, visGpuLayers: int) -> DevMap:
        devmap = DevMap.fromConfig(
            modelPath,
            "num_hidden_layers",
            "vision_config.depth"
        )

        devmap.setCudaLayer("model")
        devmap.setCudaLayer("model.embed_tokens")
        devmap.setCudaLayer("model.norm")
        devmap.setLLMLayers("model.layers", llmGpuLayers)

        if visGpuLayers == 0:
            devmap.setCpuLayer("visual")
        else:
            devmap.setCudaLayer("visual")
            devmap.setCudaLayer("visual.patch_embed")
            devmap.setCudaLayer("visual.merger")
            devmap.setVisLayers("visual.blocks", visGpuLayers)

        devmap.setCudaLayer("lm_head")
        return devmap
