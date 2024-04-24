import os
import cv2 as cv
import numpy as np
from PySide6 import QtWidgets
from PySide6.QtCore import QBuffer, QPointF, QRectF, QRect, Qt, Slot
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QPolygonF, QVector2D, QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem
from .view import ViewTool

# TODO: Bug when cropping parts outside of image. Fix: Don't allow selection to go beyond image


INTERP_MODES = {
    "Nearest": cv.INTER_NEAREST,
    "Linear":  cv.INTER_LINEAR,
    "Cubic":   cv.INTER_CUBIC,
    "Area":    cv.INTER_AREA,
    "Lanczos": cv.INTER_LANCZOS4
}

SAVE_PARAMS = {
    "PNG":  [cv.IMWRITE_PNG_COMPRESSION, 9],
    "JPG":  [cv.IMWRITE_JPEG_QUALITY, 95],
    "WEBP": [cv.IMWRITE_WEBP_QUALITY, 95]
}


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

    def updateCropAligned(self, mouseCoords: QPointF, poly: QPolygonF):
        rect = poly.boundingRect()
        imgHeight = self._imgview.image.pixmap().height()

        # Calculate crop size in viewport coordinates
        h = (self._cropHeight * self._imgview.viewport().height() * self._imgview.zoom) / imgHeight
        w = h * self._cropAspectRatio

        # Constrain crop size
        if w > rect.width():
            w = rect.width()
            h = w / self._cropAspectRatio
            self._cropHeight = (h * imgHeight) / (self._imgview.viewport().height() * self._imgview.zoom)
        if h > rect.height():
            h = rect.height()
            w = h * self._cropAspectRatio
            self._cropHeight = (h * imgHeight) / (self._imgview.viewport().height() * self._imgview.zoom)

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

        return (x, y, w, h)

    def updateCropRotated(self, mouseCoords: QPointF, poly: QPolygonF):
        # Calculate crop size in viewport coordinates
        h = (self._cropHeight * self._imgview.viewport().height() * self._imgview.zoom) / self._imgview.image.pixmap().height()
        w = h * self._cropAspectRatio

        # ----1) Calculate distance of selection corners to each side of image-poly. Store as (distance, corner-idx, side-idx) tuple.
        # ----2) Sort by distance

        # Calculate allowed zone
        # 1) Rotate selection-rect by -angle
        # 2) Calculate boundingRect of rotated rect
        # 3) w/2 and h/2 is the shrinking amount

        rect = QRectF(0, 0, w/2, h/2)
        rot = QTransform().rotate(-self._imgview.rotation)
        rect = rot.mapRect(rect)

        left = QVector2D(poly.at(1) - poly.at(0))
        left.normalize()
        left *= rect.width()
        left = left.toPointF()

        down = QVector2D(poly.at(3) - poly.at(0))
        down.normalize()
        down *= rect.height()
        down = down.toPointF()

        zone = QPolygonF([
            poly.at(0).toPointF() + left + down,
            poly.at(1).toPointF() - left + down,
            poly.at(2).toPointF() - left - down,
            poly.at(3).toPointF() + left - down
        ])

        # TODO: Check zone size / winding order to determine if selection rect is too big

        print("poly:", poly)
        print("zone:", zone)

        if not zone.containsPoint(mouseCoords, Qt.WindingFill):
            return (0, 0, 1, 1)

        # Crop position
        x = mouseCoords.x() - w/2
        y = mouseCoords.y() - h/2

        return (x, y, w, h)


    def updateCropCombined(self, mouseCoords: QPointF):
        rot  = QTransform().rotate(-self._imgview.rotation)
        
        # Constrain selection size
        # FIXME: WRONG
        imgSize = self._imgview.image.pixmap().size()
        rectSel = QRectF(0, 0, 100 * self._cropAspectRatio, 100)
        rectSel = rot.mapRect(rectSel)
        sizeRatio = min(1/self._cropAspectRatio, 1)

        cropH = min(self._cropHeight, imgSize.height()*sizeRatio)
        cropW = cropH * self._cropAspectRatio
        # if cropW > imgSize.width()*sizeRatio:
        #     cropW = imgSize.width()*sizeRatio
        #     cropH = cropW / self._cropAspectRatio
        self._cropHeight = cropH
        
        # Map mouse coordinates to image space
        mouse = self._imgview.mapToScene(mouseCoords.toPoint())
        mouse = self._imgview.image.mapFromParent(mouse)

        # Calculate selected area in image space
        rect = QRect(-cropW/2, -cropH/2, cropW, cropH)
        poly = rot.mapToPolygon(rect)
        poly.translate(mouse.x(), mouse.y())
        rect = poly.boundingRect()

        # Make selected polygon points relative to bounding box
        origin = rect.topLeft()
        pointsRel = [
            poly.at(0) - origin,
            poly.at(1) - origin,
            poly.at(2) - origin,
            poly.at(3) - origin
        ]
        
        # Constrain selection position (move bounding box)
        if rect.x() < 0:
            rect.moveLeft(0)
        if rect.y() < 0:
            rect.moveTop(0)
        
        if rect.right() > imgSize.width():
            rect.moveRight(imgSize.width())
        if rect.bottom() > imgSize.height():
            rect.moveBottom(imgSize.height())

        # Convert relative points inside bounding box back to image space
        origin = rect.topLeft()
        poly = QPolygonF([
            pointsRel[0] + origin,
            pointsRel[1] + origin,
            pointsRel[2] + origin,
            pointsRel[3] + origin
        ])

        # Map selected polygon to viewport
        poly = self._imgview.image.mapToParent(poly)
        poly = self._imgview.mapFromScene(poly)
        rect = poly.boundingRect()
        return (rect.x(), rect.y(), rect.width(), rect.height())
        



    def updateCropSelection(self, mouseCoords: QPointF):
        # Calculate image bounds in viewport coordinates
        img = self._imgview.image
        rect = QRectF(0, 0, img.pixmap().width(), img.pixmap().height())
        poly = img.mapToParent(rect)
        poly = self._imgview.mapFromScene(poly)
        
        #if abs(self._imgview.rotation) < 0.1:
        #    x, y, w, h = self.updateCropAligned(mouseCoords, poly)
        #else:
        #    x, y, w, h = self.updateCropRotated(mouseCoords, poly)
        x, y, w, h = self.updateCropCombined(mouseCoords)

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

    def toCvMat(self, pixmap):
        #print(f"pixmap w={pixmap.width()} h={pixmap.height()}")

        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        pixmap.save(buffer, "PNG")

        buf = np.frombuffer(buffer.data(), dtype=np.uint8)
        return cv.imdecode(buf, cv.IMREAD_UNCHANGED) # IMREAD_COLOR -> Convert to 3 channel BGR format

    def calcCropRect(self, poly: QPolygonF, pixmap):
        pad  = 4
        rect = poly.boundingRect().toRect()
        # FIXME: This may change the aspect ratio -> I think this doesn't matter
        rect.setLeft(max(0, rect.x()-pad))
        rect.setTop (max(0, rect.y()-pad))
        rect.setRight (min(pixmap.width(),  rect.right()+pad))
        rect.setBottom(min(pixmap.height(), rect.bottom()+pad))
        return rect

    def getExportPath(self, ext):
        filename = os.path.basename(self._imgview.image.filepath)
        filename = os.path.splitext(filename)[0] + f"_{self._targetWidth}x{self._targetHeight}"
        prefix = "/mnt/data/Pictures/SDOut/" + filename

        path = f"{prefix}.{ext}"
        suffix = 1
        while os.path.exists(path):
            path = f"{prefix}_{suffix:02}.{ext}"
            suffix += 1
        
        return path

    def exportImage(self, poly: QPolygonF):
        pixmap = self._imgview.image.pixmap()
        rect   = self.calcCropRect(poly, pixmap)
        mat    = self.toCvMat( pixmap.copy(rect) )
        
        p0, p1, p2, _ = poly
        ox, oy = rect.topLeft().toTuple()
        ptsSrc = np.float32([
            [p0.x()-ox, p0.y()-oy],
            [p1.x()-ox, p1.y()-oy],
            [p2.x()-ox, p2.y()-oy]
        ])

        ptsDest = np.float32([
            [0, 0],
            [self._targetWidth, 0],
            [self._targetWidth, self._targetHeight],
        ])

        # https://docs.opencv.org/3.4/da/d6e/tutorial_py_geometric_transformations.html
        matrix  = cv.getAffineTransform(ptsSrc, ptsDest)
        dsize   = (self._targetWidth, self._targetHeight)
        interp  = self._toolbar.getInterpolationMode()
        matDest = cv.warpAffine(src=mat, M=matrix, dsize=dsize, flags=interp)

        ext, params = self._toolbar.getSaveParams()
        path = self.getExportPath(ext)
        cv.imwrite(path, matDest, params)
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

        rect = self._cropRect.rect().toRect()
        rect.setRect(rect.x(), rect.y(), max(1, rect.width()), max(1, rect.height()))
        poly = self._imgview.mapToScene(rect)
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
        self._cropHeight = round(max(self._cropHeight, 1))
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
        layout.addWidget(self._buildSave())

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

    def _buildSave(self):
        self.cboInterp = QtWidgets.QComboBox()
        self.cboInterp.addItems(INTERP_MODES.keys())
        self.cboInterp.setCurrentIndex(4) # Default: Lanczos

        self.cboFormat = QtWidgets.QComboBox()
        self.cboFormat.addItems(SAVE_PARAMS.keys())

        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addRow("Interp:", self.cboInterp)
        layout.addRow("Format:", self.cboFormat)

        group = QtWidgets.QGroupBox("Save")
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
    

    def getInterpolationMode(self):
        idx = self.cboInterp.currentIndex()
        return INTERP_MODES[ self.cboInterp.itemText(idx) ]

    def getSaveParams(self):
        idx = self.cboFormat.currentIndex()
        key = self.cboFormat.itemText(idx)
        return (key.lower(), SAVE_PARAMS[key])



class PrecisionSpinBox(QtWidgets.QSpinBox):
    PRECISION = 10

    def textFromValue(self, val: int) -> str:
        return f"{val / self.PRECISION:.1f}"
    
    def valueFromText(self, text: str) -> int:
        val = float(text) * self.PRECISION
        return round(val)
