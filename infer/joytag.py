from .JoytagModels import VisionModel
import torch
import torch.amp.autocast_mode
import torchvision.transforms as transforms
import numpy as np
import cv2
import os


class JoyTag:
    def __init__(self, path):
        self.model = VisionModel.load_model(path).eval().to("cuda")
        self.threshold = 0.4

        with open(os.path.join(path, "top_tags.txt"), 'r') as f:
            lines = (line.strip() for line in f.readlines())
            self.topTags = [line for line in lines if line]

    def __del__(self):
        if hasattr(self, "model"):
            del self.model
        if hasattr(self, "topTags"):
            del self.topTags


    def caption(self, imgPath):
        imgMat = cv2.imread(imgPath)
        imgMat = self.padImage(imgMat, self.model.image_size)
        
        imgTensor = transforms.ToTensor()(imgMat)
        #imgTensor = transforms.functional.normalize(imgTensor, mean=[0.48145466, 0.4578275, 0.40821073], std=[0.26862954, 0.26130258, 0.27577711])

        tags, scores = self.predict(imgTensor)
        return tags


    @torch.no_grad()
    def predict(self, imgTensor):
        batch = { 'image': imgTensor.unsqueeze(0).to('cuda') }

        with torch.amp.autocast_mode.autocast('cuda', enabled=True):
            predictions = self.model(batch)
            tagPredictions = predictions['tags'].sigmoid().cpu()
        
        scores = {self.topTags[i]: tagPredictions[0][i] for i in range(len(self.topTags))}
        tags = [tag for tag, score in scores.items() if score > self.threshold]
        return ', '.join(tags), scores


    # TODO: Instead of padding, infer each half of image and combine tags. ("out of frame" problem?)
    def padImage(self, imgSrc, targetSize: int):
        srcHeight, srcWidth, channels = imgSrc.shape
        if srcHeight < srcWidth:
            scaledHeight = targetSize * (srcHeight / srcWidth)
            scaledWidth  = targetSize
            padLeft = 0
            padTop  = int(targetSize - scaledHeight) // 2
        else:
            scaledHeight = targetSize
            scaledWidth  = targetSize * (srcWidth / srcHeight)
            padLeft = int(targetSize - scaledWidth) // 2
            padTop = 0
        
        scaledHeight = int(scaledHeight + 0.5)
        scaledWidth  = int(scaledWidth + 0.5)

        interpolation = cv2.INTER_LANCZOS4 if max(srcWidth, srcHeight) < targetSize else cv2.INTER_AREA
        imgScaled = cv2.resize(src=imgSrc, dsize=(scaledWidth, scaledHeight), interpolation=interpolation)
        imgScaled = cv2.cvtColor(imgScaled, cv2.COLOR_BGR2RGB)
        imgTarget = np.zeros((targetSize, targetSize, channels), dtype=imgScaled.dtype)
        imgTarget[padTop:padTop+scaledHeight, padLeft:padLeft+scaledWidth, :] = imgScaled
        return imgTarget
