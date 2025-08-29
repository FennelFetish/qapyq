import torch
from transformers import SiglipModel, SiglipProcessor
from host.imagecache import ImageFile
from infer.devmap import DevMap
from .backend_embedding import TorchEmbeddingBackend


class Siglip(TorchEmbeddingBackend):
    MAX_LENGTH = 64

    def __init__(self, config: dict):
        super().__init__(config)

        modelPath = config["model_path"]
        self.model = SiglipModel.from_pretrained(modelPath, local_files_only=True)
        self.processor = SiglipProcessor.from_pretrained(modelPath, local_files_only=True, use_fast=True)

        self.device: torch.device = DevMap.getTorchDeviceDtype()[0]
        self.model = self.model.to(self.device).eval()

        # 49ms -> 47ms per file, 4 sec compilation
        #self.imgFeatures = torch.compile(self.model.get_image_features, mode="reduce-overhead")


    def embedTexts(self, texts: list[str]) -> torch.Tensor:
        inputs = self.processor(text=texts, padding="max_length", max_length=self.MAX_LENGTH, return_tensors="pt").to(self.device)
        with torch.inference_mode(), torch.autocast(self.device.type):
            text_embeds = self.model.get_text_features(**inputs)
            self.normalizeRowsInPlace(text_embeds)
            return text_embeds

    def embedImages(self, imgFiles: list[ImageFile]) -> torch.Tensor:
        images = [imgFile.openPIL(forceRGB=True) for imgFile in imgFiles]
        inputs = self.processor(images=images, return_tensors="pt").to(self.device)
        with torch.inference_mode(), torch.autocast(self.device.type):
            image_embeds = self.model.get_image_features(**inputs)
            #image_embeds = self.imgFeatures(**inputs)
            self.normalizeRowsInPlace(image_embeds)
            return image_embeds
