import torch # Required for cuda provider
import onnxruntime as ort
import numpy as np
import os, json
from abc import ABC, abstractmethod
from typing import NamedTuple, Iterable, Callable
from typing_extensions import override
from PIL import Image
from host.imagecache import ImageFile
from infer.devmap import DevMap
from config import Config
from .backend_embedding import EmbeddingBackend
from . import embedding_common as embed


def debugSave(mat: np.ndarray, filename: str, patchname: str):
    filename, ext = os.path.splitext(os.path.basename(filename))
    filename = f"{filename}-{patchname}{ext}"
    exportPath = os.path.join(".cache/crops", filename)

    import cv2 as cv
    mat = cv.cvtColor(mat.astype(np.uint8), cv.COLOR_RGB2BGR)
    cv.imwrite(exportPath, mat)


def normalizeRowsInPlace(mat: np.ndarray):
    mat /= np.linalg.norm(mat, axis=-1, keepdims=True)



class SiglipOnnx(EmbeddingBackend):
    MAX_LENGTH = 64
    OUTPUT_NAMES = ["pooler_output"]

    def __init__(self, config: dict):
        super().__init__(config)

        self.modelPath = config["model_path"]
        self.textModelPath = config["text_model_path"]
        self.visionModelPath = config["vision_model_path"]

        self._sessOpts = ort.SessionOptions()
        self._sessOpts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        #self._sessOpts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED

        deviceId = DevMap.getDeviceId()
        self._providers = [
            # ("TensorrtExecutionProvider", {
            #     "device_id": deviceId,
            #     "trt_fp16_enable": True,
            #     #"trt_max_workspace_size": 2147483648
            # }),
            ("CUDAExecutionProvider", {
                "device_id": deviceId,
                "arena_extend_strategy": "kNextPowerOfTwo",
                #"gpu_mem_limit": 16 * 1024 * 1024 * 1024,
                "cudnn_conv_algo_search": "EXHAUSTIVE",
                "do_copy_in_default_stream": True,
                #"enable_cuda_graph": True,  # Doesn't work: Empty output
            }),
            "CPUExecutionProvider",
        ]

        self._imageModel = None
        self._textModel  = None
        self._tokenizer  = None

        #self.imageEmbedStrategy = EmbeddingComparison(self, LineCropEmbedding(self), CenterCropEmbedding(self))
        #self.imageEmbedStrategy = EmbeddingComparison(self, LineCropEmbedding(self, True, True), LineCropEmbedding(self))
        self.imageEmbedStrategy = self.getEmbedStrategy(config)


    def getEmbedStrategy(self, config: dict) -> "ImageEmbeddingStrategy":
        sampleCfg = config[Config.INFER_PRESET_SAMPLECFG_KEY]
        processing: str = sampleCfg[embed.CONFIG_KEY_PROCESSING]
        aggregate: str  = sampleCfg[embed.CONFIG_KEY_AGGREGATE]

        match processing.strip():
            case "center-crop":             return CenterCropEmbedding(self)
            case "squish-resize":           return FixedResizeEmbedding(self)
            case "multipatch":              return MultiPatchEmbedding(self, aggregate)
            case "multipatch-center-x":     return MultiPatchEmbedding(self, aggregate, True, False)
            case "multipatch-center-y":     return MultiPatchEmbedding(self, aggregate, False, True)
            case "multipatch-center-xy":    return MultiPatchEmbedding(self, aggregate, True, True)

        raise ValueError(f"Unknown processing strategy: '{processing}'")


    @property
    def imageModel(self):
        if self._imageModel is None:
            print(f"Loading SigLIP ONNX vision model from {self.visionModelPath}")
            self._imageModel = ort.InferenceSession(self.visionModelPath, sess_options=self._sessOpts, providers=self._providers)
        return self._imageModel

    def embedImagesNumpyBytes(self, imgFiles: list[ImageFile]) -> list[bytes]:
        return [emb.tobytes() for emb in self.imageEmbedStrategy.embedImages(imgFiles)]


    @property
    def textModel(self):
        if self._textModel is None:
            print(f"Loading SigLIP ONNX text model from {self.textModelPath}")
            self._textModel = ort.InferenceSession(self.textModelPath, sess_options=self._sessOpts, providers=self._providers)
        return self._textModel

    def tokenize(self, texts: list[str]) -> dict[str, np.ndarray]:
        if self._tokenizer is None:
            from transformers import AutoTokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(self.modelPath)

        inputs = self._tokenizer(
            texts, return_tensors="np",
            max_length=self.MAX_LENGTH, padding='max_length', truncation=True,
        )

        # Need to make a new dict for some reason.
        # input_ids shape: (num texts, max length)
        return {"input_ids": inputs["input_ids"]}

    def embedTextNumpyBytes(self, text: str) -> bytes:
        inputs = self.tokenize(self.getTexts(text))
        textFeatures: np.ndarray = self.textModel.run(self.OUTPUT_NAMES, inputs)[0]
        textFeatures = np.mean(textFeatures, axis=0)
        normalizeRowsInPlace(textFeatures)
        return textFeatures.tobytes()



