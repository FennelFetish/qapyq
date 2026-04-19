import os, torch
import torch.amp.autocast_mode
import torchvision.transforms.functional as functional
import numpy as np
from host.imagecache import ImageFile
from config import Config
from .JoytagModels import VisionModel
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


    @staticmethod
    def _prepareTensor(batchMat: np.ndarray) -> torch.Tensor:
        batchMat = batchMat.transpose(0, 3, 1, 2) # BHWC -> BCHW
        batchTensor = torch.tensor(batchMat, dtype=torch.float32)
        batchTensor /= 255.0

        for img in batchTensor:
            functional.normalize(img, mean=[0.48145466, 0.4578275, 0.40821073], std=[0.26862954, 0.26130258, 0.27577711], inplace=True)

        return batchTensor


    def tag(self, imgFile: ImageFile):
        preds: torch.Tensor = None

        if imgFile.isVideo():
            for batch in self.loadVideoSquare(imgFile, self.model.image_size, rgb=True):
                batchTensor = self._prepareTensor(batch)
                batchPreds = self.predict(batchTensor)
                batchPreds = batchPreds.mean(0)
                preds = batchPreds if preds is None else torch.maximum(preds, batchPreds, out=preds)

        else:
            img = self.loadImageSquare(imgFile, self.model.image_size, rgb=True)
            img = np.expand_dims(img, axis=0)
            batchTensor = self._prepareTensor(img)
            preds = self.predict(batchTensor)[0]

        return self.predsToTags(preds.cpu())


    @torch.inference_mode()
    def predict(self, batchTensor: torch.Tensor) -> torch.Tensor:
        batch = { "image": batchTensor.to(self.device) }

        with torch.amp.autocast_mode.autocast(self.device.type, enabled=True):
            predictions: dict[str, torch.Tensor] = self.model(batch)
            tagPredictions = predictions["tags"]
            tagPredictions = tagPredictions.sigmoid()

        return tagPredictions


    def predsToTags(self, tagPredictions: torch.Tensor) -> str:
        threshold = self.thresholdMode.threshold
        if self.thresholdMode.adaptive:
            preds = tagPredictions.numpy()
            threshold = self.calcAdaptiveThreshold(preds, threshold, self.thresholdMode.strict)
            threshold = max(threshold, self.MIN_THRESH)
        else:
            preds = tagPredictions

        tagScores = sorted(
            ((tag, score) for tag, score in zip(self.topTags, preds) if score > threshold),
            key=lambda x: x[1],
            reverse=True
        )

        return ", ".join(x[0] for x in tagScores)
