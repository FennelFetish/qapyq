import numpy as np
import cv2 as cv
from typing_extensions import override
from host.imagecache import ImageFile
from lib import videorw
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

    @override
    def setConfig(self, config: dict):
        super().setConfig(config)
        self.includeRatings = False


    def _prepareMat(self, img: np.ndarray, blend: bool = False) -> np.ndarray:
        img = img.astype(np.float32)
        img /= 255.0

        # Blend onto white background
        if blend:
            alpha = img[:, :, 3:4]
            imgWhite = np.full((self.modelTargetSize, self.modelTargetSize, 3), 1.0, dtype=np.float32)
            imgWhite *= 1.0 - alpha
            imgWhite += img[:, :, :3] * alpha
            img = imgWhite

        # Normalize
        img -= self.MEAN
        img /= self.STD

        img = img.transpose(2, 0, 1) # HWC -> CHW
        return img


    @override
    def _loadImage(self, imgFile: ImageFile) -> np.ndarray:
        img = imgFile.openCvMat(allowGreyscale=False, rgb=True)
        srcHeight, srcWidth, srcChannels = img.shape

        # Resize & squish to 448x448
        interp = cv.INTER_LINEAR if max(srcWidth, srcHeight) < self.modelTargetSize else cv.INTER_AREA
        img = cv.resize(img, (self.modelTargetSize, self.modelTargetSize), interpolation=interp)

        blend = (srcChannels > 3)
        img = self._prepareMat(img, blend)
        img = np.expand_dims(img, 0)
        return img


    @override
    def _loadVideo(self, imgFile: ImageFile) -> list[np.ndarray]:
        def converterFactory(w: int, h: int):
            interp = videorw.Interpolation.AREA if max(w, h) < self.modelTargetSize else videorw.Interpolation.BILINEAR
            return videorw.createFrameConverter(self.modelTargetSize, self.modelTargetSize, interpolation=interp, format="rgb24")

        frames = imgFile.getVideoFramesCvMat(self.VIDEO_SAMPLE_FPS, self.VIDEO_MAX_FRAMES, converterFactory)
        frames = [self._prepareMat(frame) for frame in frames]

        batches = [np.stack(batchFrames) for batchFrames in self.getVideoBatches(frames)]
        return batches
