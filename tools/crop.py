from PySide6.QtGui import QBrush, QColor, QPen, QPainterPath
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsItem
from .view import ViewTool
from PySide6.QtCore import Qt, QRectF, QPointF, QBuffer
from PIL import Image
import io


def createPen(r, g, b):
    pen = QPen( QColor(r, g, b, 180) )
    pen.setDashPattern([5,5])
    return pen


class CropTool(ViewTool):
    PEN_DOWNSCALE = createPen(0, 255, 255)
    PEN_UPSCALE   = createPen(255, 0, 255)

    def __init__(self):
        super().__init__()

        self._targetWidth = 512
        self._targetHeight = 768

        self._cropHeight = 100.0
        self._cropAspectRatio = self._targetWidth / self._targetHeight

        self._cropRect = QGraphicsRectItem(-50, -50, 100, 100)
        self._cropRect.setPen(self.PEN_UPSCALE)
        self._cropRect.setVisible(False)

        self._mask = MaskRect()
        self._mask.setBrush( QBrush(QColor(0, 0, 0, 100)))

    def updateCropSelection(self, mouseCoords: QPointF):
        img = self._imgview._image
        rect = QRectF(0, 0, img.pixmap().width(), img.pixmap().height())
        rect = img.mapRectToParent(rect)
        rect = self._imgview.mapFromScene(rect).boundingRect()
        
        h = (self._cropHeight * self._imgview.viewport().height() * self._imgview._zoom) / img.pixmap().height()
        w = h * self._cropAspectRatio
        x = mouseCoords.x() - w/2
        y = mouseCoords.y() - h/2
        
        x = max(x, rect.x())
        y = max(y, rect.y())

        imgMax = rect.bottomRight()
        x = min(x, imgMax.x()-w)
        y = min(y, imgMax.y()-h)
        
        if w > rect.width():
            x += (w-rect.width()) / 2
        if h > rect.height():
            y += (h-rect.height()) / 2

        self._cropRect.setRect(x, y, w, h)

        self._mask.clipPath.clear()
        self._mask.clipPath.addRect(self._imgview.viewport().rect())
        self._mask.clipPath.addRect(self._cropRect.rect())

        wCovered = w * img.pixmap().width() / rect.width()
        if wCovered < self._targetWidth:
            self._cropRect.setPen(self.PEN_UPSCALE)
        else:
            self._cropRect.setPen(self.PEN_DOWNSCALE)

        self._imgview.scene().update()

    def toPILImage(self, qimg):
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        qimg.save(buffer, "PNG")
        return Image.open(io.BytesIO(buffer.data()))

    def exportImage(self, rect):
        # Crop and convert
        img = self._imgview._image.pixmap()
        img = self.toPILImage( img.copy(rect.toRect()) )

        # if img.width < self._targetWidth:
        #     print("upscaling")
        # else:
        #     print("downscaling")

        # Use reducing_gap=3 when downscaling?
        img = img.resize((self._targetWidth, self._targetHeight), Image.Resampling.LANCZOS)

        path = "/mnt/data/Pictures/SDOut/bla_pil.png"
        img.save(path)
        print("Exported cropped image to", path)

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

    def onMousePress(self, event) -> bool:
        if (event.modifiers() & Qt.ControlModifier) == Qt.ControlModifier:
            return False

        rect = self._cropRect.rect()
        rect = self._imgview.mapToScene(rect.toRect()).boundingRect()
        rect = self._imgview._image.mapRectFromParent(rect)
        self.exportImage(rect)
        return True

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