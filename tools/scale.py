from typing import Callable
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, Signal, QThreadPool, QSignalBlocker
import numpy as np
from config import Config
from .view import ViewTool
import ui.export_settings as export
from ui.size_preset import SizePresetComboBox
from lib.qtlib import COLOR_RED, COLOR_GREEN
from lib.filelist import DataKeys


class Size:
    def __init__(self, w, h):
        self.w, self.h = w, h


class ScaleTool(ViewTool):
    def __init__(self, tab):
        super().__init__(tab)
        self._lastExportedFile = ""
        self._toolbar = ScaleToolBar(self)

    def imgSize(self) -> Size | None:
        if pixmap := self._imgview.image.pixmap():
            return Size(pixmap.width(), pixmap.height())
        return None

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

        self.tab.statusBar().showMessage("Exporting image...")

        rot = self._toolbar.rotation
        w, h = self._toolbar.targetSize
        scaleFactor = np.sqrt( (w * h) / (pixmap.width() * pixmap.height()) )
        scaleConfig = exportWidget.getScaleConfig(scaleFactor)

        task = ScaledExportTask(currentFile, destFile, pixmap, rot, w, h, scaleConfig)
        task.signals.done.connect(self.onExportDone, Qt.ConnectionType.BlockingQueuedConnection)
        task.signals.progress.connect(self.onExportProgress, Qt.ConnectionType.BlockingQueuedConnection)
        task.signals.fail.connect(self.onExportFailed, Qt.ConnectionType.BlockingQueuedConnection)
        QThreadPool.globalInstance().start(task)

    @Slot()
    def onExportDone(self, file, path):
        message = f"Exported scaled image to: {path}"
        print(message)
        self.tab.statusBar().showColoredMessage(message, success=True)

        self._imgview.filelist.setData(file, DataKeys.CropState, DataKeys.IconStates.Saved)
        self._toolbar.updateExport()
        self._lastExportedFile = path

    @Slot()
    def onExportProgress(self, message: str):
        self.tab.statusBar().showMessage(message)

    @Slot()
    def onExportFailed(self, msg: str):
        self.tab.statusBar().showColoredMessage(f"Export failed: {msg}", False, 0)


    @Slot()
    def openLastExportedFile(self):
        if self._lastExportedFile:
            tab = self.tab.mainWindow.addTab()
            tab.filelist.load(self._lastExportedFile)


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


    def onKeyPress(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            match event.key():
                case Qt.Key.Key_E:
                    self.exportImage()
                    return

        return super().onKeyPress(event)



class ScaleToolBar(QtWidgets.QToolBar):
    def __init__(self, scaleTool):
        super().__init__("Scale")
        self.scaleTool: ScaleTool = scaleTool
        self.exportWidget = export.ExportWidget("scale", scaleTool.tab.filelist)
        self.selectedScaleMode: ScaleMode = None

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self._buildTargetSize())
        layout.addWidget(self._buildRotation())
        layout.addWidget(self.exportWidget)

        btnExport = QtWidgets.QPushButton("Export")
        btnExport.clicked.connect(self.scaleTool.exportImage)
        layout.addWidget(btnExport)

        btnOpenLast = QtWidgets.QPushButton("Open Last File")
        btnOpenLast.clicked.connect(scaleTool.openLastExportedFile)
        layout.addWidget(btnOpenLast)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.addWidget(widget)

        self.setMaximumWidth(180)

    def initScaleMode(self):
        if not self.selectedScaleMode:
            self.onScaleModeChanged(self.cboScaleMode.currentIndex())

    def _buildTargetSize(self):
        self.scaleModeLayout = QtWidgets.QVBoxLayout()
        self.scaleModeLayout.setContentsMargins(1, 1, 1, 1)

        sizeFunc = self.scaleTool.imgSize
        self.scaleModes = {
            "fixed":         FixedScaleMode(sizeFunc),
            "fixed_width":   FixedWidthScaleMode(sizeFunc),
            "fixed_height":  FixedHeightScaleMode(sizeFunc),
            "fixed_smaller": FixedSideScaleMode(sizeFunc, False),
            "fixed_larger":  FixedSideScaleMode(sizeFunc, True),
            "factor":        FactorScaleMode(sizeFunc),
            "factor_area":   AreaFactorScaleMode(sizeFunc),
            "pixel_count":   PixelCountScaleMode(sizeFunc),
            "quant_closest": QuantizedScaleMode(sizeFunc, QuantizedScaleMode.CLOSEST),
            "quant_wider":   QuantizedScaleMode(sizeFunc, QuantizedScaleMode.WIDER),
            "quant_taller":  QuantizedScaleMode(sizeFunc, QuantizedScaleMode.TALLER),
        }

        self.cboScaleMode = QtWidgets.QComboBox()
        self.cboScaleMode.addItem("Fixed Size", "fixed")
        # self.cboScaleMode.addItem("Fixed Size (pad)", "fixed_pad")
        self.cboScaleMode.addItem("Fixed Width", "fixed_width")
        self.cboScaleMode.addItem("Fixed Height", "fixed_height")
        self.cboScaleMode.addItem("Fixed Smaller Side", "fixed_smaller")
        self.cboScaleMode.addItem("Fixed Larger Side", "fixed_larger")
        self.cboScaleMode.addItem("Factor", "factor")
        self.cboScaleMode.addItem("Area Factor", "factor_area")
        self.cboScaleMode.addItem("Pixel Count", "pixel_count")
        self.cboScaleMode.addItem("Quantized Closest", "quant_closest")
        self.cboScaleMode.addItem("Quantized Wider", "quant_wider")
        self.cboScaleMode.addItem("Quantized Taller", "quant_taller")
        #self.cboScaleMode.addItem("Quantized Crop", "quant_crop")
        self.cboScaleMode.currentIndexChanged.connect(self.onScaleModeChanged)
        self.scaleModeLayout.addWidget(self.cboScaleMode)

        group = QtWidgets.QGroupBox("Target Size")
        group.setLayout(self.scaleModeLayout)
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
            self.scaleModeLayout.removeWidget(self.selectedScaleMode)
            self.selectedScaleMode.hide()
            self.selectedScaleMode.sizeChanged.disconnect(self.updateExport)

        modeKey = self.cboScaleMode.itemData(index)
        if not modeKey:
            return

        self.selectedScaleMode = self.scaleModes[modeKey]
        self.selectedScaleMode.sizeChanged.connect(self.updateExport)
        self.scaleModeLayout.addWidget(self.selectedScaleMode)
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
            rot = self.scaleTool._imgview.rotation
            self.exportWidget.setExportSize(w, h, rot)

        self.exportWidget.updateSample()



