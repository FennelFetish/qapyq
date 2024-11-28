import os
from typing import ForwardRef
from typing_extensions import override
from PySide6.QtCore import Qt, Slot, Signal, QEvent, QSignalBlocker, QRunnable, QObject, QThreadPool
from PySide6.QtGui import QImage, QPainter, QTabletEvent, QPointingDevice
from PySide6 import QtWidgets
import cv2 as cv
import numpy as np
from lib.filelist import DataKeys
from ui.export_settings import ExportWidget
from config import Config
from infer.model_settings import ModelSettingsWindow
from .view import ViewTool
from . import mask_ops

MaskItem = ForwardRef("MaskItem")

# Multiple layers (rgba as 4 alpha channels; binary masks: set layer color)
# Blur tools (gaussian)
# Auto masking (RemBg, clipseg, yolo ...)
# Invert mask
# Brushes: Set size, solid brush, blurry brush, subtractive brush (eraser) ...
# Flood fill

# Save layer names to file meta data

# Undo/Redo with Ctrl+Z/Ctrl+Y, store vector data

# OneTrainer uses filename suffix "-masklabel.png"
# kohya-ss has the masks in separate folder: conditioning_data_dir = '...'


class MaskTool(ViewTool):
    BUTTON_MAIN = Qt.MouseButton.LeftButton
    BUTTON_ALT = Qt.MouseButton.RightButton

    def __init__(self, tab):
        super().__init__(tab)
        self.maskItem: MaskItem = None
        self.layers: list[MaskItem] = None

        self._toolbar = MaskToolBar(self)


    def createMask(self, name: str = None) -> MaskItem:
        if not name:
            name = "Layer 0"

        imgview = self._imgview
        pixmap = imgview.image.pixmap()

        mask = QImage(pixmap.size(), QImage.Format.Format_Grayscale8)
        mask.fill(Qt.GlobalColor.black)

        maskItem = MaskItem.new(name, mask)
        maskItem.updateTransform(imgview.image)
        return maskItem

    def loadLayers(self):
        filelist = self.tab.filelist
        if not (currentFile := filelist.getCurrentFile()):
            return

        index = 0
        if layers := filelist.getData(currentFile, DataKeys.MaskLayers):
            index = filelist.getData(currentFile, DataKeys.MaskIndex)
            self.maskItem = layers[index]
        elif layers := self.loadLayersFromFile():
            self.maskItem = layers[0]
        else:
            self.maskItem = self.createMask()
            layers = [ self.maskItem ]

        self._imgview.scene().addItem(self.maskItem)
        self._imgview.updateScene()

        self.layers = layers
        self._toolbar.setLayers(layers, index)
        self._toolbar.setHistory(self.maskItem)

    def loadLayersFromFile(self):
        maskPath = self._toolbar.exportWidget.getAutoExportPath(self.tab.filelist.getCurrentFile()) # TODO: When overwrite disabled, load latest counter
        if not os.path.exists(maskPath):
            return None

        maskMat = cv.imread(maskPath, cv.IMREAD_UNCHANGED)
        if maskMat.ndim == 2:
            h, w = maskMat.shape
            maskMat.shape = (h, w, 1)
        channels = maskMat.shape[2]

        layers: list[MaskItem] = []
        indices = list(range(channels))
        indices[:3] = indices[2::-1] # Convert BGR(A) -> RGB(A)
        for i, c in enumerate(indices):
            array = np.ascontiguousarray(maskMat[:, :, c])
            maskItem = MaskItem.load(f"Layer {i}", array)
            maskItem.updateTransform(self._imgview.image)
            layers.append(maskItem)
        return layers

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
        self.maskItem.updateTransform(self._imgview.image)
        self._imgview.scene().addItem(self.maskItem)
        self._imgview.scene().update()

        self._toolbar.setHistory(self.maskItem)
        filelist.setData(currentFile, DataKeys.MaskIndex, index)

    @Slot()
    def deleteCurrentLayer(self):
        filelist = self.tab.filelist
        if not (currentFile := filelist.getCurrentFile()):
            return

        index = self.layers.index(self.maskItem)
        del self.layers[index]

        allRemoved = False
        if not self.layers:
            allRemoved = True
            self.layers.append( self.createMask() )

        index = max(index-1, 0)
        self.setLayer(index)
        self._toolbar.setLayers(self.layers, index)

        if allRemoved:
            filelist.removeData(currentFile, DataKeys.MaskLayers)
            filelist.removeData(currentFile, DataKeys.MaskIndex)
            filelist.setData(currentFile, DataKeys.MaskState, DataKeys.IconStates.Changed)
        else:
            self.setEdited()


    def setEdited(self):
        self.storeLayers()


    @Slot()
    def exportMask(self):
        if not self.layers:
            return

        exportWidget = self._toolbar.exportWidget
        currentFile = self.tab.filelist.getCurrentFile()
        destFile = exportWidget.getExportPath(currentFile)
        if not destFile:
            return

        self.tab.statusBar().showMessage("Saving mask...")

        masks: list[np.ndarray] = list()
        for layerItem in self.layers:
            image = layerItem.image
            array = np.frombuffer(image.constBits(), dtype=np.uint8)
            array.shape = (image.height(), image.bytesPerLine())

            # Remove padding
            if image.bytesPerLine() != image.width():
                array = array[:, :image.width()]

            masks.append(array)

        # Can't write images with only 2 channels. Need 1/3/4 channels.
        if len(masks) == 2:
            masks.append( np.zeros_like(masks[0]) )

        # Reverse order of first 3 layers to convert from BGR(A) to RGB(A)
        masks[:3] = masks[2::-1]

        # BGRA, shape: (h, w, channels)
        # Creates a copy of the data.
        combined = np.dstack(masks)

        # TODO: Save layer names to meta data?
        task = MaskExportTask(currentFile, destFile, combined, exportWidget.getSaveParams())
        task.signals.done.connect(self.onExportDone, Qt.ConnectionType.BlockingQueuedConnection)
        task.signals.fail.connect(self.onExportFailed, Qt.ConnectionType.BlockingQueuedConnection)
        QThreadPool.globalInstance().start(task)

        # Set state when export starts so editing while export is in progress will correctly reflect changed status.
        self.tab.filelist.setData(currentFile, DataKeys.MaskState, DataKeys.IconStates.Saved)


    @Slot()
    def onExportDone(self, imgFile, maskFile):
        message = f"Saved mask to: {maskFile}"
        print(message)
        self.tab.statusBar().showColoredMessage(message, success=True)

        # Remove masks
        # TODO: Which image file to load when changing back to this image?
        #       Remember exported file? Don't export multiple files, but overwrite the one with _mask suffix?
        #       What to do with history?
        # state = self.tab.filelist.getData(imgFile, DataKeys.MaskState)
        # if state == DataKeys.IconStates.Saved:
        #     self.tab.filelist.removeData(imgFile, DataKeys.MaskLayers)

        self._toolbar.updateExport()

    @Slot()
    def onExportFailed(self):
        self.tab.statusBar().showColoredMessage("Export failed", success=False)


    @property
    def op(self) -> mask_ops.MaskOperation:
        return self._toolbar.selectedOp

    def onFileChanged(self, currentFile):
        if self.maskItem:
            self._imgview.scene().removeItem(self.maskItem)
        self.loadLayers()

        self.op.onFileChanged(currentFile)

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
        self.op.onEnabled(imgview)
        self.loadLayers()

        self._toolbar.updateExport()

    @override
    def onDisabled(self, imgview):
        super().onDisabled(imgview)
        imgview.filelist.removeListener(self)
        self.tab.statusBar().setToolMessage(None)

        self.op.onDisabled(imgview)

        if self.maskItem:
            imgview.scene().removeItem(self.maskItem)
        
        self.maskItem = None
        self.layers = None

    @override
    def onSceneUpdate(self):
        super().onSceneUpdate()
        self.op.onFileChanged(self.tab.filelist.getCurrentFile()) # TODO: What function to call?

        if self.maskItem:
            self.maskItem.updateTransform(self._imgview.image)
        
        self._toolbar.updateExport()
            
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
            case self.BUTTON_MAIN:
                self.op.onMousePress(event.position(), 1.0, False)
                return True
            case self.BUTTON_ALT:
                self.op.onMousePress(event.position(), 1.0, True)
                return True

        return super().onMousePress(event)

    @override
    def onMouseRelease(self, event):
        match event.button():
            case self.BUTTON_MAIN: self.op.onMouseRelease(False)
            case self.BUTTON_ALT:  self.op.onMouseRelease(True)

    @override
    def onMouseMove(self, event):
        x, y = self.mapPosToImageInt(event.position())
        self.tab.statusBar().setMouseCoords(x, y)

        w, h = self.maskItem.image.size().toTuple() if self.maskItem else (0, 0)
        if (0 <= x < w) and (0 <= y < h):
            color = self.maskItem.image.pixelColor(x, y).red()
        else:
            color = 0
        self.tab.statusBar().setToolMessage(f"Mask Value: {color/255.0:.2f}  ({color})")

        self.op.onMouseMove(event.position(), 1.0)

    @override
    def onMouseWheel(self, event) -> bool:
        # CTRL pressed -> Use default controls (zoom)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return super().onMousePress(event)
        
        wheelSteps = event.angleDelta().y() / 120.0 # 8*15° standard
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            wheelSteps *= 10

        self.op.onMouseWheel(wheelSteps)
        return True


    @override
    def onMouseEnter(self, event):
        self.op.onCursorVisible(True)
        self._imgview.scene().update()

    @override
    def onMouseLeave(self, event):
        self.op.onCursorVisible(False)
        self._imgview.scene().update()


    @override
    def onTablet(self, event: QTabletEvent) -> bool:
        # CTRL pressed -> Use default controls (pan)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier or not self.maskItem:
            return False

        pressure = event.pressure()
        #pressure = event.pressure() ** 1.0

        pointerType = event.pointingDevice().pointerType()
        alt = (pointerType == QPointingDevice.PointerType.Eraser)

        # TODO: Handle case when stylus buttons are pressed
        match event.type():
            case QEvent.Type.TabletPress:
                self.op.onMousePress(event.position(), pressure, alt)

            case QEvent.Type.TabletMove:
                self.op.onMouseMove(event.position(), pressure)

            case QEvent.Type.TabletRelease:
                self.op.onMouseRelease(alt)

        #print("tablet event:", event)
        return True





class HistoryEntry:
    def __init__(self, title: str, compressed: bool, mask: np.ndarray | None):
        self.title = title
        self.compressed = compressed
        self.mask = mask


class MaskItem(QtWidgets.QGraphicsRectItem):
    def __init__(self, name: str):
        super().__init__()
        self.setOpacity(0.55)
        self.name = name
        self.image: QImage = None

        self.history: list[HistoryEntry] = list()
        self.historyIndex = 0

    @staticmethod
    def new(name: str, image: QImage) -> MaskItem:
        maskItem = MaskItem(name)
        maskItem.setImage(image)
        maskItem.history.append( HistoryEntry("New", False, None) )
        return maskItem

    @staticmethod
    def load(name: str, imgData: np.ndarray) -> MaskItem:
        maskItem = MaskItem(name)
        maskItem.fromNumpy(imgData)
        maskItem.addHistory("Load", np.copy(imgData))
        return maskItem


    @property
    def mask(self) -> QImage:
        return self.image
    
    @property
    def size(self) -> tuple[int, int]:
        return (self.image.width(), self.image.height())

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


    def toNumpy(self) -> np.ndarray:
        buffer = np.frombuffer(self.image.constBits(), dtype=np.uint8)
        buffer.shape = (self.image.height(), self.image.bytesPerLine())
        return np.copy( buffer[:, :self.image.width()] ) # Remove padding

    def fromNumpy(self, data: np.ndarray) -> None:
        # QImage needs alignment to 32bit/4bytes. Add padding.
        height, width = data.shape
        bytesPerLine = ((width+3) // 4) * 4
        if width != bytesPerLine:
            padded = np.zeros((height, bytesPerLine), dtype=np.uint8)
            padded[:, :width] = data
            data = padded

        image = QImage(data, width, height, QImage.Format.Format_Grayscale8)
        self.setImage(image)


    def addHistory(self, title: str, imgData: np.ndarray | None = None):
        # Create a copy of the mask so that:
        #   1. It can be used for retrieving the history until the mask is converted to PNG.
        #   2. It can be safely passed to the PNG conversion thread.
        # Also remove QImage's padding, reshape.
        if imgData is None:
            imgData = self.toNumpy()

        del self.history[self.historyIndex+1:]
        self.history.append(HistoryEntry(title, False, imgData))
        self.history = self.history[-Config.maskHistorySize:]
        self.historyIndex = len(self.history) - 1

        task = MaskHistoryTask(imgData, self.historyIndex)
        task.signals.done.connect(self._setCompressedHistory, Qt.ConnectionType.BlockingQueuedConnection)
        QThreadPool.globalInstance().start(task)

    def jumpHistory(self, index):
        if index < 0 or index >= len(self.history):
            return
        entry: HistoryEntry = self.history[index]
        self.historyIndex = index

        if entry.mask is None:
            image = QImage(self.image.size(), QImage.Format.Format_Grayscale8)
            image.fill(Qt.GlobalColor.black)
            self.setImage(image)
        else:
            mask = entry.mask
            if entry.compressed:
                mask = cv.imdecode(mask, cv.IMREAD_UNCHANGED)
            self.fromNumpy(mask)

    @Slot()
    def _setCompressedHistory(self, pngData, index):
        if 0 <= index < len(self.history):
            entry = self.history[index]
            entry.compressed = True
            entry.mask = pngData





class MaskToolBar(QtWidgets.QToolBar):
    def __init__(self, maskTool):
        super().__init__("Mask")
        self.maskTool: MaskTool = maskTool
        self.ops: dict[str, mask_ops.MaskOperation] = {}
        self.selectedOp: mask_ops.MaskOperation = None

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self._buildLayers())
        layout.addWidget(self._buildOps())
        layout.addWidget(self._buildHistory())

        self.exportWidget = ExportWidget("mask", maskTool.tab.filelist, showInterpolation=False)
        layout.addWidget(self.exportWidget)

        btnExport = QtWidgets.QPushButton("Export")
        btnExport.clicked.connect(self.maskTool.exportMask)
        layout.addWidget(btnExport)

        # TODO: Also load from image's alpha channel
        #       Only if file is PNG/WEBP
        # btnApplyAlpha = QtWidgets.QPushButton("Set as Alpha Channel")
        # btnApplyAlpha.clicked.connect(self.maskTool.applyAlpha)
        # layout.addWidget(btnApplyAlpha)
        
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

        self.layerGroup = QtWidgets.QGroupBox("Layers")
        self.layerGroup.setLayout(layout)
        return self.layerGroup

    def _buildOps(self):
        shortcutLayout = QtWidgets.QHBoxLayout()
        shortcutLayout.setContentsMargins(0, 0, 0, 0)

        btnBrush = QtWidgets.QPushButton("B")
        btnBrush.clicked.connect(lambda: self.selectOp("brush"))
        shortcutLayout.addWidget(btnBrush)

        btnFill = QtWidgets.QPushButton("F")
        btnFill.clicked.connect(lambda: self.selectOp("fill"))
        shortcutLayout.addWidget(btnFill)

        btnClear = QtWidgets.QPushButton("C")
        btnClear.clicked.connect(lambda: self.selectOp("clear"))
        shortcutLayout.addWidget(btnClear)

        btnInvert = QtWidgets.QPushButton("I")
        btnInvert.clicked.connect(lambda: self.selectOp("invert"))
        shortcutLayout.addWidget(btnInvert)

        btnMorph = QtWidgets.QPushButton("M")
        btnMorph.clicked.connect(lambda: self.selectOp("morph"))
        shortcutLayout.addWidget(btnMorph)

        btnGauss = QtWidgets.QPushButton("G")
        btnGauss.clicked.connect(lambda: self.selectOp("blur_gauss"))
        shortcutLayout.addWidget(btnGauss)

        self.opLayout = QtWidgets.QVBoxLayout()
        self.opLayout.setContentsMargins(1, 1, 1, 1)
        self.opLayout.addLayout(shortcutLayout)

        self.cboOperation = QtWidgets.QComboBox()
        self.cboOperation.currentIndexChanged.connect(self.onOpChanged)
        self.opLayout.addWidget(self.cboOperation)
        self._reloadOps()
        ModelSettingsWindow(self).signals.presetListUpdated.connect(self._reloadOps)
        
        group = QtWidgets.QGroupBox("Operations")
        group.setLayout(self.opLayout)
        return group

    @Slot()
    def _reloadOps(self):
        for op in self.ops.values():
            op.deleteLater()

        # TODO: Keep existing ops and their current settings.
        self.ops = {
            "brush": mask_ops.DrawMaskOperation(self.maskTool),
            "brush_magic": mask_ops.MagicDrawMaskOperation(self.maskTool),
            "fill": mask_ops.FillMaskOperation(self.maskTool),
            "clear": mask_ops.ClearMaskOperation(self.maskTool),
            "invert": mask_ops.InvertMaskOperation(self.maskTool),
            "morph": mask_ops.MorphologyMaskOperation(self.maskTool),
            "blur_gauss": mask_ops.BlurMaskOperation(self.maskTool),
        }

        with QSignalBlocker(self.cboOperation):
            selectedKey = self.cboOperation.currentData()
            self.cboOperation.clear()

            self.cboOperation.addItem("Brush", "brush")
            #self.cboOperation.addItem("Magic Brush", "brush_magic") # Flood fill from cursor position, keep inside brush circle (or GrabCut init with mask)
            #self.cboOperation.addItem("Rectangle", "rect")
            self.cboOperation.addItem("Flood Fill", "fill")
            self.cboOperation.addItem("Clear", "clear")
            self.cboOperation.addItem("Invert", "invert")
            self.cboOperation.addItem("Morphology", "morph")
            #self.cboOperation.addItem("Linear Gradient", "gradient_linear")
            self.cboOperation.addItem("Gaussian Blur", "blur_gauss")
            
            for name, config in Config.inferMaskPresets.items():
                self._buildCustomOp(name, config)

            index = max(0, self.cboOperation.findData(selectedKey))
            self.cboOperation.setCurrentIndex(index)
            self.onOpChanged(index)
    
    def _buildCustomOp(self, name: str, config: dict):
        match config.get("backend"):
            case "yolo-detect":
                key = f"detect {name}"
                self.ops[key] = mask_ops.DetectMaskOperation(self.maskTool, config)
                self.cboOperation.addItem(f"Detect: {name}", key)
            case "bria-rmbg":
                key = f"segment {name}"
                self.ops[key] = mask_ops.SegmentMaskOperation(self.maskTool, config)
                self.cboOperation.addItem(f"Segment: {name}", key)


    def _buildHistory(self):
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)

        self.listHistory = QtWidgets.QListWidget()
        self.listHistory.currentRowChanged.connect(lambda index: self.maskTool.maskItem.jumpHistory(index))
        layout.addWidget(self.listHistory, 0, 0, 1, 2)

        group = QtWidgets.QGroupBox("History")
        group.setLayout(layout)
        return group


    def setLayers(self, layers: list[MaskItem], selectedIndex: int):
        with QSignalBlocker(self.cboLayer):
            self.cboLayer.clear()
            for mask in layers:
                self.cboLayer.addItem(mask.name, mask)
            self.cboLayer.setCurrentIndex(selectedIndex)
        
        numLayers = len(layers)
        self.btnAddLayer.setEnabled(numLayers < 4)
        self.layerGroup.setTitle(f"Layers ({numLayers})")

    @Slot()
    def renameLayer(self, name: str):
        index = self.cboLayer.currentIndex()
        self.cboLayer.setItemText(index, name)
        self.cboLayer.itemData(index).name = name


    def selectOp(self, key: str):
        if (index := self.cboOperation.findData(key)) >= 0:
            self.cboOperation.setCurrentIndex(index)

    @Slot()
    def onOpChanged(self, index: int):
        # Updating the mask model settings updates the ops and calls this function.
        # ImgView is not available when MaskTool is not active (or during initialization).
        imgview = self.maskTool._imgview

        if self.selectedOp:
            if imgview:
                self.selectedOp.onDisabled(imgview)
            self.opLayout.removeWidget(self.selectedOp)
            self.selectedOp.hide()
        
        if not (opKey := self.cboOperation.itemData(index)):
            return
        if not (op := self.ops.get(opKey)):
            return
        
        self.selectedOp = op
        self.opLayout.addWidget(self.selectedOp)
        self.selectedOp.show()

        if imgview:
            self.selectedOp.onEnabled(imgview)


    def addHistory(self, title: str, imgData: np.ndarray | None = None):
        self.maskTool.maskItem.addHistory(title, imgData)
        self.setHistory(self.maskTool.maskItem)

    def setHistory(self, maskItem: MaskItem):
        with QSignalBlocker(self.listHistory):
            self.listHistory.clear()
            for entry in maskItem.history:
                self.listHistory.addItem(entry.title)
            self.listHistory.setCurrentRow(maskItem.historyIndex)


    def updateExport(self):
        if maskItem := self.maskTool.maskItem:
            self.exportWidget.setExportSize(maskItem.mask.width(), maskItem.mask.height())
        else:
            self.exportWidget.setExportSize(0, 0)
        
        self.exportWidget.updateSample()


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
            ExportWidget.createFolders(self.destFile)
            cv.imwrite(self.destFile, self.mask, self.saveParams)
            self.signals.done.emit(self.srcFile, self.destFile)
        except Exception as ex:
            print("Error while exporting:")
            print(ex)
            self.signals.fail.emit()
        finally:
            del self.mask



class MaskHistoryTask(QRunnable):
    class HistoryTaskSignals(QObject):
        done = Signal(object, int)
    
    def __init__(self, mask: np.ndarray, index: int):
        super().__init__()
        self.signals = self.HistoryTaskSignals()
        
        self.mask = mask
        self.index = index

    @Slot()
    def run(self):
        try:
            success, encoded = cv.imencode(".png", self.mask, [cv.IMWRITE_PNG_COMPRESSION, 9])
            if success:
                self.signals.done.emit(encoded, self.index)
            else:
                print("Couldn't encode history as PNG")
        except Exception as ex:
            print("Error while saving history:")
            print(ex)
