from transformers import Qwen2VLForConditionalGeneration, AutoProcessor, GenerationConfig, set_seed
import torch
from PIL import Image
from typing import List, Dict
from .backend import InferenceBackend
from .devmap import DevMap
from .quant import Quantization


class Qwen2VLBackend(InferenceBackend):
    def __init__(self, config: dict):
        super().__init__(config)
        modelPath = config.get("model_path")

        devmap = self.makeDeviceMap(modelPath, config.get("gpu_layers"), config.get("vis_gpu_layers"))
        quant = Quantization.getQuantConfig(config.get("quantization"), devmap.hasCpuLayers)

        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            modelPath,
            torch_dtype=torch.bfloat16,
            device_map=devmap.deviceMap,
            attn_implementation=devmap.attention,
            quantization_config=quant,
            #vision_config={"torch_dtype": torch.bfloat16}
        )

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


    def caption(self, imgPath: str, prompts: List[Dict[str, str]], systemPrompt: str = None) -> Dict[str, str]:
        image = Image.open(imgPath)
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
                inputs = inputs.to("cuda")

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



# def printErr(text):
#     import sys, os
#     sys.stderr.write(text + os.linesep)
#     sys.stderr.flush()
