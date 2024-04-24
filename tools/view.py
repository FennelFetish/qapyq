from PySide6.QtCore import QRectF, Qt
from .tool import Tool


class ViewTool(Tool):
    def __init__(self):
        super().__init__()

    def getDropRects(self):
        return [QRectF(0, 0, 1, 1)]
    
    def onDrop(self, event, zoneIndex):
        firstUrl = event.mimeData().urls()[0]
        self._imgview.loadImage(firstUrl.toLocalFile())

    def onKeyPress(self, event):
        file = ""
        match event.key():
            case Qt.Key_Left:
                file = self._imgview._filelist.getPrevFile()
            case Qt.Key_Right:
                file = self._imgview._filelist.getNextFile()
            case Qt.Key_Up:
                file = self._imgview._filelist.getNextFolder()
            case Qt.Key_Down:
                file = self._imgview._filelist.getPrevFolder()

        if file:
            self._imgview.loadImage(file, False)