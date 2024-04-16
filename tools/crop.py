from PySide6.QtGui import QBrush, QColor, QPen, QPainterPath
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsItem
from .view import ViewTool
from PySide6.QtCore import Qt, QRectF, QPointF

class CropTool(ViewTool):
    def __init__(self):
        super().__init__()

        pen = QPen( QColor(255, 0, 255, 180) )
        pen.setDashPattern([5,12])

        self._cropHeight = 100.0
        self._cropAspectRatio = 2/3

        self._cropRect = QGraphicsRectItem(-50, -50, 100, 100)
        self._cropRect.setPen(pen)
        self._cropRect.setVisible(False)

        self._mask = MaskRect()
        self._mask.setBrush( QBrush(QColor(0, 0, 0, 100)))

    def updateCropSelection(self, mouseCoords: QPointF):
        rect = QRectF(0, 0, self._imgview._image.pixmap().width(), self._imgview._image.pixmap().height())
        rect = self._imgview._image.mapRectToParent(rect)
        imgMin = self._imgview.mapFromScene(rect.topLeft())
        imgMax = self._imgview.mapFromScene(rect.bottomRight())
        imgW = imgMax.x() - imgMin.x()
        imgH = imgMax.y() - imgMin.y()

        h = (self._cropHeight * self._imgview.viewport().height() * self._imgview._zoom) / self._imgview._image.pixmap().height()
        w = h * self._cropAspectRatio
        x = mouseCoords.x() - w/2
        y = mouseCoords.y() - h/2
        
        # mxPerc = (mouseCoords.x()-imgMin.x()) / imgW
        # myPerc = (mouseCoords.y()-imgMin.y()) / imgH

        x = max(x, imgMin.x())
        y = max(y, imgMin.y())

        x = min(x, imgMax.x()-w)
        y = min(y, imgMax.y()-h)
        
        if w > imgW:
            x += (w-imgW) / 2
        if h > imgH:
            y += (h-imgH) / 2

        self._cropRect.setRect(x, y, w, h)

        self._mask.clipPath.clear()
        self._mask.clipPath.addRect(self._imgview.viewport().rect())
        self._mask.clipPath.addRect(self._cropRect.rect())

        self._imgview.scene().update()

    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        self._mask.setRect(self._imgview.viewport().rect())
        imgview._guiScene.addItem(self._mask)
        imgview._guiScene.addItem(self._cropRect)

    def onDisabled(self, imgview):
        super().onDisabled(imgview)
        imgview._guiScene.removeItem(self._mask)
        imgview._guiScene.removeItem(self._cropRect)

    def onSceneUpdate(self):
        self.updateCropSelection(self._cropRect.rect().center())

    def onResize(self, event):
        self._mask.setRect(self._imgview.viewport().rect())

    def onMouseEnter(self, event):
        self._cropRect.setVisible(True)
        self._mask.setVisible(True)

    def onMouseMove(self, event):
        self.updateCropSelection(event.position())

    def onMouseLeave(self, event):
        self._cropRect.setVisible(False)
        self._mask.setVisible(False)
        self._imgview.scene().update()

    def onMouseWheel(self, event) -> bool:
        if (event.modifiers() & Qt.ControlModifier) == Qt.ControlModifier:
            return False
        change = 1 if (event.modifiers() & Qt.ShiftModifier) == Qt.ShiftModifier else 10

        wheelSteps = event.angleDelta().y() / 120.0 # 8*15° standard
        self._cropHeight += wheelSteps * change
        self._cropHeight = max(self._cropHeight, 1)
        self.updateCropSelection(event.position())
        return True


class MaskRect(QGraphicsRectItem):
    def __init__(self):
        super().__init__(None)
        self.setFlag(QGraphicsItem.ItemClipsToShape, True)
        self.clipPath = QPainterPath()

    def shape(self) -> QPainterPath:
        return self.clipPath