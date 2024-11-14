from typing import ForwardRef
from typing_extensions import override
from PySide6.QtCore import Qt, Slot, Signal, QEvent, QRect, QRectF, QPointF, QSignalBlocker, QRunnable, QObject, QThreadPool
from PySide6.QtGui import QPixmap, QImage, QTransform, QPainter, QPen, QColor, QTabletEvent, QPointingDevice
from PySide6 import QtWidgets
import cv2 as cv
import numpy as np
from lib.filelist import DataKeys
from ui.export_settings import ExportPath
from config import Config
from .view import ViewTool

MaskItem = ForwardRef("MaskItem")

# Multiple layers (rgba as 4 alpha channels; binary masks: set layer color)
# Blur tools (gaussian)
# Auto masking (RemBg, clipseg, yolo ...)
# Invert mask
# Brushes: Set size, solid brush, blurry brush, subtractive brush (eraser) ...
# Flood fill

# For converting to CV Mat: use pixmap.bits() ? ask SuperNova
# Save layer names to file meta data

# Undo/Redo with Ctrl+Z/Ctrl+Y, store vector data

# OneTrainer uses filename suffix "-masklabel.png"
# kohya-ss has the masks in separate folder: conditioning_data_dir = '...'


class MaskTool(ViewTool):
    BUTTON_DRAW = Qt.MouseButton.LeftButton
    BUTTON_ERASE = Qt.MouseButton.RightButton

    def __init__(self, tab):
        super().__init__(tab)
        self.maskItem: MaskItem = None
        self.layers: list[MaskItem] = None

        self._drawing = False
        self._lastPoint: QPointF = None

        self._painter = QPainter()
        self._penColor = QColor()
        self._pen = QPen()
        self._pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self._pen.setWidth(10)

        cursorPen = QPen(QColor(0, 255, 255, 255))
        cursorPen.setStyle(Qt.PenStyle.DashLine)
        cursorPen.setDashPattern([2,3])
        self._cursor = QtWidgets.QGraphicsEllipseItem()
        self._cursor.setPen(cursorPen)
        self._origCursor = None

        self._toolbar = MaskToolBar(self)


    def createMask(self, name: str = None) -> MaskItem:
        if not name:
            name = "Layer 0"

        imgview = self._imgview
        pixmap = imgview.image.pixmap()

        mask = QImage(pixmap.size(), QImage.Format.Format_Grayscale8) # QImage::Format_ARGB32_Premultiplied ? (faster with alpha blending)
        mask.fill(Qt.GlobalColor.black)

        maskItem = MaskItem(name, mask)
        maskItem.updateTransform(imgview.image)
        return maskItem

    def loadLayers(self):
        filelist = self.tab.filelist
        if not (currentFile := filelist.getCurrentFile()):
            return

        self.layers = filelist.getData(currentFile, DataKeys.MaskLayers)
        if self.layers:
            index = filelist.getData(currentFile, DataKeys.MaskIndex)
            self.maskItem = self.layers[index]

        else:
            self.maskItem = self.createMask()
            self.layers = [ self.maskItem ]
            index = 0

        self._imgview.scene().addItem(self.maskItem)
        self._imgview.updateScene()

        self._toolbar.setLayers(self.layers, index)

    def storeLayers(self):
        filelist = self.tab.filelist
        if not (currentFile := filelist.getCurrentFile()):
            return

        index = self.layers.index(self.maskItem)

        filelist.setData(currentFile, DataKeys.MaskLayers, self.layers)
        filelist.setData(currentFile, DataKeys.MaskIndex, index)
        filelist.setData(currentFile, DataKeys.MaskState, DataKeys.IconStates.Changed)

    @Slot()
    def addLayer(self):
        if not self.tab.filelist.getCurrentFile():
            return

        index = len(self.layers)
        mask = self.createMask(f"Layer {index}")
        self.layers.append(mask)

        self.setLayer(index)
        self._toolbar.setLayers(self.layers, index)
        self.setEdited()
    
    @Slot()
    def setLayer(self, index: int):
        filelist = self.tab.filelist
        if not (currentFile := filelist.getCurrentFile()):
            return
        
        if not (0 <= index < len(self.layers)):
            return

        if self.maskItem:
            self._imgview.scene().removeItem(self.maskItem)

        self.maskItem = self.layers[index]
        self._imgview.scene().addItem(self.maskItem)
        self._imgview.scene().update()

        filelist.setData(currentFile, DataKeys.MaskIndex, index)

    @Slot()
    def deleteCurrentLayer(self):
        filelist = self.tab.filelist
        if not (currentFile := filelist.getCurrentFile()):
            return

        index = self.layers.index(self.maskItem)
        del self.layers[index]

        if not self.layers:
            self.layers.append( self.createMask() )

        index = max(index-1, 0)
        self.setLayer(index)
        self._toolbar.setLayers(self.layers, index)

        self.setEdited()


    # Remember: When exporting mask, simply delete the FileList Data and set icon state.
    def setEdited(self):
        self.storeLayers()


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
        if self.maskItem:
            rect = self.maskItem.mapToParent(0, 0, w, w)
            rect = self._imgview.mapFromScene(rect).boundingRect()
            w = rect.width()

        wHalf = w * 0.5
        self._cursor.setRect(pos.x()-wHalf, pos.y()-wHalf, w, w)
        self._imgview.scene().update()


    def mapPosToImage(self, eventPos):
        imgpos = self._imgview.mapToScene(eventPos.toPoint())
        imgpos = self.maskItem.mapFromParent(imgpos)
        return imgpos


    def drawStart(self, eventPos, pressure: float, erase=False):
        self._drawing = True
        self._lastPoint = self.mapPosToImage(eventPos)

        self._painter.begin(self.maskItem.mask)
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
        if self._drawing:
            self._drawing = False
            self._painter.end()
            self.setEdited()


    @Slot()
    def exportMask(self):
        if not self.layers:
            return

        self.tab.statusBar().showMessage("Saving mask...")

        masks: list[np.ndarray] = list()
        for layerItem in self.layers:
            image = layerItem.image
            array = np.frombuffer(image.constBits(), dtype=np.uint8)
            array.shape = (image.height(), image.width())
            masks.append(array)

        # Can't write images with only 2 channels. Need 1/3/4 channels.
        if len(masks) == 2:
            masks.append( np.zeros_like(masks[0]) )

        # Reverse order of first 3 layers to convert from BGR(A) to RGB(A)
        masks[:3] = masks[2::-1]

        # BGRA, shape: (h, w, channels)
        # Creates a copy of the data.
        combined = np.dstack(masks)

        exportPath = ExportPath()
        exportPath.suffix = "-masklabel"
        saveParams = [cv.IMWRITE_PNG_COMPRESSION, 9]

        #exportPath.extension = "webp"
        #saveParams = [cv.IMWRITE_WEBP_QUALITY, 100]

        currentFile = self.tab.filelist.getCurrentFile()
        destFile = exportPath.getExportPath(currentFile)

        task = MaskExportTask(currentFile, destFile, combined, saveParams)
        task.signals.done.connect(self.onExportDone, Qt.ConnectionType.BlockingQueuedConnection)
        task.signals.fail.connect(self.onExportFailed, Qt.ConnectionType.BlockingQueuedConnection)
        QThreadPool.globalInstance().start(task)

        self.tab.filelist.setData(currentFile, DataKeys.MaskState, DataKeys.IconStates.Saved)
        

    @Slot()
    def onExportDone(self, imgFile, maskFile):
        message = f"Saved mask to: {maskFile}"
        print(message)
        self.tab.statusBar().showColoredMessage(message, success=True)
        
        # Remove masks
        # TODO: Which image file to load when changing back to this image?
        #       Remember exported file? Don't export multiple files, but overwrite the one with _mask suffix?
        state = self.tab.filelist.getData(imgFile, DataKeys.MaskState)
        if state == DataKeys.IconStates.Saved:
            self.tab.filelist.removeData(imgFile, DataKeys.MaskLayers)

        #self._toolbar.updateExport()
    
    @Slot()
    def onExportFailed(self):
        self.tab.statusBar().showColoredMessage("Export failed", success=False)


    def onFileChanged(self, currentFile):
        if self._drawing:
            self._drawing = False
            self._painter.end()

        if self.maskItem:
            self._imgview.scene().removeItem(self.maskItem)
        self.loadLayers()
        self.updateCursor(self._cursor.rect().center())

    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)


    # === Tool Interface ===

    @override
    def getToolbar(self):
        return self._toolbar

    @override
    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        imgview.filelist.addListener(self)

        self._origCursor = imgview.cursor()
        imgview.setCursor(Qt.CursorShape.BlankCursor)
        imgview._guiScene.addItem(self._cursor)

        self.loadLayers()

    @override
    def onDisabled(self, imgview):
        super().onDisabled(imgview)
        imgview.filelist.removeListener(self)

        self.drawEnd()

        imgview.setCursor(self._origCursor)
        self._origCursor = None
        imgview._guiScene.removeItem(self._cursor)

        if self.maskItem:
            imgview.scene().removeItem(self.maskItem)
        
        self.maskItem = None
        self.layers = None

    @override
    def onSceneUpdate(self):
        super().onSceneUpdate()
        self.updateCursor(self._cursor.rect().center())

        if self.maskItem:
            self.maskItem.updateTransform(self._imgview.image)
            
    @override
    def onResize(self, event):
        super().onResize(event)

        if self.maskItem:
            self.maskItem.updateTransform(self._imgview.image)


    @override
    def onMousePress(self, event) -> bool:
        # CTRL pressed -> Use default controls (pan)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier or not self.maskItem:
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
        self.drawEnd()

    @override
    def onMouseMove(self, event):
        super().onMouseMove(event)
        self.updateCursor(event.position())

        if self._drawing and self.maskItem:
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
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier or not self.maskItem:
            return False

        pressure = event.pressure()
        #pressure = event.pressure() ** 1.0
        
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



