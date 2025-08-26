from abc import ABC, abstractmethod
import torch
from host.imagecache import ImageFile


TEXT_TEMPLATES = [
    "{}",
    # "{} in a photo",
    # "{} captured in detail",
    # "{} partially visible",

    # "{} shown in a photo",
    # "{} shown in a rendering",
    # "{} shown in a cropped photo",
    # "{} shown in a bad photo",
    # "{} shown in a blurry photo",
    # "{} shown in a distorted photo",
    # "{} shown in a good photo",
    # "{} shown in a close-up photo",
    # "{} shown in a painting",

    "a photo of {}",
    "a rendering of {}",
    "a cropped photo of {}",
    "a bad photo of {}",
    "a blurry photo of {}",
    "a distorted photo of {}",
    "a good photo of {}",
    "a close-up photo of {}",
    "a painting of {}",
    "a drawing of {}",
    "an illustration of {}",
    "an image of {}",
    "a screenshot of {}",
    "a caricature of {}",
    "a photo of the hard-to-see {}",
    "a low-res photo of {}",
    "a high-res photo of {}",
    "a stylish photo of {}",
    "a bland photo of {}",
    "a scene with {}",

    # "a photo with {} visible",

    # "a photo of a {}",
    # "a rendering of a {}",
    # "a cropped photo of the {}",
    # "a bad photo of a {}",
    # "a blurry photo of a {}",
    # "a distorted photo of a {}",
    # "a good photo of a {}",
    # "a close-up photo of a {}",
    # "a painting of a {}",
    # "a drawing of a {}",
    # "an illustration of a {}",
    # "an image of a {}",
    # "a caricature of a {}",
    # "a photo of the hard-to-see {}",
    # "a low-res photo of a {}",
    # "a high-res photo of a {}",
    # "a stylish photo of a {}",
    # "a bland photo of a {}",

    # "a {} depicted in a photo",
    # "a {} depicted in a rendering",
    # "a {} depicted in a cropped photo",
    # "a {} depicted in a bad photo",
    # "a {} depicted in a blurry photo",
    # "a {} depicted in a distorted photo",
    # "a {} depicted in a good photo",
    # "a {} depicted in a close-up photo",
    # "a {} depicted in a painting",
]



class EmbeddingBackend(ABC):
    def __init__(self, config: dict):
        #self.cossim: CosineSimilarity | None = None
        pass

    def setConfig(self, config: dict):
        pass


    @staticmethod
    def normalizeRowsInPlace(tensor: torch.Tensor):
        tensor /= torch.linalg.vector_norm(tensor, dim=-1, keepdim=True)


    @abstractmethod
    def embedTexts(self, texts: list[str]) -> torch.Tensor:
        ...

    @abstractmethod
    def embedImages(self, imgFiles: list[ImageFile]) -> torch.Tensor:
        ...


    def embedTextNumpyBytes(self, text: str) -> bytes:
        texts = [tpl.format(text) for tpl in TEXT_TEMPLATES]
        tensor = self.embedTexts(texts).mean(dim=0).squeeze(0)
        self.normalizeRowsInPlace(tensor)
        return tensor.to("cpu", torch.float32).numpy().tobytes()

    def embedImagesNumpyBytes(self, imgFiles: list[ImageFile]) -> list[bytes]:
        mat = self.embedImages(imgFiles).to("cpu", torch.float32).numpy()
        return [v.tobytes() for v in mat]


    # def imgTextSimilarity(self, imgFile: ImageFile, texts: list[str]) -> list[float]:
    #     if not texts:
    #         return []

    #     if self.cossim is None or self.cossim.texts != texts:
    #         self.cossim = CosineSimilarity(self, texts)
    #     return self.cossim.score(imgFile)



# class CosineSimilarity:
#     def __init__(self, backend: EmbeddingBackend, texts: list[str]):
#         self.backend = backend
#         self.texts = texts

#         textGroups = [
#             [tpl.format(text) for tpl in TEXT_TEMPLATES]
#             for text in texts
#         ]

#         # print(f"CosineSimilarity with groups:")
#         # for i, group in enumerate(textGroups, 1):
#         #     print(f"=> {i}) {group}")

#         embeddings = []
#         for texts in textGroups:
#             emb = self.backend.embedTexts(texts).mean(dim=0)
#             emb = F.normalize(emb, dim=-1)
#             embeddings.append(emb)
#         self.textEmbeddings = torch.stack(embeddings)

#     def score(self, imgFile: ImageFile) -> list[float]:
#         imgEmbedding = self.backend.embedImage(imgFile)
#         cossim = (imgEmbedding @ self.textEmbeddings.T).squeeze(0)
#         return cossim.tolist()
