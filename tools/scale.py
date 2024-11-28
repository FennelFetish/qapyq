from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, Signal, QRunnable, QObject, QThreadPool, QBuffer, QSignalBlocker
import cv2 as cv
import numpy as np
from config import Config
from .view import ViewTool
from ui.export_settings import ExportWidget
from lib.filelist import DataKeys


class ScaleTool(ViewTool):
    def __init__(self, tab):
        super().__init__(tab)
        self._toolbar = ScaleToolBar(self)

    @Slot()
    def exportImage(self):
        pixmap = self._imgview.image.pixmap()
        if not pixmap:
            return

        exportWidget = self._toolbar.exportWidget
        currentFile = self._imgview.image.filepath
        destFile = exportWidget.getExportPath(currentFile)
        if not destFile:
            return

        self.tab.statusBar().showMessage("Saving scaled image...")

        rot = self._toolbar.rotation
        w, h = self._toolbar.targetSize
        interp = exportWidget.getInterpolationMode(h > pixmap.height() or w > pixmap.width())
        border = cv.BORDER_REPLICATE
        params = exportWidget.getSaveParams()

        task = ScaledExportTask(currentFile, destFile, pixmap, rot, w, h, interp, border, params)
        task.signals.done.connect(self.onExportDone, Qt.ConnectionType.BlockingQueuedConnection)
        task.signals.fail.connect(self.onExportFailed, Qt.ConnectionType.BlockingQueuedConnection)
        QThreadPool.globalInstance().start(task)

    @Slot()
    def onExportDone(self, file, path):
        message = f"Exported scaled image to: {path}"
        print(message)
        self.tab.statusBar().showColoredMessage(message, success=True)
        self._imgview.filelist.setData(file, DataKeys.CropState, DataKeys.IconStates.Saved)

        self._toolbar.updateExport()
    
    @Slot()
    def onExportFailed(self):
        self.tab.statusBar().showColoredMessage("Export failed", success=False)


    # === Tool Interface ===

    def getToolbar(self):
        return self._toolbar

    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        imgview.rotation = self._toolbar.rotation
        imgview.updateImageTransform()

        self._toolbar.initScaleMode()
        self._toolbar.updateExport()

    def onDisabled(self, imgview):
        super().onDisabled(imgview)
        imgview.rotation = 0.0
        imgview.updateImageTransform()

    def onSceneUpdate(self):
        super().onSceneUpdate()
        self._toolbar.updateExport()

    def onResetView(self):
        self._toolbar.rotation = self._imgview.rotation


    def onMousePress(self, event) -> bool:
        button = event.button()
        if button == Qt.MouseButton.RightButton:
            self.exportImage()
            return True

        return super().onMousePress(event)



