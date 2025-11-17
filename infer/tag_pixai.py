import numpy as np
import cv2 as cv
from host.imagecache import ImageFile
from .tag_wd import WDTag


# TODO: Implement as embedding model for similarity search (output name = 'embedding')
# TODO: IPS
class PixAiTag(WDTag):
    MEAN = 0.5
    STD  = 0.5

    def __init__(self, config: dict):
        super().__init__(config)

        # inputs: 'input', shape = ['batch_size', 3, 448, 448]
        modelInput = self.model.get_inputs()[0]
        self.modelTargetSize = modelInput.shape[-1]
        self.inputName = modelInput.name

        self.outputNames = ['prediction']  # 'embedding', 'logits', 'prediction'


    def setConfig(self, config: dict):
        super().setConfig(config)
        self.includeRatings = False


    def _loadImage(self, imgFile: ImageFile) -> np.ndarray:
        img = imgFile.openCvMat(allowGreyscale=False, rgb=True)
        srcHeight, srcWidth, srcChannels = img.shape

        # Resize & squish to 448x448
        interpolation = cv.INTER_LINEAR if max(srcWidth, srcHeight) < self.modelTargetSize else cv.INTER_AREA
        img = cv.resize(img, (self.modelTargetSize, self.modelTargetSize), interpolation=interpolation)
        img = img.astype(np.float32)
        img /= 255.0

        # Blend onto white background
        if srcChannels > 3:
            alpha = img[:, :, 3:4]
            imgWhite = np.full((self.modelTargetSize, self.modelTargetSize, 3), 1.0, dtype=np.float32)
            imgWhite *= 1.0 - alpha
            imgWhite += img[:, :, :3] * alpha
            img = imgWhite

        # Normalize
        img -= self.MEAN
        img /= self.STD

        img = img.transpose(2, 0, 1) # HWC -> CHW
        img = np.expand_dims(img, 0)
        return img
