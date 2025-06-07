from typing_extensions import override
from PySide6.QtCore import Qt, Slot, QPointF, QRectF, QSignalBlocker, QRunnable, QObject, Signal
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QLinearGradient
from PySide6 import QtWidgets
import cv2 as cv
import numpy as np
from config import Config
from ui.imgview import ImgView
import lib.mask_macro as mask_macro
import lib.qtlib as qtlib
from lib.filelist import DataKeys



# Use OpenCV's GrabCut for bounding box -> segmentation conversion.
# Or cv.watershed()? https://docs.opencv.org/3.4/d3/db4/tutorial_py_watershed.html

# TODO: Add Mask Operation: Load from Alpha
# TODO: Add ConvexHull op? Move/Shift op?


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

        self._recordingStroke = False
        self._strokePoints: list[tuple[QPointF, float]] = []

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
            macroItem = self.tryCreateMacroItem(erase)
            self.maskTool._toolbar.addHistory(f"Brush {mode} ({self._strokeLength:.1f})", None, macroItem)

        self._strokePoints.clear()
        self._recordingStroke = False

    def tryCreateMacroItem(self, erase: bool):
        if not self._recordingStroke:
            return None

        w, h = self.maskItem.size
        w, h = w-1, h-1

        points = []
        for point, pressure in self._strokePoints:
            x, y = point.x()/w, point.y()/h
            points.append((x, y, pressure))

        color  = 0 if erase else self.spinBrushColor.value()
        size   = self.spinBrushSize.value()
        smooth = self.chkBrushAntiAlias.isChecked()
        return self.maskTool.macro.addOperation(mask_macro.MacroOp.Brush, color=color, size=size, smooth=smooth, stroke=points)


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
        color = pressure * self.spinBrushColor.value()
        if alt: # Erase
            self._drawing = self.DRAW_ERASE
            self._painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            color = 0
        else:
            self._drawing = self.DRAW_STROKE
            self._painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Lighten)

        if self.chkBrushAntiAlias.isChecked():
            self._painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._lastColor = QColor.fromRgbF(color, color, color, 1.0)
        self._lastPoint = self.mapPosToImage(pos)
        self._strokeLength = 0

        self.updatePen(pressure, self._lastPoint)
        self._painter.drawPoint(self._lastPoint)
        self.maskItem.update()

        self._recordingStroke = self.maskTool.macro.recording
        if self._recordingStroke:
            self._strokePoints.append((self._lastPoint, pressure))

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

        if self._recordingStroke:
            self._strokePoints.append((currentPoint, pressure))

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


