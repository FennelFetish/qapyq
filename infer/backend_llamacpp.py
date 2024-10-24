from typing import Callable, List, Dict
from llama_cpp import Llama
from .backend import InferenceBackend


class LlamaCppBackend(InferenceBackend):
    def __init__(self, config: dict, **kwargs):
        super().__init__(config)

        self.llm = Llama(
            model_path=config.get("model_path"),
            n_gpu_layers=config.get("gpu_layers", -1),
            n_ctx=config.get("ctx_length", 32768), # n_ctx should be increased to accommodate the image embedding
            n_batch=config.get("batch_size", 512),
            n_threads=config.get("num_threads", 15),
            flash_attn=True,
            seed=self.randomSeed(),
            #logits_all=True,# needed to make llava work (DEPRECATED - set llama_batch.logits instead)
            verbose=False,
            **kwargs
        )

    # def __del__(self):
    #     self.llm.close()


    def answer(self, prompts: List[Dict[str, str]], systemPrompt=None) -> Dict[str, str]:
        def getUserContent(prompt: str, index: int):
            return prompt.strip()

        return self._tryAnswer(getUserContent, prompts, systemPrompt)


    def _tryAnswer(self, userContentFunc: Callable, prompts: List[Dict[str, str]], systemPrompt) -> Dict[str, str]:
        try:
            return self._answer(userContentFunc, prompts, systemPrompt)
        except ValueError as ex:
            if str(ex).startswith("System role not supported"): # TODO: Always same error string?
                # Fallback: Include system prompt in first user message
                prompts = self.mergeSystemPrompt(prompts, systemPrompt)
                return self._answer(userContentFunc, prompts, None)
            else:
                raise ex


    def _answer(self, userContentFunc: Callable, prompts: List[Dict[str, str]], systemPrompt: str | None) -> Dict[str, str]:
        answers = {}

        for conversation in prompts:
            messages = []
            if systemPrompt:
                messages.append( {"role": "system", "content": systemPrompt.strip()} )

            for i, (name, prompt) in enumerate(conversation.items()):
                messages.append( {"role": "user", "content": userContentFunc(prompt, i)} )

                completion = self.llm.create_chat_completion(
                    messages = messages,
                    stop=self.stop,
                    seed=self.randomSeed(),
                    **self.config
                )

                msg = completion["choices"][0]["message"]
                answer = msg["content"].strip()
                messages.append( {"role": msg["role"], "content": answer} )
                answers[name] = answer
        
        return answers



class LlamaCppVisionBackend(LlamaCppBackend):
    def __init__(self, config: dict, chatHandlerType: type):
        chatHandler = chatHandlerType(
            clip_model_path=config.get("proj_path"),
            verbose=False
        )

        super().__init__(config, chat_handler=chatHandler)
        self.stop.append("USER:")
        self.stop.append("ASSISTANT:")


    def caption(self, imgPath, prompts: List[Dict[str, str]], systemPrompt=None) -> Dict[str, str]:
        imgURI = self.imageToBase64(imgPath)
        def getUserContent(prompt: str, index: int):
            if index == 0:
                return [
                    {"type": "text", "text": prompt.strip()},
                    {"type": "image_url", "image_url": {"url": imgURI}}
                ]
            else:
                return prompt.strip()

        return self._tryAnswer(getUserContent, prompts, systemPrompt)
