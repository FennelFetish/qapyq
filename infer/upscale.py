from typing import Iterable
from spandrel import ImageModelDescriptor, ModelLoader
import spandrel_extra_arches
import torch
import torchvision.transforms as transforms
import numpy as np
from host.imagecache import ImageFile
from .devmap import DevMap

# add extra architectures before `ModelLoader` is used
spandrel_extra_arches.install()


TILE_SIZE    = 128
TILE_OVERLAP = 12  # Not the actual overlap value. Used for calculating tile count and dynamic overlap. Results in padding of 6+.
BATCH_SIZE   = 4


class Tile:
    def __init__(self):
        self.cropX: int = 0
        self.cropY: int = 0
        self.cropW: int = 0
        self.cropH: int = 0
        self.pasteX: int = 0
        self.pasteY: int = 0

    def scale(self, scaleX: int, scaleY: int):
        self.cropX *= scaleX
        self.cropY *= scaleY
        self.cropW *= scaleX
        self.cropH *= scaleY
        self.pasteX *= scaleX
        self.pasteY *= scaleY



class UpscaleBackend:
    def __init__(self, config: dict):
        self.device, _ = DevMap.getTorchDeviceDtype()

        self.model = ModelLoader().load_from_file(config.get("model_path"))
        assert isinstance(self.model, ImageModelDescriptor)
        self.model.to(self.device).eval()
        #self.model = torch.compile(self.model)

        self.toTensor = transforms.ToTensor()


    def setConfig(self, config: dict):
        pass


    @torch.inference_mode()
    def _upscaleImageBatch(self, mats: Iterable[np.ndarray]) -> list[np.ndarray]:
        tensors = [self.toTensor(mat) for mat in mats]
        batch = torch.stack(tensors).to(self.device) # shape: [batch, channels, height, width]

        batchResult = self.model(batch)
        batchResult = batchResult.cpu()

        results = list()
        for i in range(batchResult.shape[0]):
            mat = batchResult[i].numpy()
            mat *= 255
            results.append(mat.astype(np.uint8).transpose(1, 2, 0))
        return results


    def upscaleImage(self, imgFile: ImageFile) -> tuple[int, int, bytes]:
        mat = imgFile.openCvMat(rgb=True, allowGreyscale=False)
        return self._upscaleImageTiled(mat)

    def upscaleImageData(self, imgData: bytes, w: int, h: int) -> tuple[int, int, bytes]:
        channels = len(imgData) // (w*h)
        mat = np.frombuffer(imgData, dtype=np.uint8).copy()
        mat.shape = (h, w, channels)
        if channels < 3:
            mat = np.stack([mat] * 3, axis=-1) # Greyscale -> RGB
        return self._upscaleImageTiled(mat)


    def _upscaleImageTiled(self, mat: np.ndarray) -> tuple[int, int, bytes]:
        if mat.shape[2] > 3:
            matAlpha = mat[..., 3]
            mat = mat[..., :3]
        else:
            matAlpha = None

        origShape = mat.shape[:3]
        matResult = None
        scaleX = scaleY = 0

        queuedTiles: list[tuple[np.ndarray, Tile]] = list()
        for tileInfo in self._getTiles(mat):
            queuedTiles.append(tileInfo)
            if len(queuedTiles) >= BATCH_SIZE:
                matResult, scaleX, scaleY = self._runBatch(queuedTiles, origShape, matResult, scaleX, scaleY)
                queuedTiles.clear()

        if queuedTiles:
            matResult, scaleX, scaleY = self._runBatch(queuedTiles, origShape, matResult, scaleX, scaleY)

        resultH, resultW = matResult.shape[:2]

        if matAlpha is not None:
            import cv2 as cv
            matResult = cv.cvtColor(matResult, cv.COLOR_RGB2RGBA)
            matResult[:, :, 3] = cv.resize(matAlpha, dsize=(resultW, resultH), interpolation=cv.INTER_CUBIC)

        return resultW, resultH, matResult.tobytes()


    # Keep all tiles the same size for
    # a) Batch processing
    # b) Prevent model overhead for changing input shape.
    def _getTiles(self, mat: np.ndarray) -> Iterable[tuple[np.ndarray, Tile]]:
        h, w = mat.shape[:2]

        tileFeedX: int = TILE_SIZE if w <= TILE_SIZE else int(np.ceil(w / np.ceil(w / (TILE_SIZE-TILE_OVERLAP))))
        tileFeedY: int = TILE_SIZE if h <= TILE_SIZE else int(np.ceil(h / np.ceil(h / (TILE_SIZE-TILE_OVERLAP))))

        padX = (TILE_SIZE - tileFeedX) // 2
        padY = (TILE_SIZE - tileFeedY) // 2

        tileW = min(TILE_SIZE, w)
        tileH = min(TILE_SIZE, h)

        tileX = tileY = 0
        endX = endY = 0
        for tileY in range(0, h, tileFeedY):
            tileY = min(tileY, h-tileH)
            endX = 0

            for tileX in range(0, w, tileFeedX):
                tileX = min(tileX, w-tileW)

                matTile = mat[
                    tileY : tileY+tileH,
                    tileX : tileX+tileW,
                    ...
                ]

                # These coords define two regions to remove artifacts at tile edges:
                # 1. The crop region from the upscaled tile (excluding its top and left borders).
                # 2. The point in the final composite image where the cropped tile is pasted.
                # Cropping includes a padding defined by padX/padY but excludes other overlapping areas which were already set in the final image.
                # When pasting the tile, the padding partially overwrites the previous tiles and replaces their border regions.
                tile = Tile()
                tile.cropW = tileW - (endX-tileX)
                tile.cropH = tileH - (endY-tileY)
                tile.cropX = tileW - tile.cropW
                tile.cropY = tileH - tile.cropH
                tile.pasteX = tileX + tile.cropX
                tile.pasteY = tileY + tile.cropY
                yield matTile, tile

                endX = tileX + tileW - padX
            endY = tileY + tileH - padY


    def _runBatch(self, queuedTiles: list[tuple[np.ndarray, Tile]], origShape: tuple[int, int, int], matResult: np.ndarray | None, scaleX: int, scaleY: int):
        upscaleResults = self._upscaleImageBatch(entry[0] for entry in queuedTiles)

        if matResult is None:
            resultH, resultW = upscaleResults[0].shape[:2]
            tileH,   tileW   = queuedTiles[0][0].shape[:2]
            scaleY,  scaleX  = round(resultH / tileH), round(resultW / tileW)
            newH,    newW    = origShape[0]*scaleY, origShape[1]*scaleX
            matResult = np.zeros((newH, newW, origShape[2]), dtype=np.uint8)

        for (matTile, tile), matUpscaledTile in zip(queuedTiles, upscaleResults):
            tile.scale(scaleX, scaleY)

            cropTile = matUpscaledTile[
                tile.cropY : tile.cropY+tile.cropH,
                tile.cropX : tile.cropX+tile.cropW,
                ...
            ]

            matResult[
                tile.pasteY : tile.pasteY+tile.cropH,
                tile.pasteX : tile.pasteX+tile.cropW
            ] = cropTile

        return matResult, scaleX, scaleY
