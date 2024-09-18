import random
from llama_cpp import Llama
from config import Config


class LLM:
    def __init__(self, config: dict = {}):
        self.config = {
            "max_tokens": 600,
            "temperature": 0.15,
            "top_p": 0.95,
            "top_k": 40,
            "min_p": 0.05,
            "typical_p": 1.0,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "repeat_penalty": 1.05,
            "mirostat_mode": 0,
            "mirostat_tau": 5.0,
            "mirostat_eta": 0.1,
            "tfs_z": 1.0
        }

        self.llm = Llama(
            model_path=config.get("model_path"),
            n_gpu_layers=config.get("gpu_layers", -1),
            n_ctx=config.get("ctx_length", 8192),
            n_batch=config.get("batch_size", 512),
            n_threads=config.get("num_threads", 15),
            flash_attn=True,
            seed=self.getSeed(),
            verbose=False
        )

        self.setConfig(config)


    def __del__(self):
        self.llm.close()


    def setConfig(self, config: dict):
        config = config.get(Config.INFER_PRESET_SAMPLECFG_KEY, {})
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