class DrawRectangleMaskOperation(MaskOperation):
    DRAW_NONE  = 0
    DRAW_FILL  = 1
    DRAW_ERASE = 2

    def __init__(self, maskTool):
        super().__init__(maskTool, Qt.CursorShape.CrossCursor)

        self._drawing = self.DRAW_NONE
        self._startPoint: QPointF = None

        rectPen = QPen(QColor(0, 255, 255, 255))
        rectPen.setStyle(Qt.PenStyle.SolidLine)

        rectBrush = QBrush(QColor(80, 180, 180, 30))
        rectBrush.setStyle(Qt.BrushStyle.Dense2Pattern)

        self._rect = QtWidgets.QGraphicsRectItem(-50, -50, 100, 100)
        self._rect.setPen(rectPen)
        self._rect.setBrush(rectBrush)
        self._rect.setVisible(False)

        self._build()

    def _build(self):
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

    @override
    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        imgview._guiScene.addItem(self._rect)

    @override
    def onDisabled(self, imgview):
        imgview._guiScene.removeItem(self._rect)
        self.stopDraw(imgview)
        super().onDisabled(imgview)

    @override
    def onFileChanged(self, file: str):
        self.stopDraw()

    def updateRect(self, pos):
        rect = QRectF()
        rect.setCoords(self._startPoint.x(), self._startPoint.y(), pos.x(), pos.y())
        self._rect.setRect(rect)

        self.imgview.scene().update()

    def stopDraw(self, imgview: ImgView|None=None):
        self._drawing = self.DRAW_NONE
        self._rect.setVisible(False)

        if imgview:
            imgview.scene().update()

    def applyDraw(self):
        color = 0.0 if self._drawing == self.DRAW_ERASE else self.spinColor.value()
        colorFill = round(color * 255)

        self.stopDraw(self.imgview)

        rect = self._rect.rect()
        startPos = self.mapPosToImage(rect.topLeft())
        endPos   = self.mapPosToImage(rect.bottomRight())

        x0, y0 = startPos.x(), startPos.y()
        x1, y1 = endPos.x(), endPos.y()

        # Sort
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0

        # Map position to range [0..1]
        imgSize = self.imgview.image.pixmap().size()
        x0 = max(np.floor(x0) / imgSize.width(),  0.0)
        x1 = min(np.ceil (x1) / imgSize.width(),  1.0)
        y0 = max(np.floor(y0) / imgSize.height(), 0.0)
        y1 = min(np.ceil (y1) / imgSize.height(), 1.0)

        mat = self.maskItem.toNumpy()
        mat = self.operate(mat, colorFill, x0, y0, x1, y1)
        self.maskItem.fromNumpy(mat)

        macroItem = self.maskTool.macro.addOperation(mask_macro.MacroOp.Rectangle, color=colorFill, x0=x0, y0=y0, x1=x1, y1=y1)

        self.maskTool.setEdited()
        self.maskTool._toolbar.addHistory(f"Rectangle ({color:.2f})", mat, macroItem)

    @staticmethod
    def operate(mat: np.ndarray, color: int, x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0

        h, w = mat.shape
        x0 = round(x0 * w)
        x1 = round(x1 * w)
        y0 = round(y0 * h)
        y1 = round(y1 * h)

        mat[y0:y1, x0:x1] = color
        return mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        if self._drawing:
            return

        self._drawing = self.DRAW_ERASE if alt else self.DRAW_FILL
        self._startPoint = pos

        self._rect.setVisible(True)
        self.updateRect(pos)

    @override
    def onMouseMove(self, pos, pressure: float):
        if self._drawing:
            self.updateRect(pos)

    @override
    def onMouseRelease(self, alt: bool):
        if not self._drawing:
            return

        # Only stop drawing if same button is released
        erase = self._drawing==self.DRAW_ERASE
        if alt == erase:
            self.applyDraw()


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
        macroItem = self.maskTool.macro.addOperation(mask_macro.MacroOp.FloodFill, color=colorFill, lowerDiff=lowerDiff, upperDiff=upperDiff, x=xRel, y=yRel)

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
        macroItem = self.maskTool.macro.addOperation(mask_macro.MacroOp.Clear, color=colorFill)
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
        macroItem = self.maskTool.macro.addOperation(mask_macro.MacroOp.Invert)
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
        macroItem = self.maskTool.macro.addOperation(mask_macro.MacroOp.Threshold, color=colorFill)
        self.maskTool._toolbar.addHistory(f"Threshold ({color:.2f})", mat, macroItem)



class NormalizeMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.spinColorMin = QtWidgets.QDoubleSpinBox()
        self.spinColorMin.setRange(0.0, 1.0)
        self.spinColorMin.setSingleStep(0.1)
        self.spinColorMin.setValue(0.0)
        layout.addWidget(QtWidgets.QLabel("Color Min:"), row, 0)
        layout.addWidget(self.spinColorMin, row, 1)

        row += 1
        self.spinColorMax = QtWidgets.QDoubleSpinBox()
        self.spinColorMax.setRange(0.0, 1.0)
        self.spinColorMax.setSingleStep(0.1)
        self.spinColorMax.setValue(1.0)
        layout.addWidget(QtWidgets.QLabel("Color Max:"), row, 0)
        layout.addWidget(self.spinColorMax, row, 1)

        self.setLayout(layout)

    @staticmethod
    def operate(mat: np.ndarray, colorMin: int, colorMax: int) -> np.ndarray:
        mat = cv.normalize(mat, mat, colorMin, colorMax, norm_type=cv.NORM_MINMAX)
        return mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        colorMin = self.spinColorMin.value()
        colorMax = self.spinColorMax.value()
        colorMin8bit = round(colorMin*255)
        colorMax8bit = round(colorMax*255)

        mat = self.maskItem.toNumpy()
        mat = self.operate(mat, colorMin8bit, colorMax8bit)
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        macroItem = self.maskTool.macro.addOperation(mask_macro.MacroOp.Normalize, colorMin=colorMin8bit, colorMax=colorMax8bit)
        self.maskTool._toolbar.addHistory(f"Normalize ({colorMin:.2f} - {colorMax:.2f})", mat, macroItem)



class QuantizeMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.cboMode = QtWidgets.QComboBox()
        self.cboMode.addItem("Minimum", "min")
        self.cboMode.addItem("Maximum", "max")
        self.cboMode.addItem("Mean", "mean")
        self.cboMode.addItem("Median", "median")
        layout.addWidget(QtWidgets.QLabel("Mode:"), row, 0)
        layout.addWidget(self.cboMode, row, 1)

        row += 1
        self.spinGridSize = QtWidgets.QSpinBox()
        self.spinGridSize.setRange(2, 4096)
        self.spinGridSize.setSingleStep(1)
        self.spinGridSize.setValue(8)
        layout.addWidget(QtWidgets.QLabel("Grid Size:"), row, 0)
        layout.addWidget(self.spinGridSize, row, 1)

        self.setLayout(layout)

    @staticmethod
    def operate(mat: np.ndarray, mode: str, gridSize: int) -> np.ndarray:
        match mode:
            case "min":    tileValueFunc = np.min
            case "max":    tileValueFunc = np.max
            case "mean":   tileValueFunc = np.mean
            case "median": tileValueFunc = np.median
            case _:
                raise ValueError(f"Invalid quantization mode: {mode}")

        h, w   = mat.shape
        tilesX = w // gridSize
        tilesY = h // gridSize
        sizeX  = tilesX * gridSize
        sizeY  = tilesY * gridSize

        # If the mask size is not divisible by gridSize, crop
        matQuant = mat if (sizeX==w and sizeY==h) else mat[0:sizeY, 0:sizeX]

        tiles = matQuant.reshape(tilesY, gridSize, tilesX, gridSize)
        tileValues = tileValueFunc(tiles, axis=(1, 3)).astype(np.uint8)

        matQuant = cv.resize(tileValues, (sizeX, sizeY), interpolation=cv.INTER_NEAREST)

        # Pad and process border tiles separately
        if sizeX != w or sizeY != h:
            padX = w - sizeX
            padY = h - sizeY
            matQuant = np.pad(matQuant, ((0, padY), (0, padX)), mode="empty")

            # If both sides are padded, the corner will be calculated twice. Doesn't matter.
            if padX > 0:
                for y in range(0, h, gridSize):
                    matQuant[y:y+gridSize, sizeX:w] = tileValueFunc( mat[y:y+gridSize, sizeX:w] )
            if padY > 0:
                for x in range(0, w, gridSize):
                    matQuant[sizeY:h, x:x+gridSize] = tileValueFunc( mat[sizeY:h, x:x+gridSize] )

        return matQuant

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        mode: str = self.cboMode.currentData()
        gridSize = self.spinGridSize.value()

        mat = self.maskItem.toNumpy()
        mat = self.operate(mat, mode, gridSize)
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        macroItem = self.maskTool.macro.addOperation(mask_macro.MacroOp.Quantize, mode=mode, gridSize=gridSize)
        self.maskTool._toolbar.addHistory(f"Quantize ({mode} {gridSize})", mat, macroItem)



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
        self.cboBorderMode = QtWidgets.QComboBox()
        self.cboBorderMode.addItem("Reflect", (cv.BORDER_REFLECT, 0))
        self.cboBorderMode.addItem("Replicate", (cv.BORDER_REPLICATE, 0))
        self.cboBorderMode.addItem("Const Black", (cv.BORDER_CONSTANT, 0))
        self.cboBorderMode.addItem("Const White", (cv.BORDER_CONSTANT, 255))
        layout.addWidget(QtWidgets.QLabel("Border:"), row, 0)
        layout.addWidget(self.cboBorderMode, row, 1)

        row += 1
        self.spinRadius = QtWidgets.QSpinBox()
        self.spinRadius.setRange(1, 4096)
        self.spinRadius.setSingleStep(1)
        self.spinRadius.setValue(10)
        layout.addWidget(QtWidgets.QLabel("Radius:"), row, 0)
        layout.addWidget(self.spinRadius, row, 1)

        self.setLayout(layout)

    @staticmethod
    def operate(mat: np.ndarray, mode: str, radius: int, border: int = cv.BORDER_CONSTANT, borderVal: int = 0) -> np.ndarray:
        size = radius*2 + 1
        kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (size, size))
        bv = (borderVal,)

        match mode:
            case "grow":
                mat = cv.dilate(mat, kernel, borderType=border, borderValue=bv)
            case "shrink":
                mat = cv.erode(mat, kernel, borderType=border, borderValue=bv)
            case "close":
                mat = cv.dilate(mat, kernel, borderType=border, borderValue=bv)
                mat = cv.erode(mat, kernel, borderType=border, borderValue=bv)
            case "open":
                mat = cv.erode(mat, kernel, borderType=border, borderValue=bv)
                mat = cv.dilate(mat, kernel, borderType=border, borderValue=bv)

        return mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        # TODO: Grow/shrink depending on mouse button?
        mode = self.cboMode.currentData()
        borderType, borderVal = self.cboBorderMode.currentData()
        radius = self.spinRadius.value()

        mat = self.maskItem.toNumpy()
        mat = self.operate(mat, mode, radius, borderType, borderVal)
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        macroItem = self.maskTool.macro.addOperation(mask_macro.MacroOp.Morph, mode=mode, radius=radius, border=borderType, borderVal=borderVal)
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
        self.cboBorderMode = QtWidgets.QComboBox()
        self.cboBorderMode.addItem("Reflect", (cv.BORDER_REFLECT, 0))
        self.cboBorderMode.addItem("Replicate", (cv.BORDER_REPLICATE, 0))
        self.cboBorderMode.addItem("Const Black", (cv.BORDER_CONSTANT, 0))
        self.cboBorderMode.addItem("Const White", (cv.BORDER_CONSTANT, 255))
        layout.addWidget(QtWidgets.QLabel("Border:"), row, 0)
        layout.addWidget(self.cboBorderMode, row, 1)

        row += 1
        self.spinRadius = QtWidgets.QSpinBox()
        self.spinRadius.setRange(1, 4096)
        self.spinRadius.setSingleStep(1)
        self.spinRadius.setValue(10)
        layout.addWidget(QtWidgets.QLabel("Radius:"), row, 0)
        layout.addWidget(self.spinRadius, row, 1)

        self.setLayout(layout)

    @staticmethod
    def operate(mat: np.ndarray, mode: str, radius: int, border: int = cv.BORDER_CONSTANT, borderVal: int = 0) -> np.ndarray:
        # cv.GaussianBlur has no borderVal argument and I don't want to pad the image.
        # https://github.com/opencv/opencv/issues/25032
        if border == cv.BORDER_CONSTANT:
            #blurBorder = cv.BORDER_ISOLATED
            blurBorder = cv.BORDER_REPLICATE
        else:
            blurBorder = border

        morphBorder = border
        bv = (borderVal,)

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
                mat = cv.dilate(mat, morphKernel, borderType=morphBorder, borderValue=bv)
            else:
                mat = cv.erode(mat, morphKernel, borderType=morphBorder, borderValue=bv)
            mat = cv.GaussianBlur(mat, blurKernel, sigmaX=0, sigmaY=0, borderType=blurBorder)

        return mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        mode = self.cboMode.currentData()
        borderType, borderVal = self.cboBorderMode.currentData()
        radius = self.spinRadius.value()

        mat = self.maskItem.toNumpy()
        mat = self.operate(mat, mode, radius, borderType, borderVal)
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        macroItem = self.maskTool.macro.addOperation(mask_macro.MacroOp.GaussBlur, mode=mode, radius=radius, border=borderType, borderVal=borderVal)
        self.maskTool._toolbar.addHistory(f"Gaussian Blur ({mode} {radius})", mat, macroItem)



class CentroidRectMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.spinAspect = QtWidgets.QDoubleSpinBox()
        self.spinAspect.setDecimals(4)
        self.spinAspect.setRange(0.0, 1024.0)
        self.spinAspect.setSingleStep(0.05)
        self.spinAspect.setValue(1.0)
        layout.addWidget(QtWidgets.QLabel("Aspect:"), row, 0)
        layout.addWidget(self.spinAspect, row, 1)

        row += 1
        self.spinColor = QtWidgets.QDoubleSpinBox()
        self.spinColor.setRange(0.0, 1.0)
        self.spinColor.setSingleStep(0.1)
        self.spinColor.setValue(1.0)
        layout.addWidget(QtWidgets.QLabel("Fill Color:"), row, 0)
        layout.addWidget(self.spinColor, row, 1)

        self.setLayout(layout)

    @staticmethod
    def operate(mat: np.ndarray, aspectRatio: float, color: int) -> np.ndarray:
        if aspectRatio <= 0.0:
            raise ValueError("CentroidRectMaskOperation: Aspect ratio must be larger than 0")

        h, w = mat.shape[:2]

        mom = cv.moments(mat, binaryImage=True)
        m00 = mom["m00"] # sum (white pixel count)
        if m00 > 0.9:
            cx = int(mom["m10"] / m00)
            cy = int(mom["m01"] / m00)
        else:
            cx = (w-1) // 2
            cy = (h-1) // 2

        if h > w:
            rectW = w
            rectH = min(round(w * aspectRatio), h)
        else:
            rectW = min(round(h * aspectRatio), w)
            rectH = h

        x0 = cx - int(rectW / 2)
        x0 = max(x0, 0)
        x1 = x0 + rectW
        if x1 > w:
            x1 = w
            x0 = w - rectW

        y0 = cy - int(rectH / 2)
        y0 = max(y0, 0)
        y1 = y0 + rectH
        if y1 > h:
            y1 = h
            y0 = h - rectH

        mat[y0:y1, x0:x1] = color
        return mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        aspectRatio = self.spinAspect.value()

        color = self.spinColor.value()
        color8Bit = round(color*255)

        mat = self.maskItem.toNumpy()
        mat = self.operate(mat, aspectRatio, color8Bit)
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        macroItem = self.maskTool.macro.addOperation(
            mask_macro.MacroOp.CentroidRect, aspectRatio=aspectRatio, color=color8Bit
        )
        self.maskTool._toolbar.addHistory(f"Centroid Rect ({aspectRatio:.4f})", mat, macroItem)



class DetectPadMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.spinMinColor = QtWidgets.QDoubleSpinBox()
        self.spinMinColor.setRange(0.0, 1.0)
        self.spinMinColor.setSingleStep(0.1)
        self.spinMinColor.setValue(0.0)
        layout.addWidget(QtWidgets.QLabel("Min Color:"), row, 0)
        layout.addWidget(self.spinMinColor, row, 1)

        row += 1
        self.spinMaxColor = QtWidgets.QDoubleSpinBox()
        self.spinMaxColor.setRange(0.0, 1.0)
        self.spinMaxColor.setSingleStep(0.1)
        self.spinMaxColor.setValue(1.0)
        layout.addWidget(QtWidgets.QLabel("Max Color:"), row, 0)
        layout.addWidget(self.spinMaxColor, row, 1)

        row += 1
        self.spinTolerance = QtWidgets.QDoubleSpinBox()
        self.spinTolerance.setRange(0.0, 1.0)
        self.spinTolerance.setSingleStep(0.01)
        self.spinTolerance.setValue(0.0)
        layout.addWidget(QtWidgets.QLabel("Tolerance:"), row, 0)
        layout.addWidget(self.spinTolerance, row, 1)

        row += 1
        self.spinFillColor = QtWidgets.QDoubleSpinBox()
        self.spinFillColor.setRange(0.0, 1.0)
        self.spinFillColor.setSingleStep(0.1)
        self.spinFillColor.setValue(1.0)
        layout.addWidget(QtWidgets.QLabel("Fill Color:"), row, 0)
        layout.addWidget(self.spinFillColor, row, 1)

        self.setLayout(layout)

    @staticmethod
    def operate(mat: np.ndarray, image: np.ndarray, minColor: int, maxColor: int, tolerance: int, fillColor: int) -> np.ndarray:
        h, w = image.shape[:2]
        channels = 1 if len(image.shape) < 3 else image.shape[2]
        match channels:
            case 3: image = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
            case 4: image = cv.cvtColor(image, cv.COLOR_BGRA2GRAY)

        padTop, padLeft = 0, 0
        padBottomInv, padRightInv = h, w  # Inverted (start index of padding)

        # Compare to top left corner
        padColor = int(image[0, 0])
        if minColor <= padColor <= maxColor:
            padColorMin = max(padColor-tolerance, minColor)
            padColorMax = min(padColor+tolerance, maxColor)

            for padTop in range(h):
                row = image[padTop]
                if not np.all((row >= padColorMin) & (row <= padColorMax)):
                    break

            for padLeft in range(w):
                col = image[:, padLeft]
                if not np.all((col >= padColorMin) & (col <= padColorMax)):
                    break

            mat[0:padTop, :] = fillColor
            mat[:, 0:padLeft] = fillColor

        # Compare to bottom right corner
        padColor = int(image[h-1, w-1])
        if minColor <= padColor <= maxColor:
            padColorMin = max(padColor-tolerance, minColor)
            padColorMax = min(padColor+tolerance, maxColor)

            for padBottomInv in range(h-1, -1, -1):
                row = image[padBottomInv]
                if not np.all((row >= padColorMin) & (row <= padColorMax)):
                    break

            for padRightInv in range(w-1, -1, -1):
                col = image[:, padRightInv]
                if not np.all((col >= padColorMin) & (col <= padColorMax)):
                    break

            mat[padBottomInv+1:h, :] = fillColor
            mat[:, padRightInv+1:w] = fillColor

        return mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        minColor = self.spinMinColor.value()
        maxColor = self.spinMaxColor.value()
        tolerance = self.spinTolerance.value()
        fillColor = self.spinFillColor.value()

        minColor8Bit = round(minColor*255)
        maxColor8Bit = round(maxColor*255)
        tolerance8Bit = round(tolerance*255)
        fillColor8Bit = round(fillColor*255)

        image = qtlib.qimageToNumpy( self.maskTool._imgview.image.pixmap().toImage() )
        image[..., :3] = image[..., 2::-1] # Convert RGB(A) -> BGR(A)

        mat = self.maskItem.toNumpy()
        mat = self.operate(mat, image, minColor8Bit, maxColor8Bit, tolerance8Bit, fillColor8Bit)
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        macroItem = self.maskTool.macro.addOperation(
            mask_macro.MacroOp.DetectPad, minColor=minColor8Bit, maxColor=maxColor8Bit, tolerance=tolerance8Bit, fillColor=fillColor8Bit
        )
        self.maskTool._toolbar.addHistory(f"Detect Pad ({fillColor:.2f})", mat, macroItem)



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
        macroItem = self.maskTool.macro.addOperation(mask_macro.MacroOp.BlendLayers, mode=mode, srcLayer=srcMatIndex)
        self.maskTool._toolbar.addHistory(f"Blend Layers ({mode})", destMat, macroItem)



class ColorConditionMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.spinMinColor = QtWidgets.QDoubleSpinBox()
        self.spinMinColor.setRange(0.0, 1.0)
        self.spinMinColor.setSingleStep(0.1)
        self.spinMinColor.setValue(0.0)
        layout.addWidget(QtWidgets.QLabel("Color Min:"), row, 0)
        layout.addWidget(self.spinMinColor, row, 1)

        row += 1
        self.spinMaxColor = QtWidgets.QDoubleSpinBox()
        self.spinMaxColor.setRange(0.0, 1.0)
        self.spinMaxColor.setSingleStep(0.1)
        self.spinMaxColor.setValue(1.0)
        self.spinMaxColor.setToolTip("The maximum is disabled when it's smaller than the minimum.")
        layout.addWidget(QtWidgets.QLabel("Color Max:"), row, 0)
        layout.addWidget(self.spinMaxColor, row, 1)

        self.setLayout(layout)

    @staticmethod
    def operate(mat: np.ndarray, minColor: int, maxColor: int) -> np.ndarray:
        if maxColor < minColor:
            maxColor = 1000

        if mat.min() >= minColor and mat.max() <= maxColor:
            fillColor = 255
        else:
            fillColor = 0

        mat.fill(fillColor)
        return mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        min = self.spinMinColor.value()
        max = self.spinMaxColor.value()

        minColor = round(min*255)
        maxColor = round(max*255)

        mat = self.maskItem.toNumpy()
        mat = self.operate(mat, minColor, maxColor)
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        macroItem = self.maskTool.macro.addOperation(mask_macro.MacroOp.CondColor, minColor=minColor, maxColor=maxColor)

        colorRangeText = f"{min:.2f} - {max:.2f}" if max > min else f"{min:.2f}"
        self.maskTool._toolbar.addHistory(f"Color Condition ({colorRangeText})", mat, macroItem)


class AreaConditionMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.spinMinArea = QtWidgets.QDoubleSpinBox()
        self.spinMinArea.setRange(0.0, 1.0)
        self.spinMinArea.setSingleStep(0.05)
        self.spinMinArea.setValue(0.0)
        layout.addWidget(QtWidgets.QLabel("Area Min %:"), row, 0)
        layout.addWidget(self.spinMinArea, row, 1)

        row += 1
        self.spinMaxArea = QtWidgets.QDoubleSpinBox()
        self.spinMaxArea.setRange(0.0, 1.0)
        self.spinMaxArea.setSingleStep(0.05)
        self.spinMaxArea.setValue(1.0)
        self.spinMaxArea.setToolTip("The maximum is disabled when it's smaller than the minimum.")
        layout.addWidget(QtWidgets.QLabel("Area Max %:"), row, 0)
        layout.addWidget(self.spinMaxArea, row, 1)

        self.setLayout(layout)

    @staticmethod
    def operate(mat: np.ndarray, minArea: float, maxArea: float) -> np.ndarray:
        h, w = mat.shape
        count = np.count_nonzero(mat)
        filledArea = count / (w * h)

        if maxArea < minArea:
            maxArea = 1.1

        fillColor = 255 if (minArea <= filledArea <= maxArea) else 0
        mat.fill(fillColor)
        return mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        minArea = self.spinMinArea.value()
        maxArea = self.spinMaxArea.value()

        mat = self.maskItem.toNumpy()
        mat = self.operate(mat, minArea, maxArea)
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        macroItem = self.maskTool.macro.addOperation(mask_macro.MacroOp.CondArea, minArea=minArea, maxArea=maxArea)

        areaRangeText = f"{minArea:.2f} - {maxArea:.2f}" if maxArea > minArea else f"{minArea:.2f}"
        self.maskTool._toolbar.addHistory(f"Area Condition ({areaRangeText})", mat, macroItem)


class RegionConditionMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.spinMinRegions = QtWidgets.QSpinBox()
        self.spinMinRegions.setRange(0, 16384)
        self.spinMinRegions.setValue(1)
        layout.addWidget(QtWidgets.QLabel("Regions Min:"), row, 0)
        layout.addWidget(self.spinMinRegions, row, 1)

        row += 1
        self.spinMaxRegions = QtWidgets.QSpinBox()
        self.spinMaxRegions.setRange(0, 16384)
        self.spinMaxRegions.setValue(0)
        self.spinMaxRegions.setToolTip("The maximum is disabled when it's smaller than the minimum.")
        layout.addWidget(QtWidgets.QLabel("Regions Max:"), row, 0)
        layout.addWidget(self.spinMaxRegions, row, 1)

        self.setLayout(layout)

    @staticmethod
    def operate(mat: np.ndarray, minRegions: int, maxRegions: int) -> np.ndarray:
        numRegions, labels = cv.connectedComponents(mat, None, 8, cv.CV_16U)
        numRegions -= 1

        if maxRegions < minRegions:
            maxRegions = numRegions

        fillColor = 255 if (minRegions <= numRegions <= maxRegions) else 0
        mat.fill(fillColor)
        return mat

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        minRegions = self.spinMinRegions.value()
        maxRegions = self.spinMaxRegions.value()

        mat = self.maskItem.toNumpy()
        mat = self.operate(mat, minRegions, maxRegions)
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        macroItem = self.maskTool.macro.addOperation(mask_macro.MacroOp.CondRegions, minRegions=minRegions, maxRegions=maxRegions)

        regionRangeText = f"{minRegions} - {maxRegions}" if maxRegions > minRegions else str(minRegions)
        self.maskTool._toolbar.addHistory(f"Region Condition ({regionRangeText})", mat, macroItem)



class MacroMaskOperation(MaskOperation):
    def __init__(self, maskTool, name, path):
        super().__init__(maskTool)
        self.macroName = name
        self.macroPath = path
        self.running = False

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        btnInspect = QtWidgets.QPushButton("Inspect...")
        btnInspect.clicked.connect(self.inspectMacro)
        layout.addWidget(btnInspect, row, 0, 1, 2)

        self.setLayout(layout)

    @Slot()
    def inspectMacro(self):
        from lib.mask_macro_vis import MacroInspectWindow
        win = MacroInspectWindow(self, self.macroName, self.macroPath)
        win.exec()


    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        imgPath = self.maskTool._imgview.image.filepath
        if not imgPath:
            return

        # Don't record macros into macros
        if self.maskTool.macro.recording:
            self.maskTool.tab.statusBar().showColoredMessage("Cannot run macros while recording macros", False)
            return

        layerIndex = self.maskTool.layers.index(self.maskTool.maskItem)

        task = MacroMaskTask(self.macroPath, self.macroName, imgPath, layerIndex, self.maskTool.layers)
        task.signals.done.connect(self.onDone)
        task.signals.fail.connect(self.onFail)

        from infer.inference import Inference
        Inference().queueTask(task)
        self.maskTool.tab.statusBar().showMessage("Running macro...", 0)

        # Store layers so result can be loaded when image is changed
        self.maskTool.setEdited()

    @Slot()
    def onDone(self, imgPath: str, macroName: str, layerItems: list, layerMats: list[np.ndarray], layerChanged: list[bool]):
        self.running = False
        historyTitle = f"Macro ({macroName})"

        # Undoing the macro in one layer will disable it for all other layers too!
        # Recording macros into macros could lead to all kind of weird interactions and mess up layers.
        # --> This could work: Create special item in Macro that allows setting which layers the results are applied to.
        #     This special item is referenced by history entries and control result application per layer.
        #macroItem = self.maskTool.macro.addOperation(MacroOp.Macro, name=macroName)

        # TODO: If only one layer is returned, always apply that one to current layer without modifying/adding/deleting other layers?
        #       Though, there are use cases where this interferes.

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

        self.maskTool.tab.statusBar().showColoredMessage(f"Finished macro: {macroName}", True)

    @Slot()
    def onFail(self, msg: str):
        self.running = False
        self.maskTool.tab.statusBar().showColoredMessage(f"Macro failed: {msg}", False, 0)
        print(msg)



class DetectMaskOperation(MaskOperation):
    def __init__(self, maskTool, preset: str):
        super().__init__(maskTool)
        self.preset = preset
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

        row += 1
        layout.addWidget(QtWidgets.QLabel("Classes:"), row, 0)

        btnGetClasses = QtWidgets.QPushButton("Retrieve")
        btnGetClasses.clicked.connect(self.retrieveClassNames)
        layout.addWidget(btnGetClasses, row, 1)

        row += 1
        classes = ", ".join( Config.inferMaskPresets[self.preset].get("classes") )
        self.txtClasses = QtWidgets.QPlainTextEdit()
        self.txtClasses.setPlainText(classes)
        layout.addWidget(self.txtClasses, row, 0, 1, 2)

        self.setLayout(layout)

    @property
    def classes(self) -> list[str]:
        classes = (name.strip() for name in self.txtClasses.toPlainText().split(","))
        return [name for name in classes if name]

    @Slot()
    def retrieveClassNames(self):
        config = Config.inferMaskPresets[self.preset]
        task = RetrieveDetectionClassesTask(config)
        task.signals.done.connect(self.onRetrieveClassesDone)
        task.signals.fail.connect(self.onRetrieveClassesFail)

        from infer.inference import Inference
        Inference().queueTask(task)
        self.maskTool.tab.statusBar().showMessage("Loading detection model...", 0)

    @Slot()
    def onRetrieveClassesDone(self, classes: list[str]):
        text = ", ".join(classes)
        self.txtClasses.setPlainText(text)
        self.maskTool.tab.statusBar().showColoredMessage(f"Retrieved {len(classes)} classes", True)

    @Slot()
    def onRetrieveClassesFail(self, msg: str):
        self.maskTool.tab.statusBar().showColoredMessage(f"Failed to retrieve classes: {msg}", False, 0)
        print(msg)


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
        config = Config.inferMaskPresets[self.preset]

        task = MaskTask(MaskTask.MODE_DETECT, self.maskTool.maskItem, config, self.classes, imgPath, color)
        task.signals.loaded.connect(self.onLoaded)
        task.signals.done.connect(self.onDone)
        task.signals.fail.connect(self.onFail)

        from infer.inference import Inference
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
        threshold = self.spinThreshold.value()
        classes = set(self.classes)

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
        macroItem = self.maskTool.macro.addOperation(mask_macro.MacroOp.Detect, preset=self.preset, color=colorFill, threshold=threshold)
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

        config = Config.inferMaskPresets[self.preset]
        if "classes" in config:
            row += 1
            layout.addWidget(QtWidgets.QLabel("Classes:"), row, 0)

            row += 1
            classes = ", ".join(config["classes"])
            self.txtClasses = QtWidgets.QPlainTextEdit()
            self.txtClasses.setPlainText(classes)
            qtlib.setTextEditHeight(self.txtClasses, 3)
            layout.addWidget(self.txtClasses, row, 0, 1, 2)

        self.setLayout(layout)

    @property
    def classes(self) -> list[str]:
        if not hasattr(self, "txtClasses"):
            return []
        classes = (name.strip() for name in self.txtClasses.toPlainText().split(","))
        return [name for name in classes if name]

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
        config = Config.inferMaskPresets[self.preset]

        task = MaskTask(MaskTask.MODE_SEGMENT, self.maskItem, config, self.classes, imgPath, color)
        task.signals.loaded.connect(self.onLoaded)
        task.signals.done.connect(self.onDone)
        task.signals.fail.connect(self.onFail)

        from infer.inference import Inference
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

        macroItem = self.maskTool.macro.addOperation(mask_macro.MacroOp.Segment, preset=self.preset, color=color)
        historyTitle = f"Segmentation ({color:.2f})"
        maskItem.addHistory(historyTitle, mat, macroItem)
        if maskItem == self.maskItem:
            self.maskTool._toolbar.setHistory(maskItem)
            self.maskTool.setEdited()

        self.maskTool.tab.statusBar().showColoredMessage("Segmentation finished", True)

    @Slot()
    def onFail(self, msg: str):
        self.running = False
        self.maskTool.tab.statusBar().showColoredMessage(f"Segmentation failed: {msg}", False, 0)
        print(msg)



class MaskTask(QRunnable):
    MODE_DETECT  = "detect"
    MODE_SEGMENT = "segment"

    class Signals(QObject):
        loaded = Signal()
        done = Signal(object, str, float, object)
        fail = Signal(str)

    def __init__(self, mode: str, maskItem, config: dict, classes: list[str], imgPath: str, color: float):
        super().__init__()
        self.setAutoDelete(False)

        self.signals  = self.Signals()
        self.mode     = mode
        self.maskItem = maskItem
        self.config   = config
        self.classes  = classes
        self.imgPath  = imgPath
        self.color    = color

        self.imgUploader = None

    @Slot()
    def run(self):
        try:
            from infer.inference import Inference, ImageUploader
            inferProc = Inference().proc
            inferProc.start()

            if inferProc.procCfg.remote:
                self.imgUploader = ImageUploader([self.imgPath])

            inferProc.setupMasking(self.config)
            self.signals.loaded.emit()

            if self.mode == self.MODE_DETECT:
                result = inferProc.maskBoxes(self.config, self.classes, self.imgPath)
            else:
                result = inferProc.mask(self.config, self.classes, self.imgPath)

            self.signals.done.emit(self.maskItem, self.imgPath, self.color, result)
        except Exception as ex:
            import traceback
            traceback.print_exc()
            self.signals.fail.emit(str(ex))
        finally:
            if self.imgUploader:
                self.imgUploader.imageDone.emit(self.imgPath)



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
            macro = mask_macro.MaskingMacro()
            macro.loadFrom(self.macroPath)
            layerMats, layerChanged = macro.run(self.imgPath, self.layerMats, self.currentLayerIndex)

            self.signals.done.emit(self.imgPath, self.macroName, self.layers, layerMats, layerChanged)
        except Exception as ex:
            import traceback
            traceback.print_exc()
            self.signals.fail.emit(str(ex))



class RetrieveDetectionClassesTask(QRunnable):
    class Signals(QObject):
        done = Signal(list) # classes: list
        fail = Signal(str)

    def __init__(self, config: dict):
        super().__init__()
        self.signals = self.Signals()
        self.config = config

    @Slot()
    def run(self):
        try:
            from infer.inference import Inference
            inferProc = Inference().proc
            inferProc.start()

            classes = inferProc.getDetectClasses(self.config)
            self.signals.done.emit(classes)
        except Exception as ex:
            import traceback
            traceback.print_exc()
            self.signals.fail.emit(str(ex))
