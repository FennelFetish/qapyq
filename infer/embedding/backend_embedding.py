from abc import ABC, abstractmethod
import torch
from host.imagecache import ImageFile
from config import Config
from . import embedding_common as embed


class EmbeddingBackend(ABC):
    DEFAULT_PROMPT_TEMPLATES = ["{}"]

    def __init__(self, config: dict):
        self.setConfig(config)

    def setConfig(self, config: dict):
        # When running only for image embeddings, the CONFIG_KEY_PROMPT_TEMPLATES key is not present.
        sampleCfg: dict = config.get(Config.INFER_PRESET_SAMPLECFG_KEY, {})
        self.promptTemplates: list[str] = sampleCfg.get(embed.CONFIG_KEY_PROMPT_TEMPLATES, self.DEFAULT_PROMPT_TEMPLATES)


    def getTexts(self, prompt: str) -> list[str]:
        return [tpl.format(prompt) for tpl in self.promptTemplates]


    @abstractmethod
    def embedTextNumpyBytes(self, text: str) -> bytes:
        ...

    @abstractmethod
    def embedImagesNumpyBytes(self, imgFiles: list[ImageFile]) -> list[bytes]:
        ...



class TorchEmbeddingBackend(EmbeddingBackend):
    @abstractmethod
    def embedTexts(self, texts: list[str]) -> torch.Tensor:
        ...

    @abstractmethod
    def embedImages(self, imgFiles: list[ImageFile]) -> torch.Tensor:
        ...


    def embedTextNumpyBytes(self, text: str) -> bytes:
        texts = self.getTexts(text)
        tensor = self.embedTexts(texts).mean(dim=0).squeeze(0)
        self.normalizeRowsInPlace(tensor)
        return tensor.to("cpu", torch.float32).numpy().tobytes()

    def embedImagesNumpyBytes(self, imgFiles: list[ImageFile]) -> list[bytes]:
        mat = self.embedImages(imgFiles).to("cpu", torch.float32).numpy()
        return [v.tobytes() for v in mat]


    @staticmethod
    def normalizeRowsInPlace(tensor: torch.Tensor):
        tensor /= torch.linalg.vector_norm(tensor, dim=-1, keepdim=True)
