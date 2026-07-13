import random
from abc import ABC, abstractmethod
from typing import Any
from config import Config
from host.imagecache import ImageFile
from infer.prompt_struct import Conversation


class InferenceBackend(ABC):
    def __init__(self, config: dict[str, Any]):
        self.stop: list[str] = []

        self.thinkEndTags: tuple[str, ...] = ()
        self.printReasoning: bool = True

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
            # "mirostat_mode": 0,
            # "mirostat_tau": 5.0,
            # "mirostat_eta": 0.1,
            # "tfs_z": 1.0
        }
        self.setConfig(config)


    def setConfig(self, config: dict):
        if sampleCfg := config.get(Config.INFER_PRESET_SAMPLECFG_KEY):
            self.config.update(sampleCfg)

    def setThinkEnd(self, *tags: str) -> 'InferenceBackend':
        self.thinkEndTags = tags
        return self


    @staticmethod
    def randomSeed():
        return random.randint(0, 2147483647)


    @staticmethod
    def mergeSystemPrompt(prompts: list[Conversation], systemPrompt: str) -> list[Conversation]:
        for conv in prompts:
            first = conv[0]
            text = Config.sysPromptFallbackTemplate.replace("{{systemPrompt}}", systemPrompt)
            first.prompt = text.replace("{{prompt}}", first.prompt)
        return prompts


    def stripReasoning(self, text: str) -> str:
        start = 0
        for tag in self.thinkEndTags:
            pos = text.rfind(tag, start)
            if pos >= 0:
                start = pos + len(tag)

        if start <= 0:
            return text

        if self.printReasoning:
            reasoningLines = iter(text[:start].splitlines())
            print(f"> Reasoning: {next(reasoningLines)}")
            for line in reasoningLines:
                print(f"> {line}")

        text = text[start:].lstrip()
        return text



class CaptionBackend(InferenceBackend):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)

    @abstractmethod
    def caption(self, imgFile: ImageFile, prompts: list[Conversation], systemPrompt: str = None) -> dict[str, str]:
        raise NotImplementedError()


class AnswerBackend(InferenceBackend):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)

    @abstractmethod
    def answer(self, prompts: list[Conversation], systemPrompt: str = None) -> dict[str, str]:
        raise NotImplementedError()
