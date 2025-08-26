# https://huggingface.co/google/siglip-so400m-patch14-384/
# https://huggingface.co/docs/transformers/model_doc/siglip
# https://slyracoon23.github.io/blog/posts/2025-03-16_what_are_image_embeddings.html

# More versions and download links:
# https://github.com/google-research/big_vision/blob/main/big_vision/configs/proj/image_text/README_siglip2.md

# SigLIP 2:
# https://huggingface.co/docs/transformers/main/en/model_doc/siglip2
# https://huggingface.co/collections/google/siglip2-67b5dcef38c175486e240107


# https://huggingface.co/docs/transformers/installation#offline-mode
# >>>>>>>>>> Set the environment variable HF_HUB_OFFLINE=1 to prevent HTTP calls to the Hub when loading a model.


import torch
from transformers import SiglipModel, SiglipProcessor
from host.imagecache import ImageFile
from infer.devmap import DevMap
from .backend_embedding import EmbeddingBackend


class Siglip(EmbeddingBackend):
    MAX_LENGTH = 64

    def __init__(self, config: dict):
        super().__init__(config)

        modelPath = config["model_path"]
        self.model = SiglipModel.from_pretrained(modelPath, local_files_only=True)
        self.processor = SiglipProcessor.from_pretrained(modelPath, local_files_only=True, use_fast=True)

        self.device: torch.device = DevMap.getTorchDeviceDtype()[0]
        self.model = self.model.to(self.device).eval()

        #self.model = torch.compile(self.model, mode="reduce-overhead", fullgraph=True)
        # self.textFeatures = torch.compile(self.model.get_text_features, mode="reduce-overhead", fullgraph=True)
        self.imgFeatures = torch.compile(self.model.get_image_features, mode="reduce-overhead") #, fullgraph=True)
        # self.embedTexts = torch.compile(self.embedTexts, mode="reduce-overhead")
        #self.embedImages = torch.compile(self.embedImages, mode="reduce-overhead")


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
            #image_embeds = self.model.get_image_features(**inputs)
            image_embeds = self.imgFeatures(**inputs)
            self.normalizeRowsInPlace(image_embeds)
            return image_embeds
