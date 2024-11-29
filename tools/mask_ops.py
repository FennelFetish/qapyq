from typing_extensions import override
from PySide6.QtCore import Qt, Slot, QPointF, QRectF, QSignalBlocker, QRunnable, QObject, Signal
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


    def mapPosToImage(self, pos: QPointF) -> QPointF:
        scenepos = self.imgview.mapToScene(pos.toPoint())
        return self.maskItem.mapFromParent(scenepos)

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
        pos = self.mapPosToImage(pos)
        r = 10

        color = self.spinFillColor.value() * 255.0
        upDiff = self.spinUpperDiff.value() * 255.0
        loDiff = self.spinLowerDiff.value() * 255.0
        
        # TODO: Convert image to array in onEnabled
        pixmap = self.maskTool._imgview.image.pixmap()
        cutX, cutY = int(pos.x()-r), int(pos.y()-r)
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
        pos = self.mapPosToImage(pos)
        r = 10

        color = self.spinFillColor.value() * 255.0
        upDiff = self.spinUpperDiff.value() * 255.0
        loDiff = self.spinLowerDiff.value() * 255.0

        # TODO: Convert image to array in onEnabled
        pixmap = self.maskTool._imgview.image.pixmap()
        cutX, cutY = int(pos.x()-r), int(pos.y()-r)
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

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        pos = self.mapPosToImage(pos).toPoint()
        pos = (pos.x(), pos.y())

        color = 0 if alt else self.spinFillColor.value()
        upperDiff = self.spinUpperDiff.value() * 255.0
        lowerDiff = self.spinLowerDiff.value() * 255.0

        # TODO: Calc upper/lower diff based on selected start point's pixel value
        mat = self.maskItem.toNumpy()
        retval, img, mask, rect = cv.floodFill(mat, None, pos, color*255, lowerDiff, upperDiff)#, cv.FLOODFILL_FIXED_RANGE)
        #print(f"flood fill result: {retval}, img: {img}, mask: {mask}, rect: {rect}")
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        self.maskTool._toolbar.addHistory(f"Flood Fill ({color:.2f})", mat)



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
        self.maskTool._toolbar.addHistory(f"Clear ({color:.2f})", mat)



class InvertMaskOperation(MaskOperation):
    def __init__(self, maskTool):
        super().__init__(maskTool)

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        mat = self.maskItem.toNumpy()
        mat = 255 - mat
        self.maskItem.fromNumpy(mat)

        self.maskTool.setEdited()
        self.maskTool._toolbar.addHistory("Invert", mat)



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

    @override
    def onMousePress(self, pos, pressure: float, alt=False):
        # TODO: Grow/shrink depending on mouse button?
        r = self.spinRadius.value()
        size = r*2 + 1
        kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (size, size))

        borderType = cv.BORDER_CONSTANT
        borderVal  = (0,)

        mat = self.maskItem.toNumpy()
        mode = self.cboMode.currentData()
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

        self.maskItem.fromNumpy(mat)
        self.maskTool.setEdited()
        self.maskTool._toolbar.addHistory(f"Morphology ({mode} {r})", mat)



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
        radius = self.spinRadius.value()
        mat = self.maskItem.toNumpy()

        blurBorder  = cv.BORDER_ISOLATED
        morphBorder = cv.BORDER_CONSTANT
        borderVal   = (0,)

        mode = self.cboMode.currentData()
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
        
        self.maskItem.fromNumpy(mat)
        self.maskTool.setEdited()
        self.maskTool._toolbar.addHistory(f"Gaussian Blur ({mode} {radius})", mat)



class DetectMaskOperation(MaskOperation):
    def __init__(self, maskTool, config):
        super().__init__(maskTool)
        self.config = config
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
    def onDone(self, maskItem, imgPath: str, color: float, boxes):
        self.running = False

        colorFill = round(color * 255)
        classes = set(self.config["classes"])
        threshold = self.spinThreshold.value()

        mat = maskItem.toNumpy()
        h, w = mat.shape

        detections = {}
        detectionsApplied = 0
        for box in boxes:
            name = box["name"]
            if box["confidence"] < threshold or (classes and name not in classes):
                continue
            detections[name] = detections.get(name, 0) + 1
            detectionsApplied += 1

            p0x, p0y = box["p0"]
            p0x, p0y = round(p0x*w), round(p0y*h)

            p1x, p1y = box["p1"]
            p1x, p1y = round(p1x*w)+1, round(p1y*h)+1

            mat[p0y:p1y, p0x:p1x] = colorFill

        maskItem.fromNumpy(mat)
        historyTitle = f"Detect ({color:.2f})"
        if maskItem == self.maskItem:
            self.maskTool.setEdited()
            self.maskTool._toolbar.addHistory(historyTitle, mat)
        else:
            maskItem.addHistory(historyTitle, mat)

        if len(boxes):
            msg = f"{len(boxes)} detections, {detectionsApplied} applied"
            if detections:
                detections = ", ". join(f"{count}x {name}" for name, count in detections.items())
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
    def __init__(self, maskTool, config):
        super().__init__(maskTool)
        self.config = config
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
    def onDone(self, maskItem, imgPath: str, color: float, maskBytes):
        self.running = False

        mask = maskItem.toNumpy()
        h, w = mask.shape

        result = np.frombuffer(maskBytes, dtype=np.uint8)
        result.shape = (h, w)

        if color < 0.9999:
            resultFloat = result.astype(np.float32)
            resultFloat *= color
            result = resultFloat.astype(np.uint8)

        np.maximum(mask, result, out=mask)
        maskItem.fromNumpy(mask)

        historyTitle = f"Segmentation ({color:.2f})"
        if maskItem == self.maskItem:
            self.maskTool.setEdited()
            self.maskTool._toolbar.addHistory(historyTitle, mask)
        else:
            maskItem.addHistory(historyTitle, mask)
        
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
