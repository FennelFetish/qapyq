from ui.dropview import DropZone
from ui.imgview import ImgView


class Tool:
    def __init__(self, tab):
        self.tab = tab

    def getToolbar(self):
        return None

    def onEnabled(self, imgview: ImgView):
        self._imgview = imgview
        imgview.clearDropZones()
        for rect in self.getDropRects():
            imgview.addDropZone( DropZone(rect))

    def onDisabled(self, imgview: ImgView):
        self._imgview = None


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

    def onMouseWheel(self, event) -> bool:
        return False


    def onKeyPress(self, event):
        pass

    
    def onGalleryRightClick(self, file):
        pass