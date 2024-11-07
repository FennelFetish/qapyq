import numpy as np
from qtpy import QtWidgets
from typing_extensions import override
from PySide6.QtGui import QPixmap, QImage, QTransform, QPainter, QPen, QColor, QTabletEvent, QPointingDevice
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem
from PySide6.QtCore import Qt, Slot, QEvent, QRect, QRectF, QPointF, QSignalBlocker
from .view import ViewTool


# Multiple layers (rgba as 4 alpha channels; binary masks: set layer color)
# Blur tools (gaussian)
# Auto masking (RemBg, clipseg, yolo ...)
# Invert mask
# Brushes: Set size, solid brush, blurry brush, subtractive brush (eraser) ...
# Flood fill

# Performance is bad with very large images. Make grid of patches? Combine them when saving or applying filters.

# For converting to CV Mat: use pixmap.bits() ? ask SuperNova


class MaskTool(ViewTool):
    BUTTON_DRAW = Qt.MouseButton.LeftButton
    BUTTON_ERASE = Qt.MouseButton.RightButton

    def __init__(self, tab):
        super().__init__(tab)
        
        self.mask: QImage = None
        self.maskItem: MaskItem = None

        self._drawing = False
        self._lastPoint: QPointF = None

        self._painter = QPainter()
        self._penColor = QColor()
        self._pen = QPen()
        self._pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self._pen.setWidth(10)

        cursorPen = QPen(QColor(0, 255, 255, 255))
        cursorPen.setStyle(Qt.PenStyle.DashLine)
        cursorPen.setDashPattern([2,2])
        self._cursor = QtWidgets.QGraphicsEllipseItem()
        self._cursor.setPen(cursorPen)
        self._origCursor = None

        self._toolbar = MaskToolBar(self)


    def createMask(self):
        imgview = self._imgview
        pixmap = imgview.image.pixmap()
        if not pixmap:
            return
        
        self.mask = QImage(pixmap.size(), QImage.Format.Format_Grayscale8) # QImage::Format_ARGB32_Premultiplied ? (faster with alpha blending)
        self.mask.fill(Qt.GlobalColor.black)

        self.maskItem = MaskItem(self.mask)
        self.updateMaskTransform()

        imgview.scene().addItem(self.maskItem)
        imgview.updateScene()

    def updateMaskTransform(self):
        img = self._imgview.image
        self.maskItem.setTransform(img.transform())
        self.maskItem.setRect(img.boundingRect())

    def updatePen(self, pressure):
        self._penColor.setRgbF(pressure, pressure, pressure, 1.0)
        self._pen.setColor(self._penColor)
        self._painter.setPen(self._pen)

    @Slot()
    def setPenWidth(self, width: int):
        width = max(width, 1)
        self._pen.setWidth(width)
        self.updateCursor(self._cursor.rect().center())

        with QSignalBlocker(self._toolbar.spinBrushSize):
            self._toolbar.spinBrushSize.setValue(width)


    def updateCursor(self, pos: QPointF):
        w = float(self._pen.width())
        rect = self.maskItem.mapToParent(0, 0, w, w)
        rect = self._imgview.mapFromScene(rect).boundingRect()
        
        w = rect.width()
        wHalf = w * 0.5
        self._cursor.setRect(pos.x() - wHalf, pos.y() - wHalf, w, w)
        self._imgview.scene().update()


    def mapPosToImage(self, eventPos):
        imgpos = self._imgview.mapToScene(eventPos.toPoint())
        imgpos = self.maskItem.mapFromParent(imgpos)
        return imgpos


    def drawStart(self, eventPos, pressure: float, erase=False):
        self._drawing = True
        self._lastPoint = self.mapPosToImage(eventPos)

        self._painter.begin(self.mask)
        if erase:
            self._painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        else:
            self._painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Lighten)
        self._painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self.updatePen(pressure)
        self._painter.drawPoint(self._lastPoint)
        self.maskItem.update()

    def drawMove(self, eventPos, pressure: float):
        currentPoint = self.mapPosToImage(eventPos)

        # TODO: Remember last pressure and draw gradient to prevent banding effect
        self.updatePen(pressure)
        self._painter.drawLine(self._lastPoint, currentPoint)
        self.maskItem.update()

        self._lastPoint = currentPoint
        
    def drawEnd(self):
        self._drawing = False
        self._painter.end()


    # === Tool Interface ===

    @override
    def getToolbar(self):
        return self._toolbar

    @override
    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        # imgview.filelist.addListener(self)

        self._origCursor = imgview.cursor()
        imgview.setCursor(Qt.CursorShape.BlankCursor)
        imgview._guiScene.addItem(self._cursor)

        self.createMask()

    @override
    def onDisabled(self, imgview):
        super().onDisabled(imgview)
        # imgview.filelist.removeListener(self)

        imgview.setCursor(self._origCursor)
        self._origCursor = None
        imgview._guiScene.removeItem(self._cursor)

        if self.maskItem:
            imgview.scene().removeItem(self.maskItem)
        self.maskItem = None
        self.mask = None

    @override
    def onSceneUpdate(self):
        super().onSceneUpdate()
        self.updateMaskTransform()
        self.updateCursor(self._cursor.rect().center())

    @override
    def onResize(self, event):
        super().onResize(event)
        self.updateMaskTransform()


    @override
    def onMousePress(self, event) -> bool:
        # CTRL pressed -> Use default controls (pan)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return super().onMousePress(event)

        match event.button():
            case self.BUTTON_DRAW:
                self.drawStart(event.position(), 1.0)
                return True
            case self.BUTTON_ERASE:
                self.drawStart(event.position(), 1.0, True)
                return True

        return super().onMousePress(event)

    @override
    def onMouseRelease(self, event):
        # TODO: Only stop drawing if same button is released
        if self._drawing:
            self.drawEnd()

    @override
    def onMouseMove(self, event):
        self.updateCursor(event.position())

        if self._drawing and self.mask:
            self.drawMove(event.position(), 1.0)

    @override
    def onMouseWheel(self, event) -> bool:
        # CTRL pressed -> Use default controls (zoom)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return super().onMousePress(event)
        
        wheelSteps = event.angleDelta().y() / 120.0 # 8*15° standard
        width = self._pen.width()
        width += wheelSteps
        self.setPenWidth(width)
        return True


    @override
    def onMouseEnter(self, event):
        self._cursor.setVisible(True)
        self._imgview.scene().update()

    @override
    def onMouseLeave(self, event):
        self._cursor.setVisible(False)
        self._imgview.scene().update()


    @override
    def onTablet(self, event: QTabletEvent) -> bool:
        # CTRL pressed -> Use default controls (pan)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return False

        pressure = event.pressure()
        #pressure = np.power(event.pressure(), 1.0)
        
        # TODO: Handle case when stylus buttons are pressed
        match event.type():
            case QEvent.Type.TabletPress:
                pointerType = event.pointingDevice().pointerType()
                eraser = (pointerType == QPointingDevice.PointerType.Eraser)
                self.drawStart(event.position(), pressure, eraser)

            case QEvent.Type.TabletMove:
                self.updateCursor(event.position())
                self.drawMove(event.position(), pressure)

            case QEvent.Type.TabletRelease:
                self.drawEnd()

        #print("tablet event:", event)
        return True



