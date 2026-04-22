from typing_extensions import override
from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QPolygon
from math import floor
from ui.dropview import DropRect
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

    def mapImageToViewport(self) -> QPolygon:
        imgRect = self._imgview.image.boundingRect()
        imgPoly = self._imgview.image.mapToParent(imgRect)
        return self._imgview.mapFromScene(imgPoly)


    @override
    def onSceneUpdate(self):
        item = self._imgview.image
        size = item.mediaSize()
        if size.isValid():
            w, h = size.toTuple()
            alpha, fps, frames = item.mediaMetadata()
        else:
            w = h   = -1
            alpha   = False
            fps     = -1
            frames  = -1

        self.tab.statusBar().setMediaInfo(w, h, alpha, fps, frames)


    @override
    def getDropRects(self) -> list[DropRect]:
        return [
            DropRect("Open Files",          0.00, 0.00, 1.00, 0.85),
            DropRect("Append Files",        0.00, 0.85, 0.50, 0.15),
            DropRect("Open in New Tab",     0.50, 0.85, 0.50, 0.15),
        ]

    @override
    def onDrop(self, event, zoneIndex):
        match zoneIndex:
            case 0:
                append = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                newTab = False
            case 1:
                append = True
                newTab = False
            case 2 | _:
                append = False
                newTab = True

        # Move this out of the event handler
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        QTimer.singleShot(0, lambda: self._loadFiles(paths, append, newTab))

    def _loadFiles(self, paths: list[str], append: bool, newTab: bool):
        tab = self.tab.mainWindow.addTab() if newTab else self.tab
        if append:
            tab.filelist.loadAppend(paths)
        else:
            tab.filelist.loadAll(paths)


    @override
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

    @override
    def onKeyPress(self, event):
        filelist = self.tab.filelist
        match event.key():
            case Qt.Key.Key_Left:
                filelist.setPrevFile()
            case Qt.Key.Key_Right:
                filelist.setNextFile()
            case Qt.Key.Key_Up:
                filelist.setPrevFolder()
            case Qt.Key.Key_Down:
                filelist.setNextFolder()
            case Qt.Key.Key_0:
                self._imgview.resetView()
                self._imgview.updateView()

    @override
    def onMouseMove(self, event):
        x, y = self.mapPosToImageInt(event.position())
        self.tab.statusBar().setMouseCoords(x, y)
