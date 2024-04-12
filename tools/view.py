from PySide6.QtCore import QRectF
from .tool import Tool


class ViewTool(Tool):
    def __init__(self):
        super().__init__()

    def getDropRects(self):
        return [QRectF(0, 0, 1, 1)]
    
    def onDrop(self, event, zoneIndex):
        firstUrl = event.mimeData().urls()[0]
        self._imgview._image.loadImage(firstUrl.toLocalFile())
        vpRect = self._imgview.viewport().rect()
        self._imgview._image.updateTransform(vpRect, 0)
        self._imgview.resetView()
        self._imgview.updateScene()