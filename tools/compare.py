from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPen, QPainterPath
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsItem
from ui.imgview import ImgItem
from .view import ViewTool


class CompareTool(ViewTool):
    def __init__(self, tab):
        super().__init__(tab)
        self._image = ClipImgItem()
        self.compareFile = ""

        self._dividerLine = QGraphicsLineItem(0, 0, 0, 0)
        self._dividerLine.setZValue(1000)
        self._dividerLine.setPen( QPen(QColor(180, 180, 180, 140)) )
        self._dividerLine.setVisible(False)

    def loadCompareImage(self, path):
        self.compareFile = path
        self._image.loadImage(path)
        self._image.updateTransform(self._imgview.viewport().rect(), self._imgview.rotation)
        self._image.setClipWidth(0)
        self._imgview.updateScene()

    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        imgview.scene().addItem(self._image)
        imgview._guiScene.addItem(self._dividerLine)
        self.onResize()

    def onDisabled(self, imgview):
        super().onDisabled(imgview)
        imgview.scene().removeItem(self._image)
        imgview._guiScene.removeItem(self._dividerLine)

    def onSceneUpdate(self):
        super().onSceneUpdate()
        self._imgview.updateImageSmoothness(self._image)


    def getDropRects(self):
        return [QRectF(0, 0, 0.5, 1), QRectF(0.5, 0, 1, 1)]

    def onDrop(self, event, zoneIndex):
        if zoneIndex == 0:
            super().onDrop(event, zoneIndex)
        else:
            path = event.mimeData().urls()[0].toLocalFile()
            self.loadCompareImage(path)

    def onGalleryRightClick(self, file):
        self.loadCompareImage(file)

    def onResize(self, event=None):
        self._image.updateTransform(self._imgview.viewport().rect(), self._imgview.rotation)


    # ===== Divider Line =====
    def onMouseEnter(self, event):
        if not self._image.pixmap().isNull():
            self._dividerLine.setVisible(True)

    def onMouseMove(self, event):
        super().onMouseMove(event)
        scenePos = self._imgview.mapToScene(event.position().toPoint())
        imgPos = self._image.mapFromParent(scenePos)
        self._image.setClipWidth(imgPos.x())

        x = event.position().x()
        h = self._imgview.viewport().height()
        self._dividerLine.setLine(x, 0, x, h)

    def onMouseLeave(self, event):
        self._image.setClipEmpty()
        self._dividerLine.setVisible(False)



class ClipImgItem(ImgItem):
    def __init__(self):
        super().__init__()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsToShape, True)
        self._clipPath = QPainterPath()

    def setClipWidth(self, x):
        w = self.pixmap().width()
        h = self.pixmap().height()
        self._clipPath.clear()
        self._clipPath.addRect(x, 0, w-x+1, h)
        self.update()
    
    def setClipEmpty(self):
        self._clipPath.clear()
        self.update()

    def shape(self) -> QPainterPath:
        return self._clipPath
