from typing import Any
import random
from abc import ABC, abstractmethod
from config import Config
from host.imagecache import ImageFile


class InferenceBackend(ABC):
    def __init__(self, config: dict[str, Any]):
        self.stop: list[str] = []

        self.config: dict[str, Any]= {
            "max_tokens": 1000,
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
        self.setConfig(config)


    def setConfig(self, config: dict):
        config = config.get(Config.INFER_PRESET_SAMPLECFG_KEY, {})
        self.config.update(config)


    @staticmethod
    def randomSeed():
        return random.randint(0, 2147483647)


    @staticmethod
    def mergeSystemPrompt(prompts: list[dict[str, str]], systemPrompt: str) -> list[dict[str, str]]:
        for conv in prompts:
            name, prompt  = next(iter(conv.items())) # First entry
            text = Config.sysPromptFallbackTemplate.replace("{{systemPrompt}}", systemPrompt)
            text = text.replace("{{prompt}}", prompt)
            conv[name] = text
        return prompts



class CaptionBackend(InferenceBackend):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)

    @abstractmethod
    def caption(self, imgFile: ImageFile, prompts: list[dict[str, str]], systemPrompt: str = None) -> dict[str, str]:
        raise NotImplementedError()


class AnswerBackend(InferenceBackend):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)

    @abstractmethod
    def answer(self, prompts: list[dict[str, str]], systemPrompt: str = None) -> dict[str, str]:
        raise NotImplementedError()