class ScaleToolBar(QtWidgets.QToolBar):
    def __init__(self, scaleTool):
        super().__init__("Scale")
        self.scaleTool: ScaleTool = scaleTool
        self.exportWidget = ExportWidget("scale", scaleTool.tab.filelist)
        self.selectedScaleMode: ScaleMode = None

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self._buildTargetSize())
        layout.addWidget(self._buildRotation())
        layout.addWidget(self.exportWidget)

        btnExport = QtWidgets.QPushButton("Export")
        btnExport.clicked.connect(self.scaleTool.exportImage)
        layout.addWidget(btnExport)
        
        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.addWidget(widget)

        self.setMaximumWidth(180)

    def initScaleMode(self):
        if not self.selectedScaleMode:
            self.onScaleModeChanged(self.cboScaleMode.currentIndex())


    def _buildTargetSize(self):
        self.scaleModelayout = QtWidgets.QVBoxLayout()
        self.scaleModelayout.setContentsMargins(1, 1, 1, 1)

        self.scaleModes = {
            "fixed":         FixedScaleMode(self.scaleTool),
            "fixed_width":   FixedWidthScaleMode(self.scaleTool),
            "fixed_height":  FixedHeightScaleMode(self.scaleTool),
            "fixed_smaller": FixedSideScaleMode(self.scaleTool, False),
            "fixed_larger":  FixedSideScaleMode(self.scaleTool, True),
            "factor":        FactorScaleMode(self.scaleTool),
            "pixel_count":   PixelCountScaleMode(self.scaleTool),
            "quant_closest": QuantizedScaleMode(self.scaleTool, QuantizedScaleMode.CLOSEST),
            "quant_wider":   QuantizedScaleMode(self.scaleTool, QuantizedScaleMode.WIDER),
            "quant_taller":  QuantizedScaleMode(self.scaleTool, QuantizedScaleMode.TALLER),
        }

        self.cboScaleMode = QtWidgets.QComboBox()
        self.cboScaleMode.addItem("Fixed Size", "fixed")
        # self.cboScaleMode.addItem("Fixed Size (pad)", "fixed_pad")
        self.cboScaleMode.addItem("Fixed Width", "fixed_width")
        self.cboScaleMode.addItem("Fixed Height", "fixed_height")
        self.cboScaleMode.addItem("Fixed Smaller Side", "fixed_smaller")
        self.cboScaleMode.addItem("Fixed Larger Side", "fixed_larger")
        self.cboScaleMode.addItem("Factor", "factor")
        self.cboScaleMode.addItem("Pixel Count", "pixel_count")
        self.cboScaleMode.addItem("Quantized Closest", "quant_closest")
        self.cboScaleMode.addItem("Quantized Wider", "quant_wider")
        self.cboScaleMode.addItem("Quantized Taller", "quant_taller")
        self.cboScaleMode.currentIndexChanged.connect(self.onScaleModeChanged)
        self.scaleModelayout.addWidget(self.cboScaleMode)

        group = QtWidgets.QGroupBox("Target Size")
        group.setLayout(self.scaleModelayout)
        return group

    def _buildRotation(self):
        self.spinRot = QtWidgets.QSpinBox()
        self.spinRot.setRange(0, 270)
        self.spinRot.setSingleStep(90)
        self.spinRot.setValue(0)
        self.spinRot.valueChanged.connect(self.updateRotation)
        self.spinRot.editingFinished.connect(self.onRotationEdited)

        btnDeg0 = QtWidgets.QPushButton("0")
        btnDeg0.clicked.connect(lambda: self.spinRot.setValue(0))
        btnDeg90 = QtWidgets.QPushButton("90")
        btnDeg90.clicked.connect(lambda: self.spinRot.setValue(90))
        btnDeg180 = QtWidgets.QPushButton("180")
        btnDeg180.clicked.connect(lambda: self.spinRot.setValue(180))
        btnDeg270 = QtWidgets.QPushButton("270")
        btnDeg270.clicked.connect(lambda: self.spinRot.setValue(270))

        btnLayout = QtWidgets.QHBoxLayout()
        btnLayout.addWidget(btnDeg0)
        btnLayout.addWidget(btnDeg90)
        btnLayout.addWidget(btnDeg180)
        btnLayout.addWidget(btnDeg270)

        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addRow("Deg:", self.spinRot)
        layout.addRow(btnLayout)
        
        group = QtWidgets.QGroupBox("Rotation")
        group.setLayout(layout)
        return group


    @Slot()
    def onScaleModeChanged(self, index):
        if self.selectedScaleMode:
            self.scaleModelayout.removeWidget(self.selectedScaleMode)
            self.selectedScaleMode.hide()
            self.selectedScaleMode.sizeChanged.disconnect(self.updateExport)

        modeKey = self.cboScaleMode.itemData(index)
        if not modeKey:
            return
        
        self.selectedScaleMode = self.scaleModes[modeKey]
        self.selectedScaleMode.sizeChanged.connect(self.updateExport)
        self.scaleModelayout.addWidget(self.selectedScaleMode)
        self.selectedScaleMode.show()
        self.selectedScaleMode.updateSize()


    @property
    def rotation(self) -> float:
        return self.spinRot.value()

    @rotation.setter
    def rotation(self, rot: float):
        self.spinRot.setValue(int(rot))

    @Slot()
    def updateRotation(self, rot: int):
        rot = rot % 360
        self.scaleTool._imgview.rotation = rot
        self.scaleTool._imgview.updateImageTransform()
        self.updateExport()
    
    @Slot()
    def onRotationEdited(self):
        rot = self.spinRot.value()
        rot = round(rot / 90) * 90
        self.spinRot.setValue(rot)


    @property
    def targetSize(self) -> tuple[int, int]:
        w, h = self.selectedScaleMode.targetSize
        w, h = max(w, 1), max(h, 1)
        
        if self.rotation == 90 or self.rotation == 270:
            return (h, w)
        return (w, h)


    @Slot()
    def updateExport(self):
        if self.selectedScaleMode:
            with QSignalBlocker(self.selectedScaleMode):
                self.selectedScaleMode.updateSize()

            w, h = self.targetSize
            self.exportWidget.setExportSize(w, h)

        self.exportWidget.updateSample()



class ScaledExportTask(QRunnable):
    class ExportTaskSignals(QObject):
        done = Signal(str, str)
        fail = Signal()

        def __init__(self):
            super().__init__()

    def __init__(self, srcFile, destFile, pixmap, rotation, targetWidth, targetHeight, interp, border, saveParams):
        super().__init__()
        self.signals = self.ExportTaskSignals()

        self.srcFile = srcFile
        self.destFile = destFile

        self.img = pixmap.toImage()
        self.rotation = rotation
        self.targetWidth  = targetWidth
        self.targetHeight = targetHeight
        self.interp = interp
        self.border = border
        self.saveParams = saveParams

    @staticmethod
    def toCvMat(image):
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        image.save(buffer, "PNG", 100) # Preserve transparency with PNG. quality 100 actually fastest?

        buf = np.frombuffer(buffer.data(), dtype=np.uint8)
        return cv.imdecode(buf, cv.IMREAD_UNCHANGED)

        # dtype = np.uint8
        # channels = 1
        # print("depth:", image.depth(), "format:", image.format())
        # match image.depth():
        #     case 16: dtype = np.uint16
        #     case 24: channels = 3
        #     case 32: channels = 4
        
        # Produces slightly different images! Why? ---> probably because of padding
        # array = np.frombuffer(image.constBits(), dtype=np.uint8)
        # channels = len(array) // (image.height() * image.width())
        # array.shape = (image.height(), image.width(), channels)
        # print("shape:", array.shape)
        # return array


    @Slot()
    def run(self):
        try:
            # Offset by half pixel to maintain pixel borders
            ptsSrc = np.float32([
                [-0.5, -0.5],
                [self.img.width()-0.5, -0.5],
                [self.img.width()-0.5, self.img.height()-0.5],
            ])

            ptsDest = np.float32(self.getRotatedDestPoints())

            # https://docs.opencv.org/3.4/da/d6e/tutorial_py_geometric_transformations.html
            matrix  = cv.getAffineTransform(ptsSrc, ptsDest)
            dsize   = (self.targetWidth, self.targetHeight)
            matSrc  = self.toCvMat(self.img)
            matDest = cv.warpAffine(src=matSrc, M=matrix, dsize=dsize, flags=self.interp, borderMode=self.border)

            ExportWidget.createFolders(self.destFile)
            cv.imwrite(self.destFile, matDest, self.saveParams)
            self.signals.done.emit(self.srcFile, self.destFile)

            del matSrc
            del matDest
        except Exception as ex:
            print("Error while exporting:")
            print(ex)
            self.signals.fail.emit()
        finally:
            del self.img


    def getRotatedDestPoints(self):
        # Apparently, whole number coordinates point to the center of pixels.
        # Last pixel index is 'dimension-1'. Offset half pixel to maintain pixel borders.
        w, h = self.targetWidth-0.5, self.targetHeight-0.5
        z = -0.5

        match self.rotation:
            case 90:
                return [[w, z], [w, h], [z, h]]
            case 180:
                return [[w, h], [z, h], [z, z]]
            case 270:
                return [[z, h], [z, z], [w, z]]
        
        return [[z, z], [w, z], [w, h]]




# Target Modes:
#     Fixed (changes aspect ratio / add padding) - "Fixed size" / "Fixed size (pad)"
#     Fixed width / fixed height (keeps aspect ratio) -> "Fixed width" / "Fixed height"
#         Fixed width or height, whatever is smaller/larger (keeps aspect ratio) -> modes "Fixed smaller side" / "Fixed larger side"
#     Factor (keeps aspect ratio)
#     Megapixels (keeps aspect ratio) (use target size W*H to define number of pixels) (this will be rounded)
#     Divisible by 64 (closest, taller, wider)

# Rotation (only 90° steps)
# Padding
# Upscale with model
# Export settings like CropTool


class ScaleMode(QtWidgets.QWidget):
    sizeChanged = Signal(int, int)

    def __init__(self, scaleTool):
        super().__init__(None)
        self.scaleTool = scaleTool

        self.lblTargetAspect = QtWidgets.QLabel()
        self.lblScale = QtWidgets.QLabel("1.0")

        self.cboSizePresets = QtWidgets.QComboBox()
        self.cboSizePresets.addItems([""] + Config.cropSizePresets)
        self.cboSizePresets.currentTextChanged.connect(self._onSizePresetChosen)
        

    @property
    def targetSize(self) -> tuple[int, int]:
        raise NotImplementedError()

    @Slot()
    def updateSize(self):
        w, h = self.targetSize
        if w>0 and h>0:
            self.lblTargetAspect.setText(f"1 : {h/w:.3f}" if h>w else f"{w/h:.3f} : 1")
        else:
            self.lblTargetAspect.setText("0")

        # Compare area (this also works for the "fixed" mode which may change aspect ratio)
        scale = 0.0
        if pixmap := self.scaleTool._imgview.image.pixmap():
            scale = (w*h) / (pixmap.width()*pixmap.height())
            scale = np.sqrt(scale)
        
        if scale > 1.0:
            self.lblScale.setStyleSheet("QLabel { color: #ff3030; }")
            self.lblScale.setText(f"▲  {scale:.3f}")
        else:
            self.lblScale.setStyleSheet("QLabel { color: #30ff30; }")
            self.lblScale.setText(f"▼  {scale:.3f}")

        self.sizeChanged.emit(w, h)


    def applySizePreset(self, w: int, h: int):
        pass

    @Slot()
    def _onSizePresetChosen(self, text: str):
        if not text:
            return

        w, h = text.split("x")
        self.applySizePreset(int(w), int(h))
        self.updateSize()
        self.cboSizePresets.setCurrentIndex(0)


class FixedScaleMode(ScaleMode):
    def __init__(self, scaleTool, displayAspectRatio=True):
        super().__init__(scaleTool)

        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.spinW = QtWidgets.QSpinBox()
        self.spinW.setRange(0, 16384)
        self.spinW.setSingleStep(Config.cropSizeStep)
        self.spinW.setValue(512)
        self.spinW.valueChanged.connect(self.updateSize)
        layout.addRow("W:", self.spinW)

        self.spinH = QtWidgets.QSpinBox()
        self.spinH.setRange(0, 16384)
        self.spinH.setSingleStep(Config.cropSizeStep)
        self.spinH.setValue(512)
        self.spinH.valueChanged.connect(self.updateSize)
        layout.addRow("H:", self.spinH)

        if displayAspectRatio:
            hboxLayout = QtWidgets.QHBoxLayout()
            hboxLayout.addWidget(self.lblTargetAspect)
            hboxLayout.addWidget(self.lblScale)
            layout.addRow("AR:", hboxLayout)
        else:
            layout.addRow("", self.lblScale)

        layout.addRow("Pre:", self.cboSizePresets)

        self.setLayout(layout)


    @property
    def targetSize(self):
        return (self.spinW.value(), self.spinH.value())

    def applySizePreset(self, w: int, h: int):
        self.spinW.setValue(int(w))
        self.spinH.setValue(int(h))


class FixedWidthScaleMode(FixedScaleMode):
    def __init__(self, scaleTool):
        super().__init__(scaleTool, False)
        self.spinH.setEnabled(False)

    @Slot()
    def updateSize(self):
        if pixmap := self.scaleTool._imgview.image.pixmap():
            w = self.spinW.value()
            scale = w / pixmap.width()
            h = pixmap.height() * scale
            self.spinH.setValue(round(h))
        super().updateSize()

class FixedHeightScaleMode(FixedScaleMode):
    def __init__(self, scaleTool):
        super().__init__(scaleTool, False)
        self.spinW.setEnabled(False)

    @Slot()
    def updateSize(self):
        if pixmap := self.scaleTool._imgview.image.pixmap():
            h = self.spinH.value()
            scale = h / pixmap.height()
            w = pixmap.width() * scale
            self.spinW.setValue(round(w))
        super().updateSize()


