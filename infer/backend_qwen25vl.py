from typing import Any
from typing_extensions import override
from transformers import AutoProcessor, AutoConfig, GenerationConfig, set_seed
import torch, json, math
from PIL import Image
from host.imagecache import ImageFile
from .backend import CaptionBackend
from .devmap import DevMap
from .quant import Quantization


class QwenVLBackend(CaptionBackend):
    DETECT_SYSPROMPT = "You are a helpful assistant"
    DETECT_PROMPT    = "Outline the position of the requested elements and output coordinates in JSON format.\nRequested elements: "


    def __init__(self, config: dict[str, Any], modelClass: type):
        modelPath: str = config["model_path"]
        self.generationConfig = GenerationConfig.from_pretrained(modelPath)

        super().__init__(config)

        self.device, self.dtype = DevMap.getTorchDeviceDtype()
        devmap = self.makeDeviceMap(modelPath, self.device, config.get("gpu_layers", 100), config.get("vis_gpu_layers", 100))
        quant = Quantization.getQuantConfig(config.get("quantization", "none"), devmap.hasCpuLayers)

        self.model = modelClass.from_pretrained(
            modelPath,
            torch_dtype=self.dtype,
            device_map=devmap.deviceMap,
            attn_implementation=devmap.attention,
            quantization_config=quant,
        ).eval()

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
    def _runTask(self, image: Image.Image, messages: list) -> str:
        inputText = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

        inputs = self.processor(
            text=[inputText],
            images=[image],
            videos=None,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(self.device)

        generatedIDs = self.model.generate(**inputs, generation_config=self.generationConfig)
        generatedIDsTrimmed = [ out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generatedIDs) ]
        outputText = self.processor.batch_decode(generatedIDsTrimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)

        return outputText[0].strip()


    def caption(self, imgFile: ImageFile, prompts: list[dict[str, str]], systemPrompt: str = None) -> dict[str, str]:
        image = imgFile.openPIL()
        image = self.downscaleImage(image)

        answers = dict()
        set_seed(self.randomSeed())

        for conversation in prompts:
            messages = []
            if systemPrompt:
                messages.append( {"role": "system", "content": systemPrompt.strip()} )

            for i, (name, prompt) in enumerate(conversation.items()):
                messages.append( {"role": "user", "content": self._getUserContent(prompt, i, imgFile)} )
                answer = self._runTask(image, messages)
                messages.append( {"role": "assistant", "content": answer} )
                answers[name] = answer

        return answers


    def detectBoxes(self, imgFile: ImageFile, classes: list[str]):
        image = imgFile.openPIL()
        image = self.downscaleImage(image)
        w, h = image.size

        prompt = self.DETECT_PROMPT + ", ".join(classes)
        messages = [
            {"role": "system", "content": self.DETECT_SYSPROMPT},
            {"role": "user", "content": self._getUserContent(prompt, 0, imgFile)}
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
                "p0": self._normalizePoint(p0x, p0y, w, h),
                "p1": self._normalizePoint(p1x, p1y, w, h)
            })

        return results

    @staticmethod
    def _normalizePoint(x: int, y: int, imgW: int, imgH: int) -> tuple[float, float]:
        return (x/imgW, y/imgH)


    def _getUserContent(self, prompt: str, index: int, imgFile: ImageFile):
        if index == 0:
            return [
                {
                    "type": "image",
                    "image": imgFile.getURI()
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
    def makeDeviceMap(modelPath: str, device, llmGpuLayers: int, visGpuLayers: int) -> DevMap:
        raise NotImplementedError()



class Qwen25VLBackend(QwenVLBackend):
    def __init__(self, config: dict):
        from transformers import Qwen2_5_VLForConditionalGeneration
        super().__init__(config, Qwen2_5_VLForConditionalGeneration)

    @staticmethod
    @override
    def makeDeviceMap(modelPath: str, device, llmGpuLayers: int, visGpuLayers: int) -> DevMap:
        devmap = DevMap.fromConfig(
            modelPath,
            "num_hidden_layers",
            "vision_config.depth"
        )

        devmap.setDevice(device)

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


class Qwen3VLBackend(QwenVLBackend):
    THINK_END = "</think>"

    def __init__(self, config: dict[str, Any]):
        from transformers import Qwen3VLForConditionalGeneration
        super().__init__(config, Qwen3VLForConditionalGeneration)

    @override
    def _runTask(self, image: Image.Image, messages: list) -> str:
        output = super()._runTask(image, messages)

        thinkIndex = output.find(self.THINK_END)
        if thinkIndex >= 0:
            reasoning = output[:thinkIndex]
            print(f"Reasoning: {reasoning}")

            thinkIndex += len(self.THINK_END)
            output = output[thinkIndex:].strip()

        return output

    @staticmethod
    @override
    def _normalizePoint(x: int, y: int, imgW: int, imgH: int) -> tuple[float, float]:
        return (x/1000, y/1000)

    @staticmethod
    @override
    def makeDeviceMap(modelPath: str, device, llmGpuLayers: int, visGpuLayers: int) -> DevMap:
        devmap = DevMap.fromConfig(
            modelPath,
            "text_config.num_hidden_layers",
            "vision_config.depth"
        )

        devmap.setDevice(device)

        devmap.setCudaLayer("model")
        devmap.setCudaLayer("model.language_model")
        devmap.setCudaLayer("model.language_model.embed_tokens")
        devmap.setCudaLayer("model.language_model.norm")
        devmap.setLLMLayers("model.language_model.layers", llmGpuLayers)

        devmap.setCudaLayer("model.visual")
        devmap.setCudaLayer("model.visual.patch_embed")
        devmap.setCudaLayer("model.visual.pos_embed")
        devmap.setCudaLayer("model.visual.merger")
        devmap.setCudaLayer("model.visual.deepstack_merger_list")

        if visGpuLayers == 0:
            visGpuLayers = 1

        devmap.setVisLayers("model.visual.blocks", visGpuLayers)

        devmap.setCudaLayer("lm_head")
        return devmap



def getQwenVLBackend(config: dict):
        modelPath: str = config["model_path"]
        modelConfig = AutoConfig.from_pretrained(modelPath)

        match modelConfig.model_type:
            case "qwen2_5_vl":  return Qwen25VLBackend(config)
            case "qwen3_vl":    return Qwen3VLBackend(config)

        return Qwen3VLBackend(config)