class MaskItem(QGraphicsRectItem):
    def __init__(self, image: QImage):
        super().__init__()
        self.setOpacity(0.7)
        self.setImage(image)

    def paint(self, painter, option, widget=None):
        painter.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(self.rect(), self.image)

    def setImage(self, image: QImage):
        self.image = image
        self.setRect( self.image.rect().toRectF() )
        self.update()



class MaskToolBar(QtWidgets.QToolBar):
    def __init__(self, maskTool):
        super().__init__("Mask")
        self.maskTool = maskTool

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self._buildLayers())
        layout.addWidget(self._buildBrush())
        layout.addWidget(self._buildOps())
        layout.addWidget(self._buildAutoMask())

        btnExport = QtWidgets.QPushButton("Export")
        #btnExport.clicked.connect(self.scaleTool.exportImage)
        layout.addWidget(btnExport)
        
        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.addWidget(widget)

        self.setMaximumWidth(180)

    def _buildLayers(self):
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)

        row = 0
        self.cboLayer = QtWidgets.QComboBox()
        self.cboLayer.setEditable(True)
        layout.addWidget(self.cboLayer, row, 0, 1, 2)

        row += 1
        self.btnAddLayer = QtWidgets.QPushButton("Add")
        layout.addWidget(self.btnAddLayer, row, 0)

        self.btnDeleteLayer = QtWidgets.QPushButton("Delete")
        layout.addWidget(self.btnDeleteLayer, row, 1)

        group = QtWidgets.QGroupBox("Layers")
        group.setLayout(layout)
        return group
    
    def _buildBrush(self):
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.spinBrushSize = QtWidgets.QSpinBox()
        self.spinBrushSize.setRange(1, 1024)
        self.spinBrushSize.setSingleStep(10)
        self.spinBrushSize.setValue(self.maskTool._pen.width())
        self.spinBrushSize.valueChanged.connect(self.maskTool.setPenWidth)
        layout.addWidget(QtWidgets.QLabel("Size:"), row, 0)
        layout.addWidget(self.spinBrushSize, row, 1)

        row += 1
        self.chkBrushAntiAlias = QtWidgets.QCheckBox("Smooth")
        layout.addWidget(self.chkBrushAntiAlias, row, 0, 1, 2)

        group = QtWidgets.QGroupBox("Brush")
        group.setLayout(layout)
        return group

    def _buildOps(self):
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)

        row = 0
        self.cboFilter = QtWidgets.QComboBox()
        self.cboFilter.addItem("Fill", "fill")
        self.cboFilter.addItem("Clear", "clear")
        self.cboFilter.addItem("Linear Gradient", "gradient_linear")
        self.cboFilter.addItem("Gaussian Blur", "blur_gauss")
        layout.addWidget(self.cboFilter, row, 1, 1, 2)

        group = QtWidgets.QGroupBox("Operations")
        group.setLayout(layout)
        return group

    def _buildAutoMask(self):
        # TODO: Mask models in Model Settings. Backends: rembg, yolo, ultralytics...

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)

        row = 0
        self.cboModel = QtWidgets.QComboBox()
        self.cboModel.addItem("RemBg", "rembg")
        self.cboModel.addItem("Yolo", "yolo")
        layout.addWidget(self.cboModel, row, 1, 1, 2)

        group = QtWidgets.QGroupBox("Auto Masking")
        group.setLayout(layout)
        return group
    