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

    def mapPosFromImage(self, posF: QPointF):
        scenePos = self._imgview.image.mapToParent(posF)
        return self._imgview.mapFromScene(scenePos)


    def onSceneUpdate(self):
        self.tab.statusBar().setImageInfo(self._imgview.image.pixmap())

    def getDropRects(self):
        return [QRectF(0, 0, 1, 1)]

    def onDrop(self, event, zoneIndex):
        paths = (url.toLocalFile() for url in event.mimeData().urls())

        # SHIFT pressed -> Append
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.tab.filelist.loadAppend(paths)
        else:
            self.tab.filelist.loadAll(paths)

    def onMousePress(self, event) -> bool:
        filelist = self.tab.filelist
        match event.button():
            case Qt.MouseButton.BackButton:
                filelist.setPrevFile()
                return True
            case Qt.MouseButton.ForwardButton:
                filelist.setNextFile()
                return True
        return False

    def onKeyPress(self, event):
        filelist = self.tab.filelist
        match event.key():
            case Qt.Key.Key_Left:
                filelist.setPrevFile()
            case Qt.Key.Key_Right:
                filelist.setNextFile()
            case Qt.Key.Key_Up:
                filelist.setNextFolder()
            case Qt.Key.Key_Down:
                filelist.setPrevFolder()

    def onMouseMove(self, event):
        x, y = self.mapPosToImageInt(event.position())
        self.tab.statusBar().setMouseCoords(x, y)