import os
from typing import ForwardRef
from typing_extensions import override
from PySide6.QtCore import Qt, Slot, Signal, QEvent, QRunnable, QObject, QThreadPool
from PySide6.QtGui import QImage, QPainter, QTabletEvent, QPointingDevice, QKeySequence
from PySide6 import QtWidgets
import cv2 as cv
import numpy as np
from lib.filelist import FileList, DataKeys
from lib.mask_macro import MaskingMacro, MacroOp, MacroOpItem
from lib.qtlib import numpyToQImageMask, qimageToNumpyMask
import lib.imagerw as imagerw
import ui.export_settings as export
from config import Config
from .view import ViewTool
from .mask_ops import MaskOperation

MaskItem = ForwardRef("MaskItem")


class MaskTool(ViewTool):
    BUTTON_MAIN = Qt.MouseButton.LeftButton
    BUTTON_ALT = Qt.MouseButton.RightButton

    def __init__(self, tab):
        super().__init__(tab)
        self.maskItem: MaskItem = None
        self.layers: list[MaskItem] = None
        self.macro = MaskingMacro()

        from .mask_toolbar import MaskToolBar
        self._toolbar = MaskToolBar(self)

    def createMask(self, name: str = None) -> MaskItem:
        if not name:
            name = "Layer 0"

        imgview = self._imgview
        pixmap = imgview.image.pixmap()

        mask = QImage(pixmap.size(), QImage.Format.Format_Grayscale8)
        mask.fill(Qt.GlobalColor.black)

        maskItem = MaskItem.new(name, mask)
        maskItem.setOpacity(self._toolbar.opacity)
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
        elif layers := self.loadLayersFromFile(filelist):
            self.maskItem = layers[0]
        else:
            self.maskItem = self.createMask()
            layers = [ self.maskItem ]

        self._imgview.scene().addItem(self.maskItem)
        self._imgview.updateView()

        self.layers = layers
        self._toolbar.setLayers(layers, index)
        self._toolbar.setHistory(self.maskItem)

        maskState = filelist.getData(currentFile, DataKeys.MaskState)
        self._toolbar.setEdited(maskState == DataKeys.IconStates.Changed)

    def loadLayersFromFile(self, filelist: FileList):
        currentFile = filelist.getCurrentFile()
        maskPath = self._toolbar.exportWidget.getAutoExportPath(currentFile, forReading=True) # TODO: When overwrite disabled, load latest counter
        if not os.path.exists(maskPath):
            filelist.removeData(currentFile, DataKeys.MaskState)
            return None

        filelist.setData(currentFile, DataKeys.MaskState, DataKeys.IconStates.Exists)

        maskMat = imagerw.loadMatBGR(maskPath)
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
            maskItem.setOpacity(self._toolbar.opacity)
            maskItem.updateTransform(self._imgview.image)
            layers.append(maskItem)
        return layers

    def resetLayers(self):
        filelist = self.tab.filelist
        if not (currentFile := filelist.getCurrentFile()):
            return

        filelist.removeData(currentFile, DataKeys.MaskLayers)
        filelist.removeData(currentFile, DataKeys.MaskIndex)
        filelist.removeData(currentFile, DataKeys.MaskState)

        self.onFileChanged(currentFile)


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
        self.macro.addOperation(MacroOp.AddLayer)

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

        self.macro.addOperation(MacroOp.SetLayer, index=index)

    @Slot()
    def deleteCurrentLayer(self):
        filelist = self.tab.filelist
        if not (currentFile := filelist.getCurrentFile()):
            return

        index = self.layers.index(self.maskItem)
        del self.layers[index]
        self.macro.addOperation(MacroOp.DeleteLayer, index=index)

        allRemoved = False
        if not self.layers:
            allRemoved = True
            self.layers.append( self.createMask() )
            self.macro.addOperation(MacroOp.AddLayer)

        index = max(index-1, 0)
        self.setLayer(index)
        self._toolbar.setLayers(self.layers, index)

        if allRemoved:
            filelist.removeData(currentFile, DataKeys.MaskLayers)
            filelist.removeData(currentFile, DataKeys.MaskIndex)
            filelist.setData(currentFile, DataKeys.MaskState, DataKeys.IconStates.Changed)
        else:
            self.setEdited()


    @Slot()
    def updateMaskOpacity(self, opacity: float):
        for layer in self.layers:
            layer.setOpacity(opacity)

    def setEdited(self):
        self.storeLayers()
        self._toolbar.setEdited(True)


    @Slot()
    def exportMask(self):
        if not self.layers:
            return

        currentFile = self.tab.filelist.getCurrentFile()
        destFile = self._toolbar.exportWidget.getExportPath(currentFile)
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
        task = MaskExportTask(currentFile, destFile, combined)
        task.signals.done.connect(self.onExportDone, Qt.ConnectionType.BlockingQueuedConnection)
        task.signals.fail.connect(self.onExportFailed, Qt.ConnectionType.BlockingQueuedConnection)
        QThreadPool.globalInstance().start(task)

        # Set state when export starts so editing while export is in progress will correctly reflect changed status.
        self.tab.filelist.setData(currentFile, DataKeys.MaskState, DataKeys.IconStates.Saved)
        self._toolbar.setEdited(False)


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
    def onExportFailed(self, msg: str):
        self.tab.statusBar().showColoredMessage(f"Export failed: {msg}", False, 0)


    @property
    def op(self) -> MaskOperation:
        return self._toolbar.selectedOp

    def onFileChanged(self, currentFile):
        if self.maskItem:
            self._imgview.scene().removeItem(self.maskItem)
        self.loadLayers()

        self.op.onFileChanged(currentFile)
        self._toolbar.stopRecordMacro()

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


    def onKeyPress(self, event):
        if event.matches(QKeySequence.StandardKey.Undo):
            self._toolbar.undoHistory()
        elif event.matches(QKeySequence.StandardKey.Redo):
            self._toolbar.redoHistory()

        elif event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            match event.key():
                case Qt.Key.Key_E:
                    self.exportMask()
                    return

        return super().onKeyPress(event)




class HistoryEntry:
    def __init__(self, title: str, mask: np.ndarray | None, macroItem: MacroOpItem | None = None):
        self.title = title
        self.compressed = False
        self.mask = mask
        self.macroItem = macroItem

    def setCompressed(self, mask: np.ndarray):
        self.compressed = True
        self.mask = mask


class MaskItem(QtWidgets.QGraphicsRectItem):
    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.image: QImage = None

        self.history: list[HistoryEntry] = list()
        self.historyIndex = 0

    @staticmethod
    def new(name: str, image: QImage) -> MaskItem:
        maskItem = MaskItem(name)
        maskItem.setImage(image)
        maskItem.history.append( HistoryEntry("New", None) )
        return maskItem

    @staticmethod
    def load(name: str, imgData: np.ndarray) -> MaskItem:
        maskItem = MaskItem(name)
        maskItem.fromNumpy(imgData)
        maskItem.addHistory("Load", np.copy(imgData)) # TODO: copy necessary?
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
        return qimageToNumpyMask(self.image)

    def fromNumpy(self, data: np.ndarray) -> None:
        image = numpyToQImageMask(data)
        self.setImage(image)


    def addHistory(self, title: str, imgData: np.ndarray | None = None, macroItem: MacroOpItem | None = None):
        # Create a copy of the mask so that:
        #   1. It can be used for retrieving the history until the mask is converted to PNG.
        #   2. It can be safely passed to the PNG conversion thread.
        # Also remove QImage's padding, reshape.
        if imgData is None:
            imgData = self.toNumpy()

        historyEntry = HistoryEntry(title, imgData, macroItem)

        del self.history[self.historyIndex+1:]
        self.history.append(historyEntry)
        self.history = self.history[-Config.maskHistorySize:]
        self.historyIndex = len(self.history) - 1

        task = MaskHistoryTask(imgData)
        # Use lambda. There's a maximally weird bug that can crash the application because 'self' in a Slot becomes a different object.
        task.signals.done.connect(lambda pngData: historyEntry.setCompressed(pngData), Qt.ConnectionType.BlockingQueuedConnection)
        QThreadPool.globalInstance().start(task)

    def jumpHistory(self, index):
        if index < 0 or index >= len(self.history) or index == self.historyIndex:
            return

        # Update macro
        start, end = sorted((index+1, self.historyIndex+1))
        opState = (index >= self.historyIndex)
        for entry in self.history[start:end]:
            if entry.macroItem: entry.macroItem.enabled = opState

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

    def clearHistoryMacroItems(self):
        for entry in self.history:
            entry.macroItem = None



class MaskExportTask(QRunnable):
    class ExportTaskSignals(QObject):
        done = Signal(str, str)
        fail = Signal(str)

        def __init__(self):
            super().__init__()

    def __init__(self, srcFile, destFile, mask):
        super().__init__()
        self.signals = self.ExportTaskSignals()

        self.srcFile = srcFile
        self.destFile = destFile
        self.mask = mask

    @Slot()
    def run(self):
        try:
            export.saveImage(self.destFile, self.mask)
            self.signals.done.emit(self.srcFile, self.destFile)
        except Exception as ex:
            print(f"Export failed: {ex}")
            self.signals.fail.emit(str(ex))
        finally:
            del self.mask



class MaskHistoryTask(QRunnable):
    class HistoryTaskSignals(QObject):
        done = Signal(object)

    def __init__(self, mask: np.ndarray):
        super().__init__()
        self.setAutoDelete(True)
        self.signals = self.HistoryTaskSignals()
        self.mask = mask

    @Slot()
    def run(self):
        try:
            success, encoded = cv.imencode(".png", self.mask, [cv.IMWRITE_PNG_COMPRESSION, 9])
            if success:
                self.signals.done.emit(encoded)
            else:
                print("Couldn't encode history as PNG")
        except Exception as ex:
            print("Error while saving history:")
            print(ex)