class FixedSideScaleMode(ScaleMode):
    def __init__(self, scaleTool, largerSide: bool):
        super().__init__(scaleTool)
        self.largerSide = largerSide

        layout = QtWidgets.QGridLayout()
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        layout.setColumnMinimumWidth(0, 24)
        layout.setContentsMargins(0, 0, 0, 0)

        self.spinSideLength = QtWidgets.QSpinBox()
        self.spinSideLength.setRange(0, 16384)
        self.spinSideLength.setSingleStep(Config.cropSizeStep)
        self.spinSideLength.setValue(512)
        self.spinSideLength.valueChanged.connect(self.updateSize)
        layout.addWidget(QtWidgets.QLabel("px:"), 0, 0)
        layout.addWidget(self.spinSideLength, 0, 1, 1, 2)

        self.lblWidth = QtWidgets.QLabel()
        layout.addWidget(QtWidgets.QLabel("W:"), 1, 0)
        layout.addWidget(self.lblWidth, 1, 1)
        layout.addWidget(self.lblScale, 1, 2)

        self.lblHeight = QtWidgets.QLabel()
        layout.addWidget(QtWidgets.QLabel("H:"), 2, 0)
        layout.addWidget(self.lblHeight, 2, 1, 1, 2)

        layout.addWidget(QtWidgets.QLabel("Pre:"), 3, 0)
        layout.addWidget(self.cboSizePresets, 3, 1, 1, 2)

        self.setLayout(layout)

    @property
    def targetSize(self):
        pixmap = self.scaleTool._imgview.image.pixmap()
        if not pixmap:
            return (1, 1)
        imgW, imgH = pixmap.width(), pixmap.height()

        sideLength = self.spinSideLength.value()
        if self.largerSide:
            if imgW > imgH:
                h = imgH * (sideLength / imgW)
                return (sideLength, round(h))
            else:
                w = imgW * (sideLength / imgH)
                return (round(w), sideLength)
        
        else:
            if imgW < imgH:
                h = imgH * (sideLength / imgW)
                return (sideLength, round(h))
            else:
                w = imgW * (sideLength / imgH)
                return (round(w), sideLength)

    @Slot()
    def updateSize(self):
        w, h = self.targetSize
        self.lblWidth.setText(f"{w} px")
        self.lblHeight.setText(f"{h} px")
        super().updateSize()

    def applySizePreset(self, w: int, h: int):
        self.spinSideLength.setValue(int(w))


class FactorScaleMode(ScaleMode):
    def __init__(self, scaleTool):
        super().__init__(scaleTool)

        layout = QtWidgets.QGridLayout()
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        layout.setColumnMinimumWidth(0, 24)
        layout.setContentsMargins(0, 0, 0, 0)

        self.spinFactor = QtWidgets.QDoubleSpinBox()
        self.spinFactor.setDecimals(3)
        self.spinFactor.setRange(0.0, 100.0)
        self.spinFactor.setSingleStep(0.1)
        self.spinFactor.setValue(0.5)
        self.spinFactor.valueChanged.connect(self.updateSize)
        layout.addWidget(QtWidgets.QLabel("↕️:"), 0, 0)
        layout.addWidget(self.spinFactor, 0, 1, 1, 2)

        self.lblWidth = QtWidgets.QLabel()
        layout.addWidget(QtWidgets.QLabel("W:"), 1, 0)
        layout.addWidget(self.lblWidth, 1, 1)
        layout.addWidget(self.lblScale, 1, 2)

        self.lblHeight = QtWidgets.QLabel()
        layout.addWidget(QtWidgets.QLabel("H:"), 2, 0)
        layout.addWidget(self.lblHeight, 2, 1)

        self.setLayout(layout)

    @property
    def targetSize(self):
        pixmap = self.scaleTool._imgview.image.pixmap()
        if not pixmap:
            return (1, 1)
        imgW, imgH = pixmap.width(), pixmap.height()

        # TODO: Quantized to 1 with closest aspect ratio would be a bit more accurate
        scale = round(self.spinFactor.value(), 3)
        return (round(scale*imgW), round(scale*imgH))

    @Slot()
    def updateSize(self):
        w, h = self.targetSize
        self.lblWidth.setText(f"{w} px")
        self.lblHeight.setText(f"{h} px")
        super().updateSize()


class PixelCountScaleMode(ScaleMode):
    def __init__(self, scaleTool):
        super().__init__(scaleTool)

        layout = QtWidgets.QGridLayout()
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        layout.setColumnMinimumWidth(0, 24)
        layout.setContentsMargins(0, 0, 0, 0)

        self.spinPixelCount = QtWidgets.QSpinBox()
        self.spinPixelCount.setRange(0, 268435456) # 16384^2
        self.spinPixelCount.setSingleStep(131072) # 1024*1024/8
        self.spinPixelCount.setValue(1048576) # 1024*1024
        self.spinPixelCount.valueChanged.connect(self.updateSize)
        layout.addWidget(QtWidgets.QLabel("px:"), 0, 0)
        layout.addWidget(self.spinPixelCount, 0, 1, 1, 2)

        self.lblWidth = QtWidgets.QLabel()
        layout.addWidget(QtWidgets.QLabel("W:"), 1, 0)
        layout.addWidget(self.lblWidth, 1, 1)
        layout.addWidget(self.lblScale, 1, 2)

        self.lblHeight = QtWidgets.QLabel()
        layout.addWidget(QtWidgets.QLabel("H:"), 2, 0)
        layout.addWidget(self.lblHeight, 2, 1)

        self.setLayout(layout)

    @property
    def targetSize(self):
        pixmap = self.scaleTool._imgview.image.pixmap()
        if not pixmap:
            return (1, 1)
        imgW, imgH = pixmap.width(), pixmap.height()

        scale = self.spinPixelCount.value() / (imgW * imgH)
        scale = np.sqrt(scale)
        return (round(scale*imgW), round(scale*imgH))

    @Slot()
    def updateSize(self):
        w, h = self.targetSize
        self.lblWidth.setText(f"{w} px")
        self.lblHeight.setText(f"{h} px")
        super().updateSize()


