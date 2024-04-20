import io, os
from PIL import Image  # https://pillow.readthedocs.io/en/stable/reference/Image.html
from PySide6.QtCore import QBuffer, QPointF, QRect, QRectF, Qt, Slot
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QPolygonF, QTransform
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
        self._mask.setBrush( QBrush(QColor(0, 0, 0, 100)) )

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
        h = (self._cropHeight * self._imgview.viewport().height() * self._imgview.zoom) / img.pixmap().height()
        w = h * self._cropAspectRatio

        # Constrain crop size
        if w > rect.width():
            w = rect.width()
            h = w / self._cropAspectRatio
            self._cropHeight = (h * img.pixmap().height()) / (self._imgview.viewport().height() * self._imgview.zoom)
        if h > rect.height():
            h = rect.height()
            w = h * self._cropAspectRatio
            self._cropHeight = (h * img.pixmap().height()) / (self._imgview.viewport().height() * self._imgview.zoom)

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
        self._toolbar.setSelectionSize(self._cropHeight * self._cropAspectRatio, self._cropHeight)


    def toPILImage(self, qimg):
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        qimg.save(buffer, "PNG")
        return Image.open(io.BytesIO(buffer.data()))

    def getExportPath(self):
        filename = os.path.basename(self._imgview.image.filepath)
        filename = os.path.splitext(filename)[0] + f"_{self._targetWidth}x{self._targetHeight}"
        prefix = "/mnt/data/Pictures/SDOut/" + filename

        path = prefix + ".png"
        suffix = 1
        while os.path.exists(path):
            path = prefix + f"_{suffix:02}.png"
            suffix += 1
        
        return path

    def calcSourceBox(self, poly: QPolygonF, rect: QRectF) -> QRectF:
        # Calc points inside cropped image
        pivot = rect.center()
        p0 = poly.at(0) - pivot
        p1 = poly.at(1) - pivot
        p2 = poly.at(2) - pivot
        p3 = poly.at(3) - pivot
        poly = QPolygonF([p0, p1, p2, p3])
        #print("polyRel:", polyRel)

        rotMatrix = QTransform().rotate(self._imgview.rotation)
        polyRot = rotMatrix.map(poly) # is now axis oriented

        rectCenter = rect.center()
        rect = rect.translated(-rectCenter.x(), -rectCenter.y())
        rectRot = rotMatrix.mapRect(rect)
        rectRot.translate(rectCenter.x(), rectCenter.y())

        origin = rectRot.topLeft()
        p0 = polyRot.at(0) + pivot - origin
        p1 = polyRot.at(1) + pivot - origin
        p2 = polyRot.at(2) + pivot - origin
        p3 = polyRot.at(3) + pivot - origin
        polyRot = QPolygonF([p0, p1, p2, p3])
        #print("poly:", polyRot)
        return polyRot.boundingRect()

    def exportImage(self, poly: QPolygonF):
        # TODO: Adjust rect to rotation -> no? it should already include everything
        # The selected region is inside the mapped boundingRect
        # Region to be exported is a rectangle inside the rotated image
        # Need the selection points relative to the boundingRect

        print("===== exportImage =====")
        #print("poly:", poly)
        rect = poly.boundingRect()
        #print("rect:", rect)

        srcRect = self.calcSourceBox(poly, rect)

        # Crop and convert
        img = self._imgview.image.pixmap()
        img = self.toPILImage( img.copy(rect.toRect()) )
        
        path = self.getExportPath()
        if abs(self._imgview.rotation) > 0.01:
            img = img.rotate(-self._imgview.rotation, Image.Resampling.BICUBIC, expand=1, fillcolor=(0,0,0))
            img.save(path + "-rot.png")

        srcBoxX = max(0, srcRect.x())
        srcBoxY = max(0, srcRect.y())
        srcBoxW = min(img.width, srcRect.width())
        srcBoxH = min(img.height, srcRect.height())
        srcBox = (srcBoxX, srcBoxY, srcBoxW, srcBoxH)
        print("srcBox:", srcBox)

        img = img.resize(size=(self._targetWidth, self._targetHeight), resample=Image.Resampling.LANCZOS, box=srcBox)

        # if img.width < self._targetWidth:
        #     # Upscaling
        #     img = img.resize((self._targetWidth, self._targetHeight), Image.Resampling.LANCZOS, srcBox)
        # else:
        #     # Downscaling: Use reducing_gap=3 when downscaling?
        #     img = img.resize((self._targetWidth, self._targetHeight), Image.Resampling.LANCZOS, srcBox)

        #path = self.getExportPath()
        img.save(path)
        print("Exported cropped image to", path)


    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        self._mask.setRect(self._imgview.viewport().rect())
        imgview._guiScene.addItem(self._mask)
        imgview._guiScene.addItem(self._cropRect)

        imgview.rotation = self._toolbar.slideRot.value() / 10
        imgview.updateImageTransform()

    def onDisabled(self, imgview):
        super().onDisabled(imgview)
        imgview._guiScene.removeItem(self._mask)
        imgview._guiScene.removeItem(self._cropRect)

        imgview.rotation = 0.0
        imgview.updateImageTransform()


    def onSceneUpdate(self):
        self.updateCropSelection(self._cropRect.rect().center())

    def onResetView(self):
        self._toolbar.slideRot.setValue(self._imgview.rotation)

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
        poly = self._imgview.mapToScene(rect.toRect())
        poly = self._imgview.image.mapFromParent(poly)
        self.exportImage(poly)
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

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self._buildTargetSize())
        layout.addWidget(self._buildSelectionSize())
        layout.addWidget(self._buildRotation())

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        act = self.addWidget(widget)

        self.updateSize()

    def _buildTargetSize(self):
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
        layout.addRow("W:", self.spinW)
        layout.addRow("H:", self.spinH)
        layout.addRow(btnSwap)

        group = QtWidgets.QGroupBox("Target Size")
        group.setLayout(layout)
        return group

    def _buildSelectionSize(self):
        self.lblW = QtWidgets.QLabel("0 px")
        self.lblH = QtWidgets.QLabel("0 px")
        self.lblScale = QtWidgets.QLabel("1.0")

        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addRow("W:", self.lblW)
        layout.addRow("H:", self.lblH)
        layout.addRow(self.lblScale)

        group = QtWidgets.QGroupBox("Selection")
        group.setLayout(layout)
        return group

    def _buildRotation(self):
        self.slideRot = QtWidgets.QSlider(Qt.Horizontal)
        self.slideRot.setRange(-1, 3600)
        self.slideRot.setTickPosition(QtWidgets.QSlider.TicksAbove)
        self.slideRot.setTickInterval(900)
        self.slideRot.setSingleStep(10)
        self.slideRot.setPageStep(50)
        self.slideRot.setValue(0)
        self.slideRot.valueChanged.connect(self.updateRotationFromSlider)

        self.spinRot = PrecisionSpinBox()
        self.spinRot.setRange(-3600, 3600)
        self.spinRot.setSingleStep(1)
        self.spinRot.setValue(0)
        self.spinRot.valueChanged.connect(self.updateRotationFromSpinner)

        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addRow(self.slideRot)
        layout.addRow("Deg:", self.spinRot)

        group = QtWidgets.QGroupBox("Rotation")
        group.setLayout(layout)
        return group

    @Slot()
    def updateSize(self):
        self._cropTool.setTargetSize(self.spinW.value(), self.spinH.value())
    
    @Slot()
    def swapSize(self):
        w = self.spinW.value()
        self.spinW.setValue(self.spinH.value())
        self.spinH.setValue(w)
        self.updateSize()
    
    @Slot()
    def updateRotationFromSlider(self, rot: int):
        self.spinRot.setValue(rot)
        self._cropTool._imgview.rotation = rot / 10
        self._cropTool._imgview.updateImageTransform()

    @Slot()
    def updateRotationFromSpinner(self, rot: int):
        rot = rot % 3600
        self.spinRot.setValue(rot)
        self.slideRot.setValue(rot)
        
        self._cropTool._imgview.rotation = rot / 10
        self._cropTool._imgview.updateImageTransform()

    def setSelectionSize(self, w, h):
        self.lblW.setText(f"{w:.1f} px")
        self.lblH.setText(f"{h:.1f} px")

        scale = self.spinH.value() / h
        if scale >= 1.0:
            self.lblScale.setStyleSheet("QLabel { color: #ff3030; }")
            self.lblScale.setText(f"▲   {scale:.3f}")
        else:
            self.lblScale.setStyleSheet("QLabel { color: #30ff30; }")
            self.lblScale.setText(f"▼   {scale:.3f}")



class PrecisionSpinBox(QtWidgets.QSpinBox):
    PRECISION = 10

    def textFromValue(self, val: int) -> str:
        return f"{val / self.PRECISION:.1f}"
    
    def valueFromText(self, text: str) -> int:
        val = float(text) * self.PRECISION
        return round(val)
