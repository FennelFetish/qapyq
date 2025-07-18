from transformers import Qwen2VLForConditionalGeneration, AutoProcessor, GenerationConfig, set_seed
import torch, math
from PIL import Image
from host.imagecache import ImageFile
from .backend import CaptionBackend
from .devmap import DevMap
from .quant import Quantization


class Qwen2VLBackend(CaptionBackend):
    def __init__(self, config: dict):
        super().__init__(config)
        modelPath = config.get("model_path")

        self.device, self.dtype = DevMap.getTorchDeviceDtype()
        devmap = self.makeDeviceMap(modelPath, self.device, config.get("gpu_layers"), config.get("vis_gpu_layers"))
        quant = Quantization.getQuantConfig(config.get("quantization"), devmap.hasCpuLayers)

        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            modelPath,
            torch_dtype=self.dtype,
            device_map=devmap.deviceMap,
            attn_implementation=devmap.attention,
            quantization_config=quant,
            #vision_config={"torch_dtype": self.dtype}
        ).eval()

        self.processor = AutoProcessor.from_pretrained(modelPath)


    def setConfig(self, config: dict):
        super().setConfig(config)

        # https://huggingface.co/docs/transformers/main_classes/text_generation
        self.generationConfig = GenerationConfig(
            max_new_tokens=self.config.get("max_tokens"),
            stop_strings=(self.stop if self.stop else None),
            do_sample=True,

            temperature=self.config.get("temperature"),
            top_k=self.config.get("top_k"),
            top_p=self.config.get("top_p"),
            min_p=self.config.get("min_p"),
            typical_p=self.config.get("typical_p"),
            repetition_penalty=self.config.get("repeat_penalty"),
        )


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
                messages.append( {"role": "user", "content": self._getUserContent(prompt, i)} )
                inputText = self.processor.apply_chat_template(messages, add_generation_prompt=True)

                # TODO: Only encode image once during first iteration. Look at implementation of Qwen2VLProcessor
                inputs = self.processor(text=[inputText], images=[image], padding=True, return_tensors="pt")
                inputs = inputs.to(self.device)

                with torch.inference_mode():
                    outputIDs = self.model.generate(**inputs, generation_config=self.generationConfig, tokenizer=self.processor.tokenizer)
                    generatedIDs = [
                        outputIDs[len(inputIDs) :]
                        for inputIDs, outputIDs in zip(inputs.input_ids, outputIDs)
                    ]
                    outputText = self.processor.batch_decode(generatedIDs, skip_special_tokens=True, clean_up_tokenization_spaces=True)

                answer = outputText[0].strip()
                messages.append( {"role": "assistant", "content": answer} )
                answers[name] = answer

        return answers


    def _getUserContent(self, prompt: str, index: int):
        if index == 0:
            return [
                {"type": "image"},
                {"type": "text", "text": prompt.strip()}
            ]
        else:
            return prompt.strip()


    def downscaleImage(self, image: Image.Image):
        width, height = image.size
        pixels = width * height
        maxPixels = 1024*1536

        scale = math.sqrt(maxPixels / pixels)
        if scale >= 1.0:
            return image

        newWidth  = round(width * scale)
        newHeight = round(height * scale)
        return image.resize((newWidth, newHeight), resample=Image.Resampling.BOX)


    @staticmethod
    def makeDeviceMap(modelPath, device, llmGpuLayers: int, visGpuLayers: int) -> DevMap:
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

        # FIXME: Offloading the visual layers to CPU causes OOM errors during inference for non-square images?
        if visGpuLayers == 0:
            devmap.setCpuLayer("visual")
        else:
            devmap.setCudaLayer("visual")
            devmap.setCudaLayer("visual.patch_embed")
            devmap.setCudaLayer("visual.merger")

        devmap.setVisLayers("visual.blocks", visGpuLayers)

        devmap.setCudaLayer("lm_head")
        return devmap
