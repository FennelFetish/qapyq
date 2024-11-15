from typing_extensions import override
from PySide6.QtCore import Qt, Slot, QPointF, QSignalBlocker
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QLinearGradient
from PySide6 import QtWidgets
import cv2 as cv
import numpy as np
from ui.imgview import ImgView


# Use OpenCV's GrabCut for bounding box -> segmentation conversion.


class MaskOperation(QtWidgets.QWidget):
    def __init__(self, maskTool, cursor=None):
        super().__init__()
        from .mask import MaskTool
        self.maskTool: MaskTool = maskTool

        self._altCursor = cursor
        self._origCursor = None

    @property
    def maskItem(self):
        return self.maskTool.maskItem

    @property
    def imgview(self):
        return self.maskTool._imgview


    def mapPosToImage(self, eventPos):
        imgpos = self.imgview.mapToScene(eventPos.toPoint())
        imgpos = self.maskItem.mapFromParent(imgpos)
        return imgpos

    def getCursor(self):
        raise NotImplementedError()

    def onEnabled(self, imgview: ImgView):
        self._origCursor = imgview.cursor()
        if self._altCursor:
            imgview.setCursor(self._altCursor)

    def onDisabled(self, imgview: ImgView):
        imgview.setCursor(self._origCursor)
        self._origCursor = None

    def onFileChanged(self, file: str):
        pass

    def onLayerChanged(self):
        pass

    def onMousePress(self, pos, pressure: float, alt: bool):
        pass

    def onMouseRelease(self, alt: bool):
        pass

    def onMouseMove(self, pos, pressure: float):
        pass

    def onMouseWheel(self, delta: int):
        pass

    def onCursorVisible(self, visible: bool):
        pass

    def op(self, image):
        raise NotImplementedError()



