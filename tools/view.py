from PySide6.QtCore import QRectF
from .tool import Tool


class ViewTool(Tool):
    def __init__(self):
        super().__init__()

    def getDropRects(self):
        return [QRectF(0, 0, 1, 1)]
    
    def onDrop(self, event, zoneIndex):
        firstUrl = event.mimeData().urls()[0]
        self._imgview.loadImage(firstUrl.toLocalFile())