class Size(NamedTuple):
    width: int
    height: int


class ImageEmbeddingStrategy(ABC):
    MEAN = [0.5, 0.5, 0.5]
    STD  = [0.5, 0.5, 0.5]
    H, W = 384, 384

    def __init__(self, backend: SiglipOnnx):
        self.backend = backend
        self.loadConfig(backend.modelPath, "preprocessor_config.json")

    def loadConfig(self, modelPath: str, filename: str):
        path = os.path.join(modelPath, filename)
        with open(path, "r") as file:
            data = json.load(file)

        self._normMean: list[int] = data.get("image_mean", self.MEAN)
        self._normStd: list[int]  = data.get("image_std", self.STD)

        size: dict = data.get("size", {"width": self.W, "height": self.H})
        self._size: Size = Size(size.get("width", self.W), size.get("height", self.H))

    def normalize(self, mat: np.ndarray) -> np.ndarray:
        mat /= 255.0
        mat = mat.transpose(2, 0, 1) # HWC -> CHW
        for c in range(3):
            mat[c] -= self._normMean[c]
            mat[c] /= self._normStd[c]
        return mat

    @abstractmethod
    def embedImages(self, imgFiles: list[ImageFile]) -> Iterable[np.ndarray]:
        'Return shape (1, dims)'
        ...



class SinglePatchEmbeddingStrategy(ImageEmbeddingStrategy):
    @override
    def embedImages(self, imgFiles: list[ImageFile]) -> Iterable[np.ndarray]:
        if len(imgFiles) == 1:
            inputs = self.loadSinglePatch(imgFiles[0])
            inputs.shape = (1, 3, self._size.height, self._size.width)
        else:
            images = [self.loadSinglePatch(imgFile) for imgFile in imgFiles]
            inputs = np.stack(images, axis=0)

        imageFeatures: np.ndarray = self.backend.imageModel.run(SiglipOnnx.OUTPUT_NAMES, {"pixel_values": inputs})[0]  # (images, dims)
        normalizeRowsInPlace(imageFeatures)
        return imageFeatures

    @abstractmethod
    def loadSinglePatch(self, imgFile: ImageFile) -> np.ndarray:
        ...


class FixedResizeEmbedding(SinglePatchEmbeddingStrategy):
    @override
    def loadSinglePatch(self, imgFile: ImageFile) -> np.ndarray:
        img = imgFile.openPIL(forceRGB=True)
        img = img.resize(self._size, resample=Image.Resampling.BICUBIC)

        mat = np.array(img, dtype=np.float32)
        #debugSave(mat, imgFile.file, f"Squish")
        return self.normalize(mat)


class CenterCropEmbedding(SinglePatchEmbeddingStrategy):
    @override
    def loadSinglePatch(self, imgFile: ImageFile) -> np.ndarray:
        img = imgFile.openPIL(forceRGB=True)
        origW, origH = img.size

        targetW, targetH = self._size
        scale = max(targetW/origW, targetH/origH) # TODO: If scale is positive -> Pad
        w, h = round(origW * scale), round(origH * scale)

        img = img.resize((w, h), resample=Image.Resampling.BICUBIC)
        mat = np.array(img, dtype=np.float32)

        if w > targetW:
            assert h == targetH
            x = (w - targetW) // 2
            mat = mat[:, x:x+targetW, :]
        elif h > targetH:
            assert w == targetW
            y = (h - targetH) // 2
            mat = mat[y:y+targetH, :, :]

        #debugSave(mat, imgFile.file, f"CenterCrop")
        return self.normalize(mat)



class MultiPatchEmbeddingStrategy(ImageEmbeddingStrategy):
    AGGREGATE_FUNCS: dict[str, Callable] = {
        "mean": np.sum, # Sum is equivalent to np.mean when also normalizing afterwards, but skips the division
        "max":  np.max
    }

    def __init__(self, backend: SiglipOnnx, aggregate: str):
        super().__init__(backend)
        self.aggregateFunc = self.AGGREGATE_FUNCS[aggregate]

    @override
    def embedImages(self, imgFiles: list[ImageFile]) -> Iterable[np.ndarray]:
        patches = list[np.ndarray]()
        filePatchCount = list[int]()
        for imgFile in imgFiles:
            filePatches = self.loadPatches(imgFile)
            patches.extend(filePatches)
            filePatchCount.append(len(filePatches))

        inputs = np.stack(patches, axis=0)
        imageFeatures: np.ndarray = self.backend.imageModel.run(SiglipOnnx.OUTPUT_NAMES, {"pixel_values": inputs})[0]

        patchEmbeddingsPerImage = np.split(imageFeatures, np.cumsum(filePatchCount[:-1]))
        for imgPatchFeatures in patchEmbeddingsPerImage:
            imgPatchFeatures = self.aggregateFunc(imgPatchFeatures, axis=0) # (n, dim) -> (dim)
            normalizeRowsInPlace(imgPatchFeatures)
            yield imgPatchFeatures

    @abstractmethod
    def loadPatches(self, imgFile: ImageFile) -> list[np.ndarray]:
        ...


class MultiPatchEmbedding(MultiPatchEmbeddingStrategy):
    MIN_OVERLAP = 1.0 + 0.125

    def __init__(self, backend: SiglipOnnx, aggregate: str, oddPatchesX=False, oddPatchesY=False):
        super().__init__(backend, aggregate)
        self.oddPatchesX = 1 if oddPatchesX else 0
        self.oddPatchesY = 1 if oddPatchesY else 0

        self.minStrideX = int(self._size.width  * (self.MIN_OVERLAP-1))
        self.minStrideY = int(self._size.height * (self.MIN_OVERLAP-1))

        # Minimum size difference required for rounding up
        # to the next odd patch count while respecting the minimum stride.
        # https://www.desmos.com/calculator/mryb7c1dmn
        self.minDiffOddX = self.minStrideX * 2
        self.minDiffOddY = self.minStrideY * 2


    def loadPatches(self, imgFile: ImageFile) -> list[np.ndarray]:
        img = imgFile.openPIL(forceRGB=True)
        origW, origH = img.size

        targetW, targetH = self._size
        scale = max(targetW/origW, targetH/origH)
        w, h = round(origW * scale), round(origH * scale)

        # When the size difference is small, squish the image and use only one patch (for speedup)
        dw = w - targetW
        if abs(dw) < self.minStrideX:
            w = targetW
            dw = 0

        dh = h - targetH
        if abs(dh) < self.minStrideY:
            h = targetH
            dh = 0

        img = img.resize((w, h), resample=Image.Resampling.BICUBIC)
        mat = np.array(img, dtype=np.float32)

        patches = list[np.ndarray]()
        if dw > 0:
            assert dh == 0
            numPatches = int(np.ceil(self.MIN_OVERLAP * w/targetW))
            if dw >= self.minDiffOddX:
                numPatches |= self.oddPatchesX # Round up to next odd number

            stride = dw // (numPatches-1)
            #print(f"{imgFile.file}: landscape image {origW}x{origH} -> {w}x{h}, patches={numPatches} @ stride={stride}")
            for x in range(0, dw+1, stride):
                patches.append(mat[:, x:x+targetW, :].copy())
            assert len(patches) == numPatches

        elif dh > 0:
            assert dw == 0
            numPatches = int(np.ceil(self.MIN_OVERLAP * h/targetH))
            if dh >= self.minDiffOddY:
                numPatches |= self.oddPatchesY # Round up to next odd number

            stride = dh // (numPatches-1)
            #print(f"{imgFile.file}: portrait image {origW}x{origH} -> {w}x{h}, patches={numPatches} @ stride={stride}")
            for y in range(0, dh+1, stride):
                patches.append(mat[y:y+targetH, :, :].copy())
            assert len(patches) == numPatches

        else:
            #print(f"{imgFile.file}: square image {origW}x{origH} -> {w}x{h}, patches=1")
            patches.append(mat)

        for i, patch in enumerate(patches):
            #debugSave(patch, imgFile.file, f"MultiPatch-{i}")
            patches[i] = self.normalize(patch)

        return patches



class EmbeddingComparison(ImageEmbeddingStrategy):
    def __init__(self, backend: SiglipOnnx, strategyMain: ImageEmbeddingStrategy, strategyCompare: ImageEmbeddingStrategy):
        super().__init__(backend)
        self.strategyMain = strategyMain
        self.strategyComp = strategyCompare

    @override
    def embedImages(self, imgFiles: list[ImageFile]) -> Iterable[np.ndarray]:
        embedMain = list(self.strategyMain.embedImages(imgFiles))

        allEmbedMain = np.stack(embedMain)
        allEmbedComp = np.stack(list( self.strategyComp.embedImages(imgFiles) ))

        cossim = allEmbedMain @ allEmbedComp.T
        for imgFile, val in zip(imgFiles, cossim.squeeze(0)):
            print(f"{val:0.8f} - {imgFile.file}")

        return embedMain
