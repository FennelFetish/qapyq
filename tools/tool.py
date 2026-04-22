from enum import IntEnum
from PySide6 import QtGui
from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QToolBar
from ui.dropview import DropRect
from ui.imgview import ImgView
from ui.tab import ImgTab


class MediaEvent(IntEnum):
    SkipOutsideSegment      = 0
    PlaybackSpeedChanged    = 1


class Tool:
    def __init__(self, tab: ImgTab):
        self.tab: ImgTab = tab
        self._imgview: ImgView = None
        self._shortcuts: list[QtGui.QShortcut] = []

    def addShortcuts(self, *shortcuts: QtGui.QShortcut):
        for shortcut in shortcuts:
            shortcut.setEnabled(False)
        self._shortcuts.extend(shortcuts)

    def getToolbar(self) -> QToolBar | None:
        return None


    def onEnabled(self, imgview: ImgView):
        self._imgview = imgview
        imgview.clearDropZones()
        for rect in self.getDropRects():
            imgview.addDropZone(rect)

        for shortcut in self._shortcuts:
            shortcut.setEnabled(True)

        imgview.setCursor(Qt.CursorShape.ArrowCursor)

    def onDisabled(self, imgview: ImgView):
        self._imgview = None

        for shortcut in self._shortcuts:
            shortcut.setEnabled(False)

    def onTabActive(self, active: bool):
        pass


    def onSceneUpdate(self):
        pass

    def onResetView(self):
        pass

    def onResize(self, event: QtGui.QResizeEvent):
        pass

    def onFullscreen(self, active: bool):
        pass


    def getDropRects(self) -> list[DropRect]:
        return []

    def onDrop(self, event: QtGui.QDropEvent, zoneIndex: int):
        pass


    def onMouseEnter(self, event: QtGui.QSinglePointEvent):
        pass

    def onMouseMove(self, event: QtGui.QMouseEvent):
        pass

    def onMouseLeave(self, event: QEvent):
        pass

    def onMousePress(self, event: QtGui.QMouseEvent) -> bool:
        return False

    def onMouseRelease(self, event: QtGui.QMouseEvent):
        pass

    def onMouseWheel(self, event: QtGui.QWheelEvent) -> bool:
        return False

    def onTablet(self, event: QtGui.QTabletEvent) -> bool:
        return False


    def onKeyPress(self, event: QtGui.QKeyEvent):
        pass


    def onGalleryRightClick(self, file: str):
        pass

    def onMediaEvent(self, event: MediaEvent):
        pass
