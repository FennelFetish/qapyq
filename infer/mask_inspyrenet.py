# https://github.com/plemeri/transparent-background
# Models: https://github.com/plemeri/InSPyReNet/blob/main/docs/model_zoo.md

import cv2 as cv
import numpy as np
from transparent_background import Remover

class InspyrenetMask:
    def __init__(self, config: dict):
        self.model = Remover(
            ckpt=config.get("model_path"),
            mode='base',
            jit=True,
            device='cuda:0',
            resize="static"
        )


    def mask(self, imgPath: str, classes: list[str]) -> bytes:
        image = cv.imread(imgPath, cv.IMREAD_UNCHANGED)

        channels = image.shape[2] if len(image.shape)>2 else 1
        if channels == 1:
            image = np.stack([image] * 3, axis=-1) # Greyscale -> RGB
        else:
            image = image[..., 2::-1] # BGR(A) -> RGB

        mask: np.ndarray = self.model.process(image, type="map")
        return mask[..., 0].tobytes()
