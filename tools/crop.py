import io
from PIL import Image  # https://pillow.readthedocs.io/en/stable/reference/Image.html
from PySide6.QtCore import QBuffer, QPointF, QRect, QRectF, Qt, Slot
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem
from PySide6 import QtWidgets
from .view import ViewTool


def createPen(r, g, b):
    pen = QPen( QColor(r, g, b, 180) )
    pen.setDashPattern([5,5])
    return pen


class CropTool(ViewTool):
    PEN_DOWNSCALE = createPen(0, 255, 255)
    PEN_UPSCALE   = createPen(255, 0, 255)

    BUTTON_CROP   = Qt.LeftButton

    def __init__(self):
        super().__init__()

        self._targetWidth = 512
        self._targetHeight = 512

        self._cropHeight = 100.0
        self._cropAspectRatio = self._targetWidth / self._targetHeight

        self._cropRect = QGraphicsRectItem(-50, -50, 100, 100)
        self._cropRect.setPen(self.PEN_UPSCALE)
        self._cropRect.setVisible(False)

        self._mask = MaskRect()
        self._mask.setBrush( QBrush(QColor(0, 0, 0, 100)))

        self._toolbar = CropToolBar(self)

    def getToolbar(self):
        return self._toolbar

    def setTargetSize(self, width, height):
        self._targetWidth = round(width)
        self._targetHeight = round(height)
        self._cropAspectRatio = self._targetWidth / self._targetHeight
        #self.updateCropSelection(self._cropRect.rect().center())

    def updateCropSelection(self, mouseCoords: QPointF):
        # Calculate image bounds in viewport coordinates
        img = self._imgview.image
        rect = QRectF(0, 0, img.pixmap().width(), img.pixmap().height())
        rect = img.mapRectToParent(rect)
        rect = self._imgview.mapFromScene(rect).boundingRect()
        
        # Calculate crop size in viewport coordinates
        h = (self._cropHeight * self._imgview.viewport().height() * self._imgview._zoom) / img.pixmap().height()
        w = h * self._cropAspectRatio

        # Constrain crop size
        if w > rect.width():
            w = rect.width()
            h = w / self._cropAspectRatio
            self._cropHeight = (h * img.pixmap().height()) / (self._imgview.viewport().height() * self._imgview._zoom)
        if h > rect.height():
            h = rect.height()
            w = h * self._cropAspectRatio
            self._cropHeight = (h * img.pixmap().height()) / (self._imgview.viewport().height() * self._imgview._zoom)

        # Crop position
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

        # Change selection color depending on crop size
        wSelected = w * img.pixmap().width() / rect.width()
        pen = self.PEN_UPSCALE if wSelected < self._targetWidth else self.PEN_DOWNSCALE
        self._cropRect.setPen(pen)

        self._imgview.scene().update()

    def toPILImage(self, qimg):
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        qimg.save(buffer, "PNG")
        return Image.open(io.BytesIO(buffer.data()))

    def exportImage(self, rect: QRect):
        # Crop and convert
        img = self._imgview.image.pixmap()
        img = self.toPILImage( img.copy(rect) )

        if img.width < self._targetWidth:
            # Upscaling
            img = img.resize((self._targetWidth, self._targetHeight), Image.Resampling.LANCZOS)
        else:
            # Downscaling: Use reducing_gap=3 when downscaling?
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
        if event.button() != self.BUTTON_CROP:
            return False
        if (event.modifiers() & Qt.ControlModifier) == Qt.ControlModifier:
            return False

        rect = self._cropRect.rect()
        rect = self._imgview.mapToScene(rect.toRect()).boundingRect()
        rect = self._imgview.image.mapRectFromParent(rect)
        self.exportImage(rect.toRect())
        return True

    def onMouseWheel(self, event) -> bool:
        if (event.modifiers() & Qt.ControlModifier) == Qt.ControlModifier:
            return False
        
        change = self._imgview.image.pixmap().height() * 0.03
        if (event.modifiers() & Qt.ShiftModifier) == Qt.ShiftModifier:
            change = 1

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



class CropToolBar(QtWidgets.QToolBar):
    def __init__(self, cropTool):
        super().__init__("Crop")
        self._cropTool = cropTool

        self.spinW = QtWidgets.QSpinBox()
        self.spinW.setRange(1, 16384)
        self.spinW.setSingleStep(64)
        self.spinW.setValue(512)
        self.spinW.valueChanged.connect(self.updateSize)

        self.spinH = QtWidgets.QSpinBox()
        self.spinH.setRange(1, 16384)
        self.spinH.setSingleStep(64)
        self.spinH.setValue(512)
        self.spinH.valueChanged.connect(self.updateSize)

        btnSwap  = QtWidgets.QPushButton("Swap")
        btnSwap.clicked.connect(self.swapSize)

        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addRow(QtWidgets.QLabel("Target Size:"))
        layout.addRow("W:", self.spinW)
        layout.addRow("H:", self.spinH)
        layout.addRow(btnSwap)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        act = self.addWidget(widget)

        self.updateSize()
    
    @Slot()
    def updateSize(self):
        self._cropTool.setTargetSize(self.spinW.value(), self.spinH.value())
    
    @Slot()
    def swapSize(self):
        w = self.spinW.value()
        self.spinW.setValue(self.spinH.value())
        self.spinH.setValue(w)
        self.updateSize()