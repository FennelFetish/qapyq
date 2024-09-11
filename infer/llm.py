import base64, io, os, random
from llama_cpp import Llama


class LLM:
    def __init__(self, modelPath, config:dict={}):
        self.config = {
            "max_tokens": 600,
            "temperature": 0.15,
            "top_p": 0.95,
            "top_k": 60,
            "min_p": 0.05,
            "repeat_penalty": 1.05
        }

        self.llm = Llama(
            model_path=modelPath,
            n_gpu_layers=config.get("n_gpu_layers", -1),
            n_ctx=config.get("n_ctx", 8192), # n_ctx should be increased to accommodate the image embedding
            n_batch=512,
            n_threads=12,
            flash_attn=True,
            seed=self.getSeed(),
            verbose=False
        )

        self.setConfig(config)


    def __del__(self):
        self.llm.close()


    def setConfig(self, config: dict):
        if "n_ctx" in config:
            del config["n_ctx"]
        if "n_gpu_layers" in config:
            del config["n_gpu_layers"]
        self.config.update(config)


    def getSeed(self):
        return random.randint(0, 2147483647)

    
    def answer(self, prompts: dict, systemPrompt=None, rounds=1):
        try:
            return self._answer(prompts, systemPrompt, rounds)
        except ValueError as ex:
            if str(ex).startswith("System role not supported"):
                # Fallback: Include system prompt in first user message
                prompts = self._mergeSystemPrompt(prompts, systemPrompt)
                return self._answer(prompts, None, rounds)
            else:
                raise ex


    def _mergeSystemPrompt(self, prompts, systemPrompt) -> dict:
        name, prompt  = next(iter(prompts.items()))
        prompts[name] = "# System Instructions:\n" \
                      + systemPrompt + "\n\n" \
                      + "# Prompt:\n" \
                      + prompt
        return prompts


    def _answer(self, prompts: dict, systemPrompt=None, rounds=1):
        answers = {}

        for r in range(rounds):
            messages = []
            if systemPrompt:
                messages.append( {"role": "system", "content": systemPrompt.strip()} )

            for name, prompt in prompts.items():
                messages.append( {"role": "user", "content": prompt.strip()} )

                completion = self.llm.create_chat_completion(
                    messages = messages,
                    #stop=self.stop,
                    seed=self.getSeed(),
                    **self.config
                )

                msg = completion["choices"][0]["message"]
                answer = msg["content"].strip()
                messages.append( { "role": msg["role"], "content": f"{answer}\n"} )

                if r > 0:
                    name = f"{name}_round{r}"
                answers[name] = answer
        
        return answers
