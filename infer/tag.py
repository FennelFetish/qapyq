import cv2 as cv
import numpy as np
from host.imagecache import ImageFile


# https://github.com/toriato/stable-diffusion-webui-wd14-tagger/blob/a9eacb1eff904552d3012babfa28b57e1d3e295c/tagger/ui.py#L368
kaomojis = {
    "0_0", "(o)_(o)", "+_+", "+_-", "._.", "<o>_<o>", "<|>_<|>", "=_=", ">_<", "3_3", "6_9", ">_o", "@_@", "^_^", "o_o", "u_u", "x_x", "|_|", "||_||"
}


class TagBackend:
    def __init__(self):
        pass

    def setConfig(self, config: dict):
        raise NotImplementedError()

    def tag(self, imgFile: ImageFile) -> str:
        raise NotImplementedError()

    # TODO: Instead of padding, infer each half of image and combine tags. ("out of frame" problem?)
    @staticmethod
    def loadImageSquare(imgFile: ImageFile, targetSize: int):
        imgSrc = imgFile.openCvMat() # BGR(A) uint8

        # Greyscale -> BGR
        if len(imgSrc.shape) < 3:
            imgSrc = np.stack([imgSrc] * 3, axis=-1)

        srcHeight, srcWidth, srcChannels = imgSrc.shape

        if srcHeight < srcWidth:
            scaledHeight = targetSize * (srcHeight / srcWidth)
            scaledHeight = int(scaledHeight + 0.5)
            scaledWidth  = targetSize
            padLeft = 0
            padTop  = int(targetSize - scaledHeight) // 2
        else:
            scaledHeight = targetSize
            scaledWidth  = targetSize * (srcWidth / srcHeight)
            scaledWidth  = int(scaledWidth + 0.5)
            padLeft = int(targetSize - scaledWidth) // 2
            padTop = 0

        interpolation = cv.INTER_LANCZOS4 if max(srcWidth, srcHeight) < targetSize else cv.INTER_AREA
        imgScaled = cv.resize(src=imgSrc, dsize=(scaledWidth, scaledHeight), interpolation=interpolation)

        imgTarget = np.full((targetSize, targetSize, 3), 255, dtype=np.float32)
        targetSlice = imgTarget[padTop:padTop+scaledHeight, padLeft:padLeft+scaledWidth, :]

        if srcChannels == 4:
            # Blend
            alpha = imgScaled[:, :, 3] / 255.0
            alphaInv = 1.0 - alpha
            for chan in range(3):
                targetSlice[:, :, chan] *= alphaInv
                targetSlice[:, :, chan] += imgScaled[:, :, chan] * alpha
        else:
            targetSlice[:] = imgScaled

        return imgTarget


    @staticmethod
    def removeUnderscore(tag: str) -> str:
        return tag if (tag in kaomojis) else tag.replace("_", " ")
