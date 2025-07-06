from __future__ import annotations
from typing import NamedTuple
import cv2 as cv
import numpy as np
from host.imagecache import ImageFile

# TODO: Mode in which tags below a threshold are only added if they are a superset of tags above the threshold,
# for refining tags with colors for example.


# https://github.com/toriato/stable-diffusion-webui-wd14-tagger/blob/a9eacb1eff904552d3012babfa28b57e1d3e295c/tagger/ui.py#L368
kaomojis = {
    "0_0", "(o)_(o)", "+_+", "+_-", "._.", "<o>_<o>", "<|>_<|>", "=_=", ">_<", "3_3", "6_9", ">_o", "@_@", "^_^", "o_o", "u_u", "x_x", "|_|", "||_||"
}



class ThresholdMode(NamedTuple):
    threshold: float
    adaptive: bool
    strict: bool = False

    @staticmethod
    def fromConfig(config: dict, thresholdKey: str, modeKey: str, defaultThreshold: float) -> ThresholdMode:
        threshold = float(config.get(thresholdKey, defaultThreshold))
        thresholdMode = config.get(modeKey, "fixed")
        match thresholdMode:
            case "fixed":        return ThresholdMode(threshold, False)
            case "adapt_strict": return ThresholdMode(threshold, True, True)
            case "adapt_lax":    return ThresholdMode(threshold, True, False)

        print(f"WARNING: Unrecognized threshold mode for tagging: '{thresholdMode}'")
        return ThresholdMode(threshold, False)



class TagBackend:
    MIN_THRESH = 0.01

    def __init__(self):
        pass

    def setConfig(self, config: dict):
        raise NotImplementedError()

    def tag(self, imgFile: ImageFile) -> str:
        raise NotImplementedError()


    # TODO: Instead of padding, infer each half of image and combine tags. ("out of frame" problem?)
    @staticmethod
    def loadImageSquare(imgFile: ImageFile, targetSize: int):
        imgSrc = imgFile.openCvMat(allowGreyscale=False) # BGR(A) uint8
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


    # Repeat mcut with the probs after the largest gap and include clusters with:
    # - Strict: All scores >= threshold.
    # - Lax:    Highest score >= threshold.
    # When threshold is 1.0, this will act like the original mcut and always return the first cluster.
    @classmethod
    def calcAdaptiveThreshold(cls, probs: np.ndarray, threshold: float, strict: bool = False) -> float:
        lastThresh: float = 2.0
        for clusterHi, clusterLo, nextHi in cls._getProbsClusters(probs):
            if (clusterHi < threshold) or (strict and clusterLo < threshold):
                # Always include first cluster
                if lastThresh > 1.0:
                    lastThresh = float(clusterLo + nextHi) / 2
                break

            lastThresh = float(clusterLo + nextHi) / 2
            if clusterLo < threshold:
                break

        #print(f"> Adaptive Threshold: {lastThresh}")
        return lastThresh

    @staticmethod
    def _getProbsClusters(probs: np.ndarray):
        sortedProbs = probs[probs.argsort()[::-1]]  # n
        difs = sortedProbs[:-1] - sortedProbs[1:]   # n-1
        count = len(sortedProbs)

        idx = 0
        while idx < count:
            i = int(difs.argmax())

            #print(f"prob cluster[{idx}-{idx+i}]: {sortedProbs[idx]} - {sortedProbs[idx+i]}")
            yield sortedProbs[idx], sortedProbs[idx+i], sortedProbs[idx+i+1]

            idx += i + 1
            difs = difs[i+1:]


    @staticmethod
    def mcutThreshold(probs: np.ndarray):
        """
        Maximum Cut Thresholding (MCut)
        Largeron, C., Moulin, C., & Gery, M. (2012). MCut: A Thresholding Strategy
        for Multi-label Classification. In 11th International Symposium, IDA 2012
        (pp. 172-183).
        """
        sorted_probs = probs[probs.argsort()[::-1]]
        difs = sorted_probs[:-1] - sorted_probs[1:]
        t = difs.argmax()
        thresh = (sorted_probs[t] + sorted_probs[t + 1]) / 2
        return thresh
