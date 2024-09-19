from transformers import Qwen2VLForConditionalGeneration, AutoProcessor, GenerationConfig
import torch
from PIL import Image
from .backend import InferenceBackend


class Qwen2VLBackend(InferenceBackend):
    def __init__(self, config: dict):
        super().__init__(config)
        modelPath = config.get("model_path")

        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            modelPath,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            attn_implementation="flash_attention_2",
            vision_config={"torch_dtype": torch.bfloat16}
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


    def caption(self, imgPath: str, prompts: dict, systemPrompt: str = None, rounds=1) -> dict:
        image = Image.open(imgPath)
        answers = dict()

        for r in range(rounds):
            messages = []
            if systemPrompt:
                messages.append( {"role": "system", "content": systemPrompt.strip()} )

            for i, (name, prompt) in enumerate(prompts.items()):
                messages.append( {"role": "user", "content": self._getUserContent(prompt, i)} )
                inputText = self.processor.apply_chat_template(messages, add_generation_prompt=True)

                # TODO: Only encode image once during first iteration. Look at implementation of Qwen2VLProcessor
                inputs = self.processor(text=[inputText], images=[image], padding=True, return_tensors="pt")
                inputs = inputs.to("cuda")

                outputIDs = self.model.generate(**inputs, generation_config=self.generationConfig, tokenizer=self.processor.tokenizer)
                generatedIDs = [
                    outputIDs[len(inputIDs) :]
                    for inputIDs, outputIDs in zip(inputs.input_ids, outputIDs)
                ]
                outputText = self.processor.batch_decode(generatedIDs, skip_special_tokens=True, clean_up_tokenization_spaces=True)

                answer = outputText[0].strip()
                messages.append( {"role": "assistant", "content": answer} )

                if r > 0:
                    name = f"{name}_round{r}"
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


    def answer(self, prompts: dict, systemPrompt=None, rounds=1) -> dict:
        return {}


# import sys, os
# def printErr(text):
#     sys.stderr.write(text + os.linesep)
#     sys.stderr.flush()
