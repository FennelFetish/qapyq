from __future__ import annotations
from typing import Callable


# TODO: Upload Session, for ensuring cache is cleared on inference error


class ImageFile:
    def __init__(self, file: str, data: bytearray | None = None):
        self.file = file
        self.data = data
        self.size = 0
        self._callbacks: list[Callable[[ImageFile], None]] | None = None

    @staticmethod
    def empty(filename: str, size: int):
        return ImageFile(filename, bytearray(size))

    @staticmethod
    def fromMsg(msg: dict):
        file = msg["img"]
        if data := msg.get("img_data"):
            print(f"{file}: Using data from buffer")
            imgFile = ImageFile(file, data)
            imgFile.size = len(data)
            return imgFile

        print(f"{file}: Loading from file")
        return ImageFile(file)


    def addData(self, data: bytes):
        assert self.data is not None

        end = self.size + len(data)
        if end > len(self.data):
            raise OverflowError("ImageCache size mismatch")

        self.data[self.size:end] = data
        self.size = end

        if end >= len(self.data):
            print(f">>> Upload complete: '{self.file}'")
            self._notifyComplete()


    def isComplete(self) -> bool:
        return (self.data is None) or self.size >= len(self.data)

    def addCompleteCallback(self, callback: Callable[[ImageFile], None]):
        if self._callbacks is None:
            self._callbacks = list()
        self._callbacks.append(callback)

    def _notifyComplete(self):
        if not self._callbacks:
            return
        for cb in self._callbacks:
            cb(self)
        self._callbacks = None


    def openCvMat(self):
        import cv2 as cv
        if self.data:
            import numpy as np
            arr = np.frombuffer(self.data, dtype=np.uint8)
            return cv.imdecode(arr, cv.IMREAD_UNCHANGED)
        return cv.imread(self.file, cv.IMREAD_UNCHANGED)

    def openPIL(self):
        from PIL import Image
        if self.data:
            import io
            return Image.open(io.BytesIO(self.data))
        return Image.open(self.file)



class ImageCache:
    def __init__(self):
        self.images: dict[str, ImageFile] = dict()
        self.totalSize = 0

    def recvImageData(self, file: str, data: bytes, totalSize: int):
        imgFile = self.images.get(file)
        if not imgFile:
            self.images[file] = imgFile = ImageFile.empty(file, totalSize)

        imgFile.addData(data)
        self.totalSize += len(data)
        #print(f"Received image data for '{file}', total cache size: {self.totalSize}")

    def getImage(self, file: str) -> ImageFile | None:
        return self.images.get(file)

    def releaseImage(self, file: str):
        if imgFile := self.images.pop(file, None):
            assert imgFile.data is not None
            self.totalSize -= imgFile.size
            #print(f"Released from ImageCache: {file} (total chache size down to: {self.totalSize})")
