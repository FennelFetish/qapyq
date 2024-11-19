from PySide6.QtCore import QRectF, Qt, QPointF
from math import floor
from .tool import Tool


class ViewTool(Tool):
    def __init__(self, tab):
        super().__init__(tab)

    def mapPosToImage(self, posF: QPointF) -> QPointF:
        scenePos = self._imgview.mapToScene(posF.toPoint())
        return self._imgview.image.mapFromParent(scenePos)

    def mapPosToImageInt(self, posF: QPointF) -> tuple[int, int]:
        imgpos = self.mapPosToImage(posF)
        return (floor(imgpos.x()), floor(imgpos.y()))


    def onSceneUpdate(self):
        imgSize = self._imgview.image.pixmap().size()
        self.tab.statusBar().setImageSize(imgSize.width(), imgSize.height())

    def getDropRects(self):
        return [QRectF(0, 0, 1, 1)]
    
    def onDrop(self, event, zoneIndex):
        paths = (url.toLocalFile() for url in event.mimeData().urls())
        
        # SHIFT pressed -> Append
        if (event.modifiers() & Qt.ShiftModifier) == Qt.ShiftModifier:
            self._imgview.filelist.loadAppend(paths)
        else:
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

    def onMouseMove(self, event):
        x, y = self.mapPosToImageInt(event.position())
        self.tab.statusBar().setMouseCoords(x, y)