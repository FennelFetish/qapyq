from PySide6.QtCore import QRectF, Qt
from .tool import Tool


class ViewTool(Tool):
    def __init__(self):
        super().__init__()

    def getDropRects(self):
        return [QRectF(0, 0, 1, 1)]
    
    def onDrop(self, event, zoneIndex):
        paths = (url.toLocalFile() for url in event.mimeData().urls())
        self._imgview.filelist.loadAll(paths)

    def onMousePress(self, event) -> bool:
        match event.button():
            case Qt.BackButton:
                self._imgview.filelist.setPrevFile()
                return True
            case Qt.ForwardButton:
                self._imgview.filelist.setNextFile()
                return True
        return False

    def onKeyPress(self, event):
        match event.key():
            case Qt.Key_Left:
                self._imgview.filelist.setPrevFile()
            case Qt.Key_Right:
                self._imgview.filelist.setNextFile()
            case Qt.Key_Up:
                self._imgview.filelist.setNextFolder()
            case Qt.Key_Down:
                self._imgview.filelist.setPrevFolder()
