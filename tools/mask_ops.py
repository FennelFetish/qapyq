from typing_extensions import override
import os
from PySide6.QtCore import Qt, Slot, QPointF, QRectF, QSignalBlocker, QRunnable, QObject, Signal
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QLinearGradient
from PySide6 import QtWidgets
import cv2 as cv
import numpy as np
from config import Config
from ui.imgview import ImgView
from lib.mask_macro import MaskingMacro, MacroOp
from lib.filelist import DataKeys

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


    def mapPosToImage(self, pos: QPointF) -> QPointF:
        scenepos = self.imgview.mapToScene(pos.toPoint())
        return self.maskItem.mapFromParent(scenepos)

    def mapPosToImageInt(self, pos: QPointF) -> tuple[int, int]:
        imgpos = self.mapPosToImage(pos)
        return ( int(np.floor(imgpos.x())), int(np.floor(imgpos.y())) )

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

        self._cursor = self._buildCircleCursor()
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

    def _buildCircleCursor(self):
        cursorPen = QPen(QColor(0, 255, 255, 255))
        cursorPen.setStyle(Qt.PenStyle.SolidLine)

        circle = QtWidgets.QGraphicsEllipseItem()
        circle.setRect(-10, -10, 20, 20)
        circle.setPen(cursorPen)

        crosshairSize = 3
        lineH = QtWidgets.QGraphicsLineItem()
        lineH.setLine(-crosshairSize, 0, crosshairSize, 0)
        lineH.setPen(cursorPen)

        lineV = QtWidgets.QGraphicsLineItem()
        lineV.setLine(0, -crosshairSize, 0, crosshairSize)
        lineV.setPen(cursorPen)

        group = QtWidgets.QGraphicsItemGroup()
        group.addToGroup(circle)
        group.addToGroup(lineH)
        group.addToGroup(lineV)
        return group

    def updateCursor(self, pos: QPointF):
        w = float(self._pen.width())
        if self.maskItem:
            wHalf = w * 0.5
            rect = self.maskItem.transform().mapRect(QRectF(0, 0, w, w))
            rect = self.imgview.transform().mapRect(rect)
            w = rect.width()

        wHalf = w * 0.5
        self._cursor.childItems()[0].setRect(-wHalf, -wHalf, w, w)
        self._cursor.setPos(pos.x(), pos.y())
        self.imgview.scene().update()

    @override
    def onCursorVisible(self, visible: bool):
        self._cursor.setVisible(visible)


    @Slot()
    def setPenWidth(self, width: int):
        width = max(width, 1)
        self._pen.setWidth(width)
        self.updateCursor(self._cursor.pos())

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
            # TODO: Macro recording


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
        self.updateCursor(self._cursor.pos())


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
        # dx = currentPoint.x() - self._lastPoint.x()
        # dy = currentPoint.y() - self._lastPoint.y()
        # len = np.sqrt((dx*dx) + (dy*dy))
        # if len < 5:
        #     return

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



class MagicDrawMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool, Qt.CursorShape.CrossCursor)
        self._drawing = False

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
        self.spinUpperDiff.setSingleStep(0.01)
        self.spinUpperDiff.setValue(0.1)
        layout.addWidget(QtWidgets.QLabel("Upper Diff:"), row, 0)
        layout.addWidget(self.spinUpperDiff, row, 1)

        row += 1
        self.spinLowerDiff = QtWidgets.QDoubleSpinBox()
        self.spinLowerDiff.setRange(0.0, 1.0)
        self.spinLowerDiff.setSingleStep(0.01)
        self.spinLowerDiff.setValue(0.1)
        layout.addWidget(QtWidgets.QLabel("Lower Diff:"), row, 0)
        layout.addWidget(self.spinLowerDiff, row, 1)

        self.setLayout(layout)
    
    def floodfill(self, pos):
        x, y = self.mapPosToImageInt(pos)
        r = 10

        color = self.spinFillColor.value() * 255.0
        upDiff = self.spinUpperDiff.value() * 255.0
        loDiff = self.spinLowerDiff.value() * 255.0
        
        # TODO: Convert image to array in onEnabled
        pixmap = self.maskTool._imgview.image.pixmap()
        cutX, cutY = x-r, y-r
        cutSize = 2*r
        cut = pixmap.copy(cutX, cutY, cutSize, cutSize).toImage()
        mat = np.frombuffer(cut.constBits(), dtype=np.uint8)
        mat.shape = (cut.height(), cut.width(), 4)
        mat = cv.cvtColor(mat, cv.COLOR_RGBA2GRAY)

        mask = np.zeros((cut.height()+2, cut.width()+2), dtype=np.uint8)
        flags = 8 | (int(color) << 8) | cv.FLOODFILL_MASK_ONLY
        retval, floodimg, mask, rect = cv.floodFill(mat, mask, (r, r), color, loDiff, upDiff, flags)
        #print(f"flood fill result: {retval}, img: floodimg, mask: mask, rect: {rect}")
        #cv.imwrite("/mnt/ai/Datasets/floodfill.png", mask)
        mask = mask[1:-1, 1:-1]

        mat = self.maskItem.toNumpy()
        mat[cutY:cutY+cutSize, cutX:cutX+cutSize] += mask
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        self.maskTool._toolbar.addHistory("Magic Brush (Flood Fill)", mat)
    
    def grabcut(self, pos):
        x, y = self.mapPosToImageInt(pos)
        r = 10

        color = self.spinFillColor.value() * 255.0
        upDiff = self.spinUpperDiff.value() * 255.0
        loDiff = self.spinLowerDiff.value() * 255.0

        # TODO: Convert image to array in onEnabled
        pixmap = self.maskTool._imgview.image.pixmap()
        cutX, cutY = x-r, y-r
        cutSize = 2*r
        cut = pixmap.copy(cutX, cutY, cutSize, cutSize).toImage()
        img = np.frombuffer(cut.constBits(), dtype=np.uint8)
        img.shape = (cut.height(), cut.width(), 4)
        img = cv.cvtColor(img, cv.COLOR_RGBA2BGR)

        mask = self.maskItem.toNumpy()
        maskCut = mask[cutY:cutY+cutSize, cutX:cutX+cutSize]
        #maskCut = np.ascontiguousarray(maskCut)
        maskCut = np.where((maskCut!=0), cv.GC_PR_FGD, cv.GC_PR_BGD).astype(np.uint8)
        maskCut[r, r] = cv.GC_FGD
        #print(f"maskCut shape={maskCut.shape} type={maskCut.dtype} min={maskCut.min()} max={maskCut.max()}")

        # TODO: Use alt button to mark regions as definitely background
        fgd = np.zeros((1,65), np.float64)
        bgd = np.zeros((1,65), np.float64)
        grabcutMask, bgd, fgd = cv.grabCut(img, maskCut, rect=None, bgdModel=bgd, fgdModel=fgd, iterCount=1, mode=cv.GC_INIT_WITH_MASK)
        #print(grabcutMask)

        #cv.imwrite("/mnt/ai/Datasets/grabcut.png", grabcutMask)

        apply = np.where((grabcutMask==2)|(grabcutMask==0), 0, color).astype(np.uint8)
        mask[cutY:cutY+cutSize, cutX:cutX+cutSize] += apply
        self.maskItem.fromNumpy(mask)

        self.maskTool.setEdited()
        self.maskTool._toolbar.addHistory("Magic Brush (GrabCut)", mask)

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        self._drawing = True
    
    def onMouseRelease(self, alt: bool):
        self._drawing = False

    def onMouseMove(self, pos, pressure: float):
        if self._drawing:
            self.grabcut(pos)

    # @override
    # def onMouseMove(self, pos, pressure: float):
    #     self.onMousePress(pos, pressure)


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
        self.spinUpperDiff.setSingleStep(0.01)
        self.spinUpperDiff.setValue(1.0)
        layout.addWidget(QtWidgets.QLabel("Upper Diff:"), row, 0)
        layout.addWidget(self.spinUpperDiff, row, 1)

        row += 1
        self.spinLowerDiff = QtWidgets.QDoubleSpinBox()
        self.spinLowerDiff.setRange(0.0, 1.0)
        self.spinLowerDiff.setSingleStep(0.01)
        self.spinLowerDiff.setValue(0.0)
        layout.addWidget(QtWidgets.QLabel("Lower Diff:"), row, 0)
        layout.addWidget(self.spinLowerDiff, row, 1)

        self.setLayout(layout)

    @staticmethod
    def operate(mat: np.ndarray, color: int, lowerDiff: float, upperDiff: float, x: int, y: int) -> np.ndarray:
        retval, img, mask, rect = cv.floodFill(mat, None, (x, y), color, lowerDiff, upperDiff)#, cv.FLOODFILL_FIXED_RANGE)
        #print(f"flood fill result: {retval}, img: {img}, mask: {mask}, rect: {rect}")
        return mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        x, y = self.mapPosToImageInt(pos)
        w, h = self.maskItem.mask.width(), self.maskItem.mask.height()
        if not (0 <= x < w and 0 <= y < h):
            return

        color = 0 if alt else self.spinFillColor.value()
        colorFill = round(color*255)
        upperDiff = self.spinUpperDiff.value() * 255.0
        lowerDiff = self.spinLowerDiff.value() * 255.0
        # TODO: Calc upper/lower diff based on selected start point's pixel value

        mat = self.maskItem.toNumpy()
        mat = self.operate(mat, colorFill, lowerDiff, upperDiff, x, y)
        self.maskItem.fromNumpy(mat)

        xRel, yRel = x/max(1, w-1), y/max(1, h-1)
        macroItem = self.maskTool.macro.addOperation(MacroOp.FloodFill, color=colorFill, lowerDiff=lowerDiff, upperDiff=upperDiff, x=xRel, y=yRel)

        self.maskTool.setEdited()
        self.maskTool._toolbar.addHistory(f"Flood Fill ({color:.2f})", mat, macroItem)



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

    @staticmethod
    def operate(mat: np.ndarray, color: int) -> np.ndarray:
        mat.fill(color)
        return mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        color = self.spinClearColor.value()
        if alt:
            color = 1.0 - color
        colorFill = round(color*255)

        w, h = self.maskItem.mask.width(), self.maskItem.mask.height()
        mat = np.full((h, w), colorFill, dtype=np.uint8)
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        macroItem = self.maskTool.macro.addOperation(MacroOp.Clear, color=colorFill)
        self.maskTool._toolbar.addHistory(f"Clear ({color:.2f})", mat, macroItem)



class InvertMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool)

    @staticmethod
    def operate(mat: np.ndarray) -> np.ndarray:
        return 255 - mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        mat = self.maskItem.toNumpy()
        mat = self.operate(mat)
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        macroItem = self.maskTool.macro.addOperation(MacroOp.Invert)
        self.maskTool._toolbar.addHistory("Invert", mat, macroItem)



class ThresholdMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.spinColor = QtWidgets.QDoubleSpinBox()
        self.spinColor.setRange(0.0, 1.0)
        self.spinColor.setSingleStep(0.1)
        self.spinColor.setValue(0.5)
        layout.addWidget(QtWidgets.QLabel("Color:"), row, 0)
        layout.addWidget(self.spinColor, row, 1)

        self.setLayout(layout)

    @staticmethod
    def operate(mat: np.ndarray, color: int) -> np.ndarray:
        retval, dst = cv.threshold(mat, color, 255, cv.THRESH_BINARY, dst=mat)
        return mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        color = self.spinColor.value()
        colorFill = round(color*255)

        mat = self.maskItem.toNumpy()
        mat = self.operate(mat, colorFill)
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        macroItem = self.maskTool.macro.addOperation(MacroOp.Threshold, color=colorFill)
        self.maskTool._toolbar.addHistory(f"Threshold ({color:.2f})", mat, macroItem)



class MorphologyMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.cboMode = QtWidgets.QComboBox()
        self.cboMode.addItem("Grow", "grow")
        self.cboMode.addItem("Shrink", "shrink")
        self.cboMode.addItem("Close Holes", "close")
        self.cboMode.addItem("Open Gaps", "open")
        layout.addWidget(QtWidgets.QLabel("Op:"), row, 0)
        layout.addWidget(self.cboMode, row, 1)

        row += 1
        self.spinRadius = QtWidgets.QSpinBox()
        self.spinRadius.setRange(1, 4096)
        self.spinRadius.setSingleStep(1)
        self.spinRadius.setValue(10)
        layout.addWidget(QtWidgets.QLabel("Radius:"), row, 0)
        layout.addWidget(self.spinRadius, row, 1)

        self.setLayout(layout)

    @staticmethod
    def operate(mat: np.ndarray, mode: str, radius: int) -> np.ndarray:
        size = radius*2 + 1
        kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (size, size))

        borderType = cv.BORDER_CONSTANT
        borderVal  = (0,)

        match mode:
            case "grow":
                mat = cv.dilate(mat, kernel, borderType=borderType, borderValue=borderVal)
            case "shrink":
                mat = cv.erode(mat, kernel, borderType=borderType, borderValue=borderVal)
            case "close":
                mat = cv.dilate(mat, kernel, borderType=borderType, borderValue=borderVal)
                mat = cv.erode(mat, kernel, borderType=borderType, borderValue=borderVal)
            case "open":
                mat = cv.erode(mat, kernel, borderType=borderType, borderValue=borderVal)
                mat = cv.dilate(mat, kernel, borderType=borderType, borderValue=borderVal)
        
        return mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        # TODO: Grow/shrink depending on mouse button?
        mode = self.cboMode.currentData()
        radius = self.spinRadius.value()
        
        mat = self.maskItem.toNumpy()
        mat = self.operate(mat, mode, radius)
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        macroItem = self.maskTool.macro.addOperation(MacroOp.Morph, mode=mode, radius=radius)
        self.maskTool._toolbar.addHistory(f"Morphology ({mode} {radius})", mat, macroItem)



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

    @staticmethod
    def operate(mat: np.ndarray, mode: str, radius: int) -> np.ndarray:
        blurBorder  = cv.BORDER_ISOLATED
        morphBorder = cv.BORDER_CONSTANT
        borderVal   = (0,)

        if mode == "both" or radius <= 1:
            kernelSize = radius*2 + 1 # needs odd kernel size
            mat = cv.GaussianBlur(mat, (kernelSize, kernelSize), sigmaX=0, sigmaY=0, borderType=blurBorder)
        else:                                # 2    3    4    5    6    7
            r           = (radius+1) * 0.5   # 1.5, 2.0, 2.5, 3.0, 3.5, 4.0
            blurSize    = int(r)*2 + 1       # 3    5    5    7    7    9
            morphSize   = int(r+0.5)*2 - 1   # 3    3    5    5    7    7
            blurKernel  = (blurSize, blurSize)
            morphKernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (morphSize, morphSize))

            if mode == "out":
                mat = cv.dilate(mat, morphKernel, borderType=morphBorder, borderValue=borderVal)
            else:
                mat = cv.erode(mat, morphKernel, borderType=morphBorder, borderValue=borderVal)
            mat = cv.GaussianBlur(mat, blurKernel, sigmaX=0, sigmaY=0, borderType=blurBorder)
        
        return mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        mode = self.cboMode.currentData()
        radius = self.spinRadius.value()

        mat = self.maskItem.toNumpy()
        mat = self.operate(mat, mode, radius)
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        macroItem = self.maskTool.macro.addOperation(MacroOp.GaussBlur, mode=mode, radius=radius)
        self.maskTool._toolbar.addHistory(f"Gaussian Blur ({mode} {radius})", mat, macroItem)



class BlendLayersMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.cboMode = QtWidgets.QComboBox()
        self.cboMode.addItem("Add", "add")
        self.cboMode.addItem("Subtract", "subtract")
        self.cboMode.addItem("Difference", "diff")
        self.cboMode.addItem("Multiply", "mult")
        self.cboMode.addItem("Minimum", "min")
        self.cboMode.addItem("Maximum", "max")
        layout.addWidget(QtWidgets.QLabel("Mode:"), row, 0)
        layout.addWidget(self.cboMode, row, 1)

        row += 1
        self.cboSrcLayer = QtWidgets.QComboBox()
        layout.addWidget(QtWidgets.QLabel("Source:"), row, 0)
        layout.addWidget(self.cboSrcLayer, row, 1)

        self.setLayout(layout)

    def setLayers(self, layers: list):
        selectedName  = self.cboSrcLayer.currentText()
        selectedIndex = self.cboSrcLayer.currentIndex()

        self.cboSrcLayer.clear()
        for i, layer in enumerate(layers):
            self.cboSrcLayer.addItem(layer.name, int(i))
        
        index = self.cboSrcLayer.findText(selectedName)
        if index < 0:
            index = min(selectedIndex, self.cboSrcLayer.count()-1)
        self.cboSrcLayer.setCurrentIndex(max(0, index))

    @staticmethod
    def operate(srcMat: np.ndarray, destMat: np.ndarray, mode: str) -> np.ndarray:
        srcMat = srcMat.astype(np.float32)
        srcMat /= 255
        destMat = destMat.astype(np.float32)
        destMat /= 255

        match mode:
            case "add":
                destMat += srcMat
            case "subtract":
                destMat -= srcMat
            case "diff":
                np.abs(destMat - srcMat, out=destMat)
            case "mult":
                destMat *= srcMat
            case "min":
                np.minimum(srcMat, destMat, out=destMat)
            case "max":
                np.maximum(srcMat, destMat, out=destMat)

        destMat *= 255
        np.round(destMat, out=destMat)
        np.clip(destMat, 0, 255, out=destMat)
        return destMat.astype(np.uint8)

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        mode = self.cboMode.currentData()

        srcMatIndex = self.cboSrcLayer.currentData()
        srcMat = self.maskTool.layers[srcMatIndex].toNumpy()
        
        destMat = self.maskItem.toNumpy()
        destMat = self.operate(srcMat, destMat, mode)
        self.maskItem.fromNumpy(destMat)

        self.maskTool.setEdited()
        macroItem = self.maskTool.macro.addOperation(MacroOp.BlendLayers, mode=mode, srcLayer=srcMatIndex)
        self.maskTool._toolbar.addHistory(f"Blend Layers ({mode})", destMat, macroItem)



class MacroMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool)
        self.running = False

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.cboMacro = QtWidgets.QComboBox()
        layout.addWidget(QtWidgets.QLabel("Macro:"), row, 0)
        layout.addWidget(self.cboMacro, row, 1)
        self.reloadMacros()

        self.setLayout(layout)

    def reloadMacros(self):
        selectedText = self.cboMacro.currentText()
        self.cboMacro.clear()

        for root, dirs, files in os.walk(os.path.abspath(Config.pathMaskMacros)):
            for path in (f"{root}/{f}" for f in files if f.endswith(".json")):
                filenameNoExt, ext = os.path.splitext( os.path.basename(path) )
                self.cboMacro.addItem(filenameNoExt, path)
        
        index = self.cboMacro.findText(selectedText)
        self.cboMacro.setCurrentIndex(max(0, index))

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        imgPath = self.maskTool._imgview.image.filepath
        if not imgPath:
            return
        
        # Don't record macros into macros
        if self.maskTool.macro.recording:
            self.maskTool.tab.statusBar().showColoredMessage("Cannot run macros while recording macros", False)
            return

        macroName, macroPath = self.cboMacro.currentText(), self.cboMacro.currentData()
        layerIndex = self.maskTool.layers.index(self.maskTool.maskItem)

        task = MacroMaskTask(macroPath, macroName, imgPath, layerIndex, self.maskTool.layers)
        task.signals.done.connect(self.onDone)
        task.signals.fail.connect(self.onFail)

        from infer import Inference
        Inference().queueTask(task)
        self.maskTool.tab.statusBar().showMessage("Starting macro...", 0)

        # Store layers so result can be loaded when image is changed
        self.maskTool.setEdited()

    @Slot()
    def onDone(self, imgPath: str, macroName: str, layerItems: list, layerMats: list[np.ndarray], layerChanged: list[bool]):
        self.running = False
        historyTitle = f"Macro ({macroName})"

        # Undoing the macro in one layer will disable it for all other layers too!
        # Recording macros into macros could lead to all kind of weird interactions and mess up layers.
        #macroItem = self.maskTool.macro.addOperation(MacroOp.Macro, name=macroName)

        for item, mat, changed in zip(layerItems, layerMats, layerChanged):
            if changed:
                item.fromNumpy(mat)
                item.addHistory(historyTitle, mat) 

        # Handle added/deleted layers
        layerDiff = len(layerMats) - len(layerItems)
        if layerDiff > 0:
            from tools.mask import MaskItem
            start = min(len(layerMats), len(layerItems))
            for i in range(start, start+layerDiff):
                maskItem = MaskItem(f"Layer {i}")
                maskItem.fromNumpy(layerMats[i])
                maskItem.addHistory(historyTitle, layerMats[i])
                layerItems.append(maskItem)
        elif layerDiff < 0:
            for i in range(-layerDiff):
                del layerItems[-1]
        
        filelist = self.maskTool.tab.filelist
        filelist.setData(imgPath, DataKeys.MaskLayers, layerItems)
        filelist.setData(imgPath, DataKeys.MaskState, DataKeys.IconStates.Changed)

        selectedLayer = filelist.getData(imgPath, DataKeys.MaskIndex)
        selectedLayer = min(selectedLayer, len(layerItems)-1)
        filelist.setData(imgPath, DataKeys.MaskIndex, selectedLayer)

        # Reload layers
        if filelist.getCurrentFile() == imgPath:
            self.maskTool.onFileChanged(imgPath)
        
        self.maskTool.tab.statusBar().showColoredMessage(f"Finished {historyTitle}", True, 0)

    @Slot()
    def onFail(self, msg: str):
        self.running = False
        self.maskTool.tab.statusBar().showColoredMessage(f"Macro failed: {msg}", False, 0)
        print(msg)