class DrawMaskOperation(MaskOperation):
    DRAW_NONE   = 0
    DRAW_STROKE = 1
    DRAW_ERASE  = 2

    def __init__(self, maskTool):
        super().__init__(maskTool, Qt.CursorShape.BlankCursor)

        self._drawing = self.DRAW_NONE
        self._lastPoint: QPointF = None
        self._lastColor: QColor = None
        self._strokeLength = 0

        self._painter = QPainter()
        
        self._pen = QPen()
        self._pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self._pen.setWidth(10)
        self._gradient = QLinearGradient()

        cursorPen = QPen(QColor(0, 255, 255, 255))
        cursorPen.setStyle(Qt.PenStyle.DashLine)
        cursorPen.setDashPattern([2,3])
        self._cursor = QtWidgets.QGraphicsEllipseItem()
        self._cursor.setPen(cursorPen)

        self._build()

    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.spinBrushSize = QtWidgets.QSpinBox()
        self.spinBrushSize.setRange(1, 1024)
        self.spinBrushSize.setSingleStep(10)
        self.spinBrushSize.setValue(self._pen.width())
        self.spinBrushSize.valueChanged.connect(self.setPenWidth)
        layout.addWidget(QtWidgets.QLabel("Size:"), row, 0)
        layout.addWidget(self.spinBrushSize, row, 1)

        row += 1
        self.spinBrushColor = QtWidgets.QDoubleSpinBox()
        self.spinBrushColor.setRange(0.0, 1.0)
        self.spinBrushColor.setSingleStep(0.1)
        self.spinBrushColor.setValue(1.0)
        layout.addWidget(QtWidgets.QLabel("Color:"), row, 0)
        layout.addWidget(self.spinBrushColor, row, 1)

        row += 1
        self.chkBrushAntiAlias = QtWidgets.QCheckBox("Smooth")
        self.chkBrushAntiAlias.setChecked(True)
        layout.addWidget(self.chkBrushAntiAlias, row, 0, 1, 2)

        self.setLayout(layout)


    def stopDraw(self, valid=False):
        if not self._drawing:
            return

        erase = self._drawing==self.DRAW_ERASE
        self._drawing = self.DRAW_NONE
        self._painter.end()

        # FIXME: Handle case when file is changed. Don't apply history to new file, etc.
        if valid:
            self.maskTool.setEdited()
            mode = "Erase" if erase else "Stroke"
            self.maskTool._toolbar.addHistory(f"Brush {mode} ({self._strokeLength:.1f})")


    @Slot()
    def setPenWidth(self, width: int):
        width = max(width, 1)
        self._pen.setWidth(width)
        self.updateCursor(self._cursor.rect().center())

        with QSignalBlocker(self.spinBrushSize):
            self.spinBrushSize.setValue(width)

    def updatePen(self, pressure, endPoint) -> QColor:
        self._gradient.setStart(self._lastPoint)
        self._gradient.setFinalStop(endPoint)

        color = pressure * self.spinBrushColor.value()
        endColor = QColor.fromRgbF(color, color, color, 1.0)
        self._gradient.setStops([(0.0, self._lastColor), (1.0, endColor)])

        self._pen.setBrush(QBrush(self._gradient))
        self._painter.setPen(self._pen)

        return endColor


    def updateCursor(self, pos: QPointF):
        w = float(self._pen.width())
        if self.maskItem:
            rect = self.maskItem.mapToParent(0, 0, w, w)
            rect = self.imgview.mapFromScene(rect).boundingRect()
            w = rect.width()

        wHalf = w * 0.5
        self._cursor.setRect(pos.x()-wHalf, pos.y()-wHalf, w, w)
        self.imgview.scene().update()

    @override
    def onCursorVisible(self, visible: bool):
        self._cursor.setVisible(visible)


    @override
    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        imgview._guiScene.addItem(self._cursor)

    @override
    def onDisabled(self, imgview):
        super().onDisabled(imgview)
        self.stopDraw()
        imgview._guiScene.removeItem(self._cursor)

    @override
    def onFileChanged(self, file: str):
        self.stopDraw()
        self.updateCursor(self._cursor.rect().center())


    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        if self._drawing:
            return

        self._painter.begin(self.maskItem.mask)
        if alt: # Erase
            self._drawing = self.DRAW_ERASE
            self._painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        else:
            self._drawing = self.DRAW_STROKE
            self._painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Lighten)

        if self.chkBrushAntiAlias.isChecked():
            self._painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = pressure * self.spinBrushColor.value()
        self._lastColor = QColor.fromRgbF(color, color, color, 1.0)
        self._lastPoint = self.mapPosToImage(pos)
        self._strokeLength = 0

        self.updatePen(pressure, self._lastPoint)
        self._painter.drawPoint(self._lastPoint)
        self.maskItem.update()

    @override
    def onMouseMove(self, pos, pressure: float):
        self.updateCursor(pos)

        if not self._drawing or not self.maskItem:
            return

        currentPoint = self.mapPosToImage(pos)
        self._lastColor = self.updatePen(pressure, currentPoint)
        self._painter.drawLine(self._lastPoint, currentPoint)
        self.maskItem.update()

        dx = currentPoint.x() - self._lastPoint.x()
        dy = currentPoint.y() - self._lastPoint.y()
        self._strokeLength += np.sqrt((dx*dx) + (dy*dy))
        self._lastPoint = currentPoint

    @override
    def onMouseRelease(self, alt: bool):
        if not self._drawing:
            return

        # Only stop drawing if same button is released
        erase = self._drawing==self.DRAW_ERASE
        if alt == erase:
            self.stopDraw(True)

    @override
    def onMouseWheel(self, delta: int):
        width = self._pen.width()
        width += delta
        self.setPenWidth(width)



class FillMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool, Qt.CursorShape.CrossCursor)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.spinFillColor = QtWidgets.QDoubleSpinBox()
        self.spinFillColor.setRange(0.0, 1.0)
        self.spinFillColor.setSingleStep(0.1)
        self.spinFillColor.setValue(1.0)
        layout.addWidget(QtWidgets.QLabel("Color:"), row, 0)
        layout.addWidget(self.spinFillColor, row, 1)

        row += 1
        self.spinUpperDiff = QtWidgets.QDoubleSpinBox()
        self.spinUpperDiff.setRange(0.0, 1.0)
        self.spinUpperDiff.setSingleStep(0.1)
        self.spinUpperDiff.setValue(1.0)
        layout.addWidget(QtWidgets.QLabel("Upper Diff:"), row, 0)
        layout.addWidget(self.spinUpperDiff, row, 1)

        row += 1
        self.spinLowerDiff = QtWidgets.QDoubleSpinBox()
        self.spinLowerDiff.setRange(0.0, 1.0)
        self.spinLowerDiff.setSingleStep(0.1)
        self.spinLowerDiff.setValue(0.0)
        layout.addWidget(QtWidgets.QLabel("Lower Diff:"), row, 0)
        layout.addWidget(self.spinLowerDiff, row, 1)

        self.setLayout(layout)

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        pos = self.mapPosToImage(pos).toPoint()
        pos = (pos.x(), pos.y())

        color = self.spinFillColor.value()
        upperDiff = self.spinUpperDiff.value() * 255.0
        lowerDiff = self.spinLowerDiff.value() * 255.0

        mat = self.maskItem.toNumpy()
        retval, img, mask, rect = cv.floodFill(mat, None, pos, color*255, lowerDiff, upperDiff)
        #print(f"flood fill result: {retval}, img: {img}, mask: {mask}, rect: {rect}")
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        self.maskTool._toolbar.addHistory(f"Flood Fill ({color:.2f})")



class ClearMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.spinClearColor = QtWidgets.QDoubleSpinBox()
        self.spinClearColor.setRange(0.0, 1.0)
        self.spinClearColor.setSingleStep(0.1)
        self.spinClearColor.setValue(0.0)
        layout.addWidget(QtWidgets.QLabel("Color:"), row, 0)
        layout.addWidget(self.spinClearColor, row, 1)

        self.setLayout(layout)

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        color = self.spinClearColor.value()
        if alt:
            color = 1.0 - color

        w, h = self.maskItem.mask.width(), self.maskItem.mask.height()
        mat = np.full((h, w), color*255, dtype=np.uint8)
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        self.maskTool._toolbar.addHistory(f"Clear ({color:.2f})")



class InvertMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool)

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        mat = self.maskItem.toNumpy()
        mat = 255 - mat
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        self.maskTool._toolbar.addHistory("Invert")



class BlurMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.cboMode = QtWidgets.QComboBox()
        self.cboMode.addItem("Both", "both")
        self.cboMode.addItem("Outwards", "out")
        self.cboMode.addItem("Inwards", "in")
        layout.addWidget(QtWidgets.QLabel("Direction:"), row, 0)
        layout.addWidget(self.cboMode, row, 1)

        row += 1
        self.spinRadius = QtWidgets.QSpinBox()
        self.spinRadius.setRange(1, 4096)
        self.spinRadius.setSingleStep(1)
        self.spinRadius.setValue(10)
        layout.addWidget(QtWidgets.QLabel("Radius:"), row, 0)
        layout.addWidget(self.spinRadius, row, 1)

        self.setLayout(layout)

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        r = self.spinRadius.value()
        size = r*2 + 1 # needs odd kernel size
        kernel = (size, size)

        mat = self.maskItem.toNumpy()
        blurred = cv.GaussianBlur(mat, kernel, sigmaX=0, sigmaY=0)

        mode = self.cboMode.currentData()
        match mode:
            case "out":
                #mask = cv.bitwise_not(mat)
                mask = 255 - mat
                mat = cv.add(mat, blurred, mat, mask)
            case "in":
                blurred = 255 - blurred
                mat = cv.subtract(mat, blurred, mat, mat)
            case _:
                mat = blurred

        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        self.maskTool._toolbar.addHistory(f"Gaussian Blur ({mode} {r})")
