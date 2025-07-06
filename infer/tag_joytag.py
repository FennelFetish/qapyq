from .JoytagModels import VisionModel
import os, torch
import torch.amp.autocast_mode
import torchvision.transforms as transforms
import torchvision.transforms.functional as functional
import cv2 as cv
from config import Config
from .tag import TagBackend, ThresholdMode
from .devmap import DevMap


class JoyTag(TagBackend):
    DEFAULT_THRESH = 0.4

    def __init__(self, config: dict):
        super().__init__()

        self.thresholdMode: ThresholdMode = ThresholdMode(self.DEFAULT_THRESH, False)
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
        self.thresholdMode = ThresholdMode.fromConfig(config, "threshold", "threshold_mode", self.DEFAULT_THRESH)


    def tag(self, imgFile):
        img = self.loadImageSquare(imgFile, self.model.image_size)
        img = cv.cvtColor(img, cv.COLOR_BGR2RGB) / 255.0

        imgTensor = transforms.ToTensor()(img)
        imgTensor = functional.normalize(imgTensor, mean=[0.48145466, 0.4578275, 0.40821073], std=[0.26862954, 0.26130258, 0.27577711])

        tags = self.predict(imgTensor)
        return tags


    @torch.inference_mode()
    def predict(self, imgTensor: torch.Tensor):
        batch = { "image": imgTensor.unsqueeze(0).to(self.device) }

        with torch.amp.autocast_mode.autocast(self.device.type, enabled=True):
            predictions: dict[str, torch.Tensor] = self.model(batch)
            tagPredictions = predictions["tags"]
            tagPredictions = tagPredictions.sigmoid().cpu()[0]

        threshold = self.thresholdMode.threshold
        if self.thresholdMode.adaptive:
            tagPredictions = tagPredictions.numpy()
            threshold = self.calcAdaptiveThreshold(tagPredictions, threshold, self.thresholdMode.strict)
            threshold = max(threshold, self.MIN_THRESH)

        tagScores = sorted(
            ((tag, score) for tag, score in zip(self.topTags, tagPredictions) if score > threshold),
            key=lambda x: x[1],
            reverse=True
        )

        return ", ".join(x[0] for x in tagScores)