class DetectMaskOperation(MaskOperation):
    def __init__(self, maskTool, preset: str):
        super().__init__(maskTool)
        self.preset = preset
        self.config = Config.inferMaskPresets[preset]
        self.running = False

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.spinColor = QtWidgets.QDoubleSpinBox()
        self.spinColor.setRange(0.0, 1.0)
        self.spinColor.setSingleStep(0.1)
        self.spinColor.setValue(1.0)
        layout.addWidget(QtWidgets.QLabel("Color:"), row, 0)
        layout.addWidget(self.spinColor, row, 1)

        row += 1
        self.spinThreshold = QtWidgets.QDoubleSpinBox()
        self.spinThreshold.setRange(0.0, 1.0)
        self.spinThreshold.setSingleStep(0.1)
        self.spinThreshold.setValue(0.4)
        layout.addWidget(QtWidgets.QLabel("Threshold:"), row, 0)
        layout.addWidget(self.spinThreshold, row, 1)

        self.setLayout(layout)

    @staticmethod
    def operate(mat: np.ndarray, box: dict, color: int) -> np.ndarray:
        h, w = mat.shape

        p0x, p0y = box["p0"]
        p0x, p0y = round(p0x*w), round(p0y*h)

        p1x, p1y = box["p1"]
        p1x, p1y = round(p1x*w)+1, round(p1y*h)+1

        mat[p0y:p1y, p0x:p1x] = color
        return mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        if self.running:
            return
        self.running = True

        imgPath = self.maskTool._imgview.image.filepath
        color = 0.0 if alt else self.spinColor.value()

        task = MaskTask("maskBoxes", self.maskTool.maskItem, self.config, imgPath, color)
        task.signals.loaded.connect(self.onLoaded)
        task.signals.done.connect(self.onDone)
        task.signals.fail.connect(self.onFail)

        from infer import Inference
        Inference().queueTask(task)
        self.maskTool.tab.statusBar().showMessage("Loading detection model...", 0)

        # Store layers so result can be loaded when image is changed
        self.maskTool.setEdited()

    @Slot()
    def onLoaded(self):
        self.maskTool.tab.statusBar().showMessage("Detecting boxes...", 0)

    @Slot()
    def onDone(self, maskItem, imgPath: str, color: float, boxes: list[dict]):
        self.running = False

        colorFill = round(color * 255)
        classes = set(self.config["classes"])
        threshold = self.spinThreshold.value()

        mat = maskItem.toNumpy()

        detections = {}
        detectionsApplied = 0
        for box in boxes:
            name = box["name"]
            if box["confidence"] < threshold or (classes and name not in classes):
                continue

            detections[name] = detections.get(name, 0) + 1
            detectionsApplied += 1
            mat = self.operate(mat, box, colorFill)

        maskItem.fromNumpy(mat)

        # History
        macroItem = self.maskTool.macro.addOperation(MacroOp.Detect, preset=self.preset, color=colorFill, threshold=threshold)
        historyTitle = f"Detect ({color:.2f})"
        maskItem.addHistory(historyTitle, mat, macroItem)
        if maskItem == self.maskItem:
            self.maskTool._toolbar.setHistory(maskItem)
            self.maskTool.setEdited()

        # Status bar message
        if len(boxes):
            msg = f"{len(boxes)} detections, {detectionsApplied} applied"
            if detections:
                detections = ", ".join(f"{count}x {name}" for name, count in detections.items())
                msg += f": {detections}"
        else:
            msg = "No detections"

        self.maskTool.tab.statusBar().showColoredMessage(msg, True, 0)

    @Slot()
    def onFail(self, msg: str):
        self.running = False
        self.maskTool.tab.statusBar().showColoredMessage(f"Detection failed: {msg}", False, 0)
        print(msg)



class SegmentMaskOperation(MaskOperation):
    def __init__(self, maskTool, preset: str):
        super().__init__(maskTool)
        self.preset = preset
        self.config = Config.inferMaskPresets[preset]
        self.running = False

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.spinColor = QtWidgets.QDoubleSpinBox()
        self.spinColor.setRange(0.0, 1.0)
        self.spinColor.setSingleStep(0.1)
        self.spinColor.setValue(1.0)
        layout.addWidget(QtWidgets.QLabel("Color:"), row, 0)
        layout.addWidget(self.spinColor, row, 1)

        self.setLayout(layout)

    @staticmethod
    def operate(mat: np.ndarray, maskBytes: bytes, color: float) -> np.ndarray:
        h, w = mat.shape

        result = np.frombuffer(maskBytes, dtype=np.uint8)
        result.shape = (h, w)

        if color < 0.9999:
            resultFloat = result.astype(np.float32)
            resultFloat *= color
            result = resultFloat.astype(np.uint8)

        np.maximum(mat, result, out=mat)
        return mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        if self.running:
            return
        self.running = True

        imgPath = self.maskTool._imgview.image.filepath
        color = self.spinColor.value()

        task = MaskTask("mask", self.maskItem, self.config, imgPath, color)
        task.signals.loaded.connect(self.onLoaded)
        task.signals.done.connect(self.onDone)
        task.signals.fail.connect(self.onFail)

        from infer import Inference
        Inference().queueTask(task)
        self.maskTool.tab.statusBar().showMessage("Loading segmentation model...", 0)

        # Store layers so result can be loaded when image is changed
        self.maskTool.setEdited()

    @Slot()
    def onLoaded(self):
        self.maskTool.tab.statusBar().showMessage("Generating segmentation mask...", 0)

    @Slot()
    def onDone(self, maskItem, imgPath: str, color: float, maskBytes: bytes):
        self.running = False

        mat = maskItem.toNumpy()
        mat = self.operate(mat, maskBytes, color)
        maskItem.fromNumpy(mat)

        macroItem = self.maskTool.macro.addOperation(MacroOp.Segment, preset=self.preset, color=color)
        historyTitle = f"Segmentation ({color:.2f})"
        maskItem.addHistory(historyTitle, mat, macroItem)
        if maskItem == self.maskItem:
            self.maskTool._toolbar.addHistory(historyTitle, mat)
            self.maskTool.setEdited()

        self.maskTool.tab.statusBar().showColoredMessage("Segmentation finished", True)

    @Slot()
    def onFail(self, msg: str):
        self.running = False
        self.maskTool.tab.statusBar().showColoredMessage(f"Segmentation failed: {msg}", False, 0)
        print(msg)



class MaskTask(QRunnable):
    class Signals(QObject):
        loaded = Signal()
        done = Signal(object, str, float, object)
        fail = Signal(str)
    
    def __init__(self, funcName: str, maskItem, config: dict, imgPath: str, color: float):
        super().__init__()
        self.signals  = self.Signals()
        self.funcName = funcName
        self.maskItem = maskItem
        self.config   = config
        self.imgPath  = imgPath
        self.color    = color

    @Slot()
    def run(self):
        try:
            from infer import Inference
            inferProc = Inference().proc
            inferProc.start()

            inferProc.setupMasking(self.config)
            self.signals.loaded.emit()

            func = getattr(inferProc, self.funcName)
            result = func(self.config, self.imgPath)
            self.signals.done.emit(self.maskItem, self.imgPath, self.color, result)
        except Exception as ex:
            import traceback
            traceback.print_exc()
            self.signals.fail.emit(str(ex))



class MacroMaskTask(QRunnable):
    class Signals(QObject):
        done = Signal(str, str, list, list, list) # imgPath: str, macroName: str, layers: list[MaskItem], layerMats: list[np.ndarray], layerChanged: list[bool]
        fail = Signal(str)

    def __init__(self, macroPath: str, macroName: str, imgPath: str, currentLayerIndex: int, layerItems):
        super().__init__()
        self.signals    = self.Signals()
        self.macroPath  = macroPath
        self.macroName  = macroName
        self.imgPath    = imgPath
        self.currentLayerIndex = currentLayerIndex
        self.layers     = layerItems
        self.layerMats  = [item.toNumpy() for item in layerItems]

    @Slot()
    def run(self):
        try:
            macro = MaskingMacro()
            macro.loadFrom(self.macroPath)
            layerMats, layerChanged = macro.run(self.imgPath, self.layerMats, self.currentLayerIndex)

            self.signals.done.emit(self.imgPath, self.macroName, self.layers, layerMats, layerChanged)
        except Exception as ex:
            import traceback
            traceback.print_exc()
            self.signals.fail.emit(str(ex))
