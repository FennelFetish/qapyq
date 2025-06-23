# https://github.com/plemeri/transparent-background
# Models: https://github.com/plemeri/InSPyReNet/blob/main/docs/model_zoo.md

import numpy as np
from transparent_background import Remover
from host.imagecache import ImageFile


class InspyrenetMask:
    def __init__(self, config: dict):
        self.model = Remover(
            ckpt=config.get("model_path"),
            mode='base',
            jit=True,
            device='cuda:0',
            resize="static"
        )


    def setConfig(self, config: dict):
        pass


    def mask(self, imgFile: ImageFile, classes: list[str]) -> bytes:
        mat = imgFile.openCvMat(rgb=True, forceRGB=True)
        mask: np.ndarray = self.model.process(mat, type="map")
        return mask[..., 0].tobytes()
