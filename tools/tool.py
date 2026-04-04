from enum import IntEnum
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QToolBar
from ui.dropview import DropZone
from ui.imgview import ImgView
from ui.tab import ImgTab


class MediaEvent(IntEnum):
    SkipOutsideSegment      = 0
    PlaybackSpeedChanged    = 1


class Tool:
    def __init__(self, tab: ImgTab):
        self.tab: ImgTab = tab
        self._imgview: ImgView = None
        self._shortcuts: list[QShortcut] = []

    def addShortcuts(self, *shortcuts: QShortcut):
        for shortcut in shortcuts:
            shortcut.setEnabled(False)
        self._shortcuts.extend(shortcuts)

    def getToolbar(self) -> QToolBar | None:
        return None


    def onEnabled(self, imgview: ImgView):
        self._imgview = imgview
        imgview.clearDropZones()
        for rect in self.getDropRects():
            imgview.addDropZone(DropZone(rect))

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

    def onResize(self, event):
        pass

    def onFullscreen(self, active):
        pass


    def getDropRects(self):
        return []

    def onDrop(self, event, zoneIndex):
        pass


    def onMouseEnter(self, event):
        pass

    def onMouseMove(self, event):
        pass

    def onMouseLeave(self, event):
        pass

    def onMousePress(self, event) -> bool:
        return False

    def onMouseRelease(self, event):
        pass

    def onMouseWheel(self, event) -> bool:
        return False

    def onTablet(self, event) -> bool:
        return False


    def onKeyPress(self, event):
        pass


    def onGalleryRightClick(self, file):
        pass

    def onMediaEvent(self, event: MediaEvent):
        pass