class QuantizedScaleMode(ScaleMode):
    CLOSEST = 0
    TALLER  = 1
    WIDER   = 2

    def __init__(self, scaleTool, mode):
        super().__init__(scaleTool)
        self.mode = mode

        layout = QtWidgets.QGridLayout()
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        layout.setColumnMinimumWidth(0, 24)
        layout.setContentsMargins(0, 0, 0, 0)

        self.spinFactor = QtWidgets.QDoubleSpinBox()
        self.spinFactor.setDecimals(3)
        self.spinFactor.setRange(0.0, 100.0)
        self.spinFactor.setSingleStep(0.1)
        self.spinFactor.setValue(1.0)
        self.spinFactor.valueChanged.connect(self.updateSize)
        layout.addWidget(QtWidgets.QLabel("↕️:"), 0, 0)
        layout.addWidget(self.spinFactor, 0, 1, 1, 2)

        self.spinQuant = QtWidgets.QSpinBox()
        self.spinQuant.setRange(0, 16384)
        self.spinQuant.setSingleStep(32)
        self.spinQuant.setValue(64)
        self.spinQuant.valueChanged.connect(self.updateSize)
        layout.addWidget(QtWidgets.QLabel("Q:"), 1, 0)
        layout.addWidget(self.spinQuant, 1, 1, 1, 2)

        self.lblWidth = QtWidgets.QLabel()
        layout.addWidget(QtWidgets.QLabel("W:"), 2, 0)
        layout.addWidget(self.lblWidth, 2, 1, 1, 2)
        
        self.lblHeight = QtWidgets.QLabel()
        layout.addWidget(QtWidgets.QLabel("H:"), 3, 0)
        layout.addWidget(self.lblHeight, 3, 1, 1, 2)

        layout.addWidget(QtWidgets.QLabel("AR:"), 4, 0)
        layout.addWidget(self.lblTargetAspect, 4, 1)
        layout.addWidget(self.lblScale, 4, 2)

        self.setLayout(layout)

    @property
    def targetSize(self):
        pixmap = self.scaleTool._imgview.image.pixmap()
        if not pixmap:
            return (1, 1)
        imgW, imgH = pixmap.width(), pixmap.height()

        scale = round(self.spinFactor.value(), 3)
        quant = max(self.spinQuant.value(), 1)

        wq = max(imgW * scale / quant, 1)
        hq = max(imgH * scale / quant, 1)

        wUp, wDn = int(np.ceil(wq)*quant), int(np.floor(wq)*quant)
        hUp, hDn = int(np.ceil(hq)*quant), int(np.floor(hq)*quant)
        
        # (width, height, aspect ratio)
        points = [
            (wDn, hDn, wDn/hDn),
            (wUp, hDn, wUp/hDn),
            (wDn, hUp, wDn/hUp),
            (wUp, hUp, wUp/hUp)
        ]

        aspect = imgW / imgH
        # TODO: Also sort by target size
        # [(192, 192, 1.0), (288, 192, 1.5), (192, 288, 0.6666666666666666), (288, 288, 1.0)]  << here, 288x288 should be chosen for a 256^2 input image?
        points.sort(key=lambda p: abs(p[2]-aspect))

        selectedPoint = points[0] # Size with closest aspect ratio
        if self.mode == self.WIDER:
            selectedPoint = next((p for p in points if p[2] >= aspect), selectedPoint)
        elif self.mode == self.TALLER:
            selectedPoint = next((p for p in points if p[2] <= aspect), selectedPoint)
        
        return selectedPoint[:2]


    @Slot()
    def updateSize(self):
        w, h = self.targetSize
        q = max(self.spinQuant.value(), 1)
        self.lblWidth.setText(f"{w} px   ({int(w/q)} x Q)")
        self.lblHeight.setText(f"{h} px   ({int(h/q)} x Q)")
        super().updateSize()
