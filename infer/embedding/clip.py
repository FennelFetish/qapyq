import torch
from transformers import CLIPConfig, CLIPModel, CLIPProcessor
from host.imagecache import ImageFile
from infer.devmap import DevMap
from .backend_embedding import TorchEmbeddingBackend


class Clip(TorchEmbeddingBackend):
    def __init__(self, config: dict):
        super().__init__(config)

        modelPath = config["model_path"]
        #self.model = self._loadModel(config["model_path"])
        self.model = CLIPModel.from_pretrained(modelPath, local_files_only=True)
        self.processor = CLIPProcessor.from_pretrained(modelPath, local_files_only=True) #, use_fast=True)

        self.device: torch.device = DevMap.getTorchDeviceDtype()[0]
        self.dtype = torch.float16 if torch.device.type != "cpu" else torch.float32
        self.model = self.model.to(self.device, self.dtype).eval()

        # No speedup, or slower
        #self.imgFeatures = torch.compile(self.model.get_image_features, mode="reduce-overhead")


    def _loadModelSafetensors(self, modelPath: str):
        from safetensors import safe_open

        stateDict = dict()
        with safe_open(modelPath, framework="pt", device="cpu") as f:
            for key in f.keys():
                stateDict[key] = f.get_tensor(key)

        configPath = "./res/tokenizer/clip-vit-large-patch14/"
        config: CLIPConfig = CLIPConfig.from_pretrained(configPath)
        model = CLIPModel(config)
        keys = model.load_state_dict(stateDict, strict=False)

        if keys.missing_keys:
            print("CLIP missing keys from safetensors:")
            for key in keys.missing_keys:
                print(f"  {key}")
            print()

        if keys.unexpected_keys:
            print("CLIP unexpected keys in safetensors:")
            for key in keys.unexpected_keys:
                print(f"  {key}")
            print()

        return model


    # TODO: Long prompts, mask padding?
    def embedTexts(self, texts: list[str]) -> torch.Tensor:
        inputs = self.processor(text=texts, return_tensors="pt", padding=True).to(self.device)
        with torch.inference_mode(), torch.autocast(self.device.type):
            text_embeds = self.model.get_text_features(**inputs)
            self.normalizeRowsInPlace(text_embeds)
            return text_embeds

    def embedImages(self, imgFiles: list[ImageFile]) -> torch.Tensor:
        images = [imgFile.openPIL() for imgFile in imgFiles]
        inputs = self.processor(images=images, return_tensors="pt").to(self.device)
        with torch.inference_mode(), torch.autocast(self.device.type):
            image_embeds = self.model.get_image_features(**inputs)
            self.normalizeRowsInPlace(image_embeds)
            return image_embeds
