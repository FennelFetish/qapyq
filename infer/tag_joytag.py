from .JoytagModels import VisionModel
import os, torch
import torch.amp.autocast_mode
import torchvision.transforms as transforms
import cv2 as cv
from config import Config
from .tag import TagBackend
from .devmap import DevMap


class JoyTag(TagBackend):
    def __init__(self, config: dict):
        self.threshold = 0.4
        self.setConfig(config)

        self.device, _ = DevMap.getTorchDeviceDtype()

        modelDir = config.get("model_path")
        self.model = VisionModel.load_model(modelDir).to(self.device).eval()

        with open(os.path.join(modelDir, "top_tags.txt"), 'r') as f:
            lines = (self.removeUnderscore(line.strip()) for line in f.readlines())
            self.topTags = [line for line in lines if line]


    def __del__(self):
        if hasattr(self, "model"):
            del self.model


    def setConfig(self, config: dict):
        config = config.get(Config.INFER_PRESET_SAMPLECFG_KEY, {})
        self.threshold = float(config.get("threshold", 0.4))


    def tag(self, imgFile):
        img = self.loadImageSquare(imgFile, self.model.image_size)
        img = cv.cvtColor(img, cv.COLOR_BGR2RGB) / 255.0

        imgTensor = transforms.ToTensor()(img)
        imgTensor = transforms.functional.normalize(imgTensor, mean=[0.48145466, 0.4578275, 0.40821073], std=[0.26862954, 0.26130258, 0.27577711])

        tags = self.predict(imgTensor)
        return tags


    @torch.inference_mode()
    def predict(self, imgTensor: torch.Tensor):
        batch = { 'image': imgTensor.unsqueeze(0).to(self.device) }

        with torch.amp.autocast_mode.autocast(self.device.type, enabled=True):
            predictions = self.model(batch)
            tagPredictions = predictions['tags'].sigmoid().cpu()

        tagScores = sorted(
            ((tag, score) for tag, score in zip(self.topTags, tagPredictions[0]) if score > self.threshold),
            key=lambda x: x[1],
            reverse=True
        )

        return ', '.join(x[0] for x in tagScores)
