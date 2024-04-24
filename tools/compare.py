from PySide6.QtCore import QRectF
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsLineItem
from imgview import ClipImgItem
from .tool import Tool


class CompareTool(Tool):
    def __init__(self):
        super().__init__()
        self._image = ClipImgItem()

        self._dividerLine = QGraphicsLineItem(0, 0, 0, 0)
        self._dividerLine.setZValue(1000)
        self._dividerLine.setPen( QPen(QColor(180, 180, 180, 140)) )
        self._dividerLine.setVisible(False)

    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        imgview.scene().addItem(self._image)
        imgview._guiScene.addItem(self._dividerLine)

    def onDisabled(self, imgview):
        super().onDisabled(imgview)
        imgview.scene().removeItem(self._image)
        imgview._guiScene.removeItem(self._dividerLine)


    def getDropRects(self):
        return [QRectF(0, 0, 0.5, 1), QRectF(0.5, 0, 1, 1)]

    def onDrop(self, event, zoneIndex):
        img = self._image if zoneIndex>0 else self._imgview.image

        firstUrl = event.mimeData().urls()[0]
        img.loadImage(firstUrl.toLocalFile())
        img.updateTransform(self._imgview.viewport().rect(), self._imgview.rotation)
        
        if zoneIndex == 0:
            self._imgview.resetView()
        else:
            img.setClipWidth(0)

        self._imgview.updateScene()

    def onResize(self, event):
        rect = QRectF(0, 0, event.size().width(), event.size().height())
        self._image.updateTransform(rect, self._imgview.rotation)


    # ===== Divider Line =====
    def onMouseEnter(self, event):
        if not self._image.pixmap().isNull():
            self._dividerLine.setVisible(True)

    def onMouseMove(self, event):
        imgpos = self._imgview.mapToScene(event.position().toPoint())
        imgpos = self._image.mapFromParent(imgpos)
        self._image.setClipWidth(imgpos.x())

        x = event.position().x()
        h = self._imgview.viewport().height()
        self._dividerLine.setLine(x, 0, x, h)

    def onMouseLeave(self, event):
        self._image.setClipWidth(0)
        self._dividerLine.setVisible(False)