class ScaledExportTask(export.ImageExportTask):
    def __init__(self, srcFile, destFile, pixmap, rotation: float, targetWidth: int, targetHeight: int, scaleConfig: export.ScaleConfig):
        super().__init__(srcFile, destFile, pixmap, targetWidth, targetHeight, scaleConfig)
        self.rotation = rotation

    def processImage(self, mat: np.ndarray) -> np.ndarray:
        if self.rotation == 0:
            return self.resize(mat)

        # Offset by half pixel to maintain pixel borders
        h, w = mat.shape[:2]
        ptsSrc = [
            [-0.5, -0.5],
            [w-0.5, -0.5],
            [w-0.5, h-0.5],
        ]

        ptsDest = self.getRotatedDestPoints()
        return self.warpAffine(mat, ptsSrc, ptsDest)

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



class ScaleMode(QtWidgets.QWidget):
    sizeChanged = Signal(int, int)

    def __init__(self, sizeFunc: Callable[[], Size | None]):
        super().__init__(None)
        self.sizeFunc = sizeFunc

        self.lblTargetAspect = QtWidgets.QLabel()
        self.lblScale = QtWidgets.QLabel("1.0")

        self.cboSizePresets = SizePresetComboBox()
        self.cboSizePresets.presetSelected.connect(self._onSizePresetChosen)


    def getScaleFunc(self) -> Callable[[int, int], tuple[int, int]]:
        raise NotImplementedError()

    @property
    def targetSize(self) -> tuple[int, int]:
        if imgSize := self.sizeFunc():
            return self.getScaleFunc()(imgSize.w, imgSize.h)
        else:
            return (1, 1)

    @Slot()
    def updateSize(self):
        w, h = self.targetSize
        if w>0 and h>0:
            self.lblTargetAspect.setText(f"1 : {h/w:.3f}" if h>w else f"{w/h:.3f} : 1")
        else:
            self.lblTargetAspect.setText("0")

        # Compare area (this also works for the "fixed" mode which may change aspect ratio)
        scale = 0.0
        if imgSize := self.sizeFunc():
            scale = (w*h) / (imgSize.w * imgSize.h)
            scale = np.sqrt(scale)

        if scale > 1.0:
            self.lblScale.setStyleSheet(f"QLabel{{color:{COLOR_RED}}}")
            self.lblScale.setText(f"▲  {scale:.3f}")
        else:
            self.lblScale.setStyleSheet(f"QLabel{{color:{COLOR_GREEN}}}")
            self.lblScale.setText(f"▼  {scale:.3f}")

        self.sizeChanged.emit(w, h)


    def applySizePreset(self, w: int, h: int):
        pass

    @Slot()
    def _onSizePresetChosen(self, w: int, h: int):
        self.applySizePreset(w, h)
        self.updateSize()


class FixedScaleMode(ScaleMode):
    def __init__(self, sizeFunc: Callable[[], Size | None], displayAspectRatio=True):
        super().__init__(sizeFunc)

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

    def getScaleFunc(self):
        w, h = self.spinW.value(), self.spinH.value()
        def func(imgWidth: int, imgHeight: int):
            return (w, h)
        return func

    def applySizePreset(self, w: int, h: int):
        self.spinW.setValue(int(w))
        self.spinH.setValue(int(h))


class FixedWidthScaleMode(FixedScaleMode):
    def __init__(self, sizeFunc):
        super().__init__(sizeFunc, False)
        self.spinH.setEnabled(False)

    def getScaleFunc(self):
        w = self.spinW.value()
        def func(imgWidth: int, imgHeight: int):
            scale = w / imgWidth
            h = scale * imgHeight
            return (w, round(h))
        return func

    @Slot()
    def updateSize(self):
        if imgSize := self.sizeFunc():
            w, h = self.getScaleFunc()(imgSize.w, imgSize.h)
            self.spinH.setValue(h)
        super().updateSize()

class FixedHeightScaleMode(FixedScaleMode):
    def __init__(self, sizeFunc):
        super().__init__(sizeFunc, False)
        self.spinW.setEnabled(False)

    def getScaleFunc(self):
        h = self.spinH.value()
        def func(imgWidth: int, imgHeight: int):
            scale = h / imgHeight
            w = scale * imgWidth
            return (round(w), h)
        return func

    @Slot()
    def updateSize(self):
        if imgSize := self.sizeFunc():
            w, h = self.getScaleFunc()(imgSize.w, imgSize.h)
            self.spinW.setValue(w)
        super().updateSize()


class FixedSideScaleMode(ScaleMode):
    def __init__(self, sizeFunc, largerSide: bool):
        super().__init__(sizeFunc)
        self.largerSide = largerSide

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
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

    def getScaleFunc(self):
        sideLength = self.spinSideLength.value()

        if self.largerSide:
            def func(imgWidth: int, imgHeight: int):
                if imgWidth > imgHeight:
                    h = imgHeight * (sideLength / imgWidth)
                    return (sideLength, round(h))
                else:
                    w = imgWidth * (sideLength / imgHeight)
                    return (round(w), sideLength)

        else: # fixed smaller side
            def func(imgWidth: int, imgHeight: int):
                if imgWidth < imgHeight:
                    h = imgHeight * (sideLength / imgWidth)
                    return (sideLength, round(h))
                else:
                    w = imgWidth * (sideLength / imgHeight)
                    return (round(w), sideLength)

        return func

    @Slot()
    def updateSize(self):
        w, h = self.targetSize
        self.lblWidth.setText(f"{w} px")
        self.lblHeight.setText(f"{h} px")
        super().updateSize()

    def applySizePreset(self, w: int, h: int):
        self.spinSideLength.setValue(int(w))


class FactorScaleMode(ScaleMode):
    def __init__(self, sizeFunc):
        super().__init__(sizeFunc)

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
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

    def getScaleFunc(self):
        scale = round(self.spinFactor.value(), 3)
        def func(imgWidth: int, imgHeight: int):
            # TODO: Quantized to 1 with closest aspect ratio would be a bit more accurate
            return (round(scale*imgWidth), round(scale*imgHeight))
        return func

    @Slot()
    def updateSize(self):
        w, h = self.targetSize
        self.lblWidth.setText(f"{w} px")
        self.lblHeight.setText(f"{h} px")
        super().updateSize()


class AreaFactorScaleMode(FactorScaleMode):
    def __init__(self, sizeFunc):
        super().__init__(sizeFunc)

    def getScaleFunc(self):
        scale = np.sqrt(round(self.spinFactor.value(), 3))
        def func(imgWidth: int, imgHeight: int):
            return (round(scale*imgWidth), round(scale*imgHeight))
        return func


class PixelCountScaleMode(ScaleMode):
    def __init__(self, sizeFunc):
        super().__init__(sizeFunc)

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
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

        # TODO: Make this a spin box
        self.lblMegaPx = QtWidgets.QLabel()
        layout.addWidget(QtWidgets.QLabel("MP:"), 1, 0)
        layout.addWidget(self.lblMegaPx, 1, 1, 1, 2)

        self.lblWidth = QtWidgets.QLabel()
        layout.addWidget(QtWidgets.QLabel("W:"), 2, 0)
        layout.addWidget(self.lblWidth, 2, 1)
        layout.addWidget(self.lblScale, 2, 2)

        self.lblHeight = QtWidgets.QLabel()
        layout.addWidget(QtWidgets.QLabel("H:"), 3, 0)
        layout.addWidget(self.lblHeight, 3, 1)

        self.setLayout(layout)

    def getScaleFunc(self):
        pixelCount = self.spinPixelCount.value()
        def func(imgWidth: int, imgHeight: int):
            scale = pixelCount / (imgWidth * imgHeight)
            scale = np.sqrt(scale)
            return (round(scale*imgWidth), round(scale*imgHeight))
        return func

    @Slot()
    def updateSize(self):
        w, h = self.targetSize
        megaPx = (w*h) / 1000000
        self.lblMegaPx.setText(f"{megaPx:.3f}")
        self.lblWidth.setText(f"{w} px")
        self.lblHeight.setText(f"{h} px")
        super().updateSize()


class QuantizedScaleMode(ScaleMode):
    CLOSEST = 0
    TALLER  = 1
    WIDER   = 2

    def __init__(self, sizeFunc, mode):
        super().__init__(sizeFunc)
        self.mode = mode

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
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

    def getScaleFunc(self):
        mode = self.mode
        scale = round(self.spinFactor.value(), 3)
        quant = max(self.spinQuant.value(), 1)

        def func(imgWidth: int, imgHeight: int):
            wq = max(imgWidth * scale / quant, 1)
            hq = max(imgHeight * scale / quant, 1)

            wUp, wDn = int(np.ceil(wq)*quant), int(np.floor(wq)*quant)
            hUp, hDn = int(np.ceil(hq)*quant), int(np.floor(hq)*quant)

            # (width, height, aspect ratio)
            points = [
                (wDn, hDn, wDn/hDn),
                (wUp, hDn, wUp/hDn),
                (wDn, hUp, wDn/hUp),
                (wUp, hUp, wUp/hUp)
            ]

            aspect = imgWidth / imgHeight
            # TODO: Also sort by target size
            # [(192, 192, 1.0), (288, 192, 1.5), (192, 288, 0.6666666666666666), (288, 288, 1.0)]  << here, 288x288 should be chosen for a 256^2 input image?
            points.sort(key=lambda p: abs(p[2]-aspect))

            selectedPoint = points[0] # Size with closest aspect ratio
            if mode == QuantizedScaleMode.WIDER:
                selectedPoint = next((p for p in points if p[2] >= aspect), selectedPoint)
            elif mode == QuantizedScaleMode.TALLER:
                selectedPoint = next((p for p in points if p[2] <= aspect), selectedPoint)

            return selectedPoint[:2]

        return func

    @Slot()
    def updateSize(self):
        w, h = self.targetSize
        q = max(self.spinQuant.value(), 1)
        self.lblWidth.setText(f"{w} px   ({int(w/q)} x Q)")
        self.lblHeight.setText(f"{h} px   ({int(h/q)} x Q)")
        super().updateSize()
