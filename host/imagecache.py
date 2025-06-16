from __future__ import annotations
from typing import Callable
from io import BytesIO


class ImageFile:
    MIME_TYPES = ["image/png", "image/jpeg"]

    def __init__(self, file: str, data: bytearray | None = None):
        self.file = file
        self.data = data
        self.size = 0
        self._callbacks: list[Callable[[ImageFile], None]] | None = None


    @staticmethod
    def fromMsg(msg: dict):
        file = msg["img"]
        if data := msg.get("img_data"):
            imgFile = ImageFile(file, data)
            imgFile.size = len(data)
            return imgFile

        return ImageFile(file)


    def addData(self, data: bytes, totalSize: int):
        if self.data is None:
            self.data = bytearray(totalSize)

        end = self.size + len(data)
        if end > len(self.data):
            raise OverflowError("ImageCache size mismatch")

        self.data[self.size:end] = data
        self.size = end

        if end >= len(self.data):
            self._notifyComplete()


    def isComplete(self) -> bool:
        return (self.data is not None) and self.size >= len(self.data)

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
            return Image.open(BytesIO(self.data))
        return Image.open(self.file)

    def getURI(self) -> str:
        import base64, mimetypes
        mimetype = mimetypes.guess_type(self.file)[0]
        if mimetype in self.MIME_TYPES:
            if self.data:
                imgData = self.data
            else:
                return f"file://{self.file}"

        else:
            buffer = BytesIO()
            img = self.openPIL()
            img.save(buffer, format='PNG', optimize=False, compress_level=0)
            imgData = buffer.getvalue()
            mimetype = "image/png"

        base64Data = base64.b64encode(imgData).decode('utf-8')
        return "".join(("data:", mimetype, ";base64,", base64Data))



class ImageCache:
    def __init__(self):
        self.images: dict[str, ImageFile] = dict()
        self.totalSize = 0

    def recvImageData(self, file: str, data: bytes, totalSize: int):
        imgFile = self.getImage(file)
        imgFile.addData(data, totalSize)
        self.totalSize += len(data)

    def getImage(self, file: str) -> ImageFile:
        imgFile = self.images.get(file)
        if not imgFile:
            self.images[file] = imgFile = ImageFile(file)
        return imgFile

    def releaseImage(self, file: str):
        if imgFile := self.images.pop(file, None):
            assert imgFile.data is not None
            self.totalSize -= imgFile.size

    def clear(self):
        self.images.clear()
        self.totalSize = 0
