from .JoytagModels import VisionModel
import torch
import torch.amp.autocast_mode
import torchvision.transforms as transforms
import cv2 as cv
import os
from .tag import TagBackend
from config import Config


class JoyTag(TagBackend):
    def __init__(self, config: dict):
        self.threshold = 0.4
        self.setConfig(config)

        modelDir = config.get("model_path")
        self.model = VisionModel.load_model(modelDir).eval().to("cuda")
        
        with open(os.path.join(modelDir, "top_tags.txt"), 'r') as f:
            lines = (self.removeUnderscore(line.strip()) for line in f.readlines())
            self.topTags = [line for line in lines if line]


    def __del__(self):
        if hasattr(self, "model"):
            del self.model


    def setConfig(self, config: dict):
        config = config.get(Config.INFER_PRESET_SAMPLECFG_KEY, {})
        self.threshold = float(config.get("threshold", 0.4))


    def tag(self, imgPath):
        img = self.loadImageSquare(imgPath, self.model.image_size)
        img = cv.cvtColor(img, cv.COLOR_BGR2RGB) / 255.0

        imgTensor = transforms.ToTensor()(img)
        imgTensor = transforms.functional.normalize(imgTensor, mean=[0.48145466, 0.4578275, 0.40821073], std=[0.26862954, 0.26130258, 0.27577711])

        tags, scores = self.predict(imgTensor)
        return tags


    @torch.inference_mode()
    def predict(self, imgTensor: torch.Tensor):
        batch = { 'image': imgTensor.unsqueeze(0).to('cuda') }

        with torch.amp.autocast_mode.autocast('cuda', enabled=True):
            predictions = self.model(batch)
            tagPredictions = predictions['tags'].sigmoid().cpu()
        
        scores = {self.topTags[i]: tagPredictions[0][i] for i in range(len(self.topTags))}
        tags = [tag for tag, score in scores.items() if score > self.threshold]
        return ', '.join(tags), scores