class MaskItem(QtWidgets.QGraphicsRectItem):
    def __init__(self, name: str, image: QImage):
        super().__init__()
        self.setOpacity(0.7)
        self.setImage(image)
        self.name = name
    
    @property
    def mask(self) -> QImage:
        return self.image

    def paint(self, painter, option, widget=None):
        painter.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(self.rect(), self.image)

    def setImage(self, image: QImage):
        self.image = image
        self.setRect( image.rect().toRectF() )
        self.update()

    def updateTransform(self, baseImage):
        self.setTransform(baseImage.transform())
        self.setRect(baseImage.boundingRect())



class MaskToolBar(QtWidgets.QToolBar):
    def __init__(self, maskTool):
        super().__init__("Mask")
        self.maskTool: MaskTool = maskTool

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self._buildLayers())
        layout.addWidget(self._buildBrush())
        layout.addWidget(self._buildOps())
        layout.addWidget(self._buildAutoMask())

        btnExport = QtWidgets.QPushButton("Export")
        btnExport.clicked.connect(self.maskTool.exportMask)
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
        self.cboLayer.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.cboLayer.currentIndexChanged.connect(self.maskTool.setLayer)
        self.cboLayer.editTextChanged.connect(self.renameLayer)
        layout.addWidget(self.cboLayer, row, 0, 1, 2)

        row += 1
        self.btnAddLayer = QtWidgets.QPushButton("Add")
        self.btnAddLayer.clicked.connect(self.maskTool.addLayer)
        layout.addWidget(self.btnAddLayer, row, 0)

        self.btnDeleteLayer = QtWidgets.QPushButton("Delete")
        self.btnDeleteLayer.clicked.connect(self.maskTool.deleteCurrentLayer)
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
        self.cboFilter.addItem("Invert", "invert")
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


    def setLayers(self, layers: list[MaskItem], selectedIndex: int):
        with QSignalBlocker(self.cboLayer):
            self.cboLayer.clear()
            for mask in layers:
                self.cboLayer.addItem(mask.name, mask)
            self.cboLayer.setCurrentIndex(selectedIndex)
        
        self.btnAddLayer.setEnabled(len(layers) < 4)


    @Slot()
    def renameLayer(self, name: str):
        index = self.cboLayer.currentIndex()
        self.cboLayer.setItemText(index, name)
        self.cboLayer.itemData(index).name = name



class MaskExportTask(QRunnable):
    class ExportTaskSignals(QObject):
        done = Signal(str, str)
        fail = Signal()

        def __init__(self):
            super().__init__()

    def __init__(self, srcFile, destFile, mask, saveParams):
        super().__init__()
        self.signals = self.ExportTaskSignals()

        self.srcFile = srcFile
        self.destFile = destFile
        self.mask = mask
        self.saveParams = saveParams

    @Slot()
    def run(self):
        try:
            ExportPath.createFolders(self.destFile)
            cv.imwrite(self.destFile, self.mask, self.saveParams)
            self.signals.done.emit(self.srcFile, self.destFile)
        except Exception as ex:
            print("Error while exporting:")
            print(ex)
            self.signals.fail.emit()
        finally:
            del self.mask
