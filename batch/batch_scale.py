from typing import Callable
from PySide6 import QtWidgets
from PySide6.QtCore import Slot
import cv2 as cv
import numpy as np
from config import Config
from lib import qtlib
import lib.imagerw as imagerw
import tools.scale as scale
import ui.export_settings as export
from infer.inference import InferenceChain
from infer.inference_proc import InferenceProcess
from .batch_task import BatchTask, BatchInferenceTask, BatchTaskHandler
from .batch_log import BatchLog


class BatchScale(QtWidgets.QWidget):
    EXPORT_PRESET_KEY = "batch-scale"

    def __init__(self, tab, logWidget: BatchLog, bars):
        super().__init__()
        self.tab = tab
        self.logWidget = logWidget
        self.taskHandler = BatchTaskHandler("Scale", bars, tab.filelist, self.getConfirmOps, self.createTask)

        self._imageSize = None
        self.scaleModes = {}
        self.selectedScaleMode: scale.ScaleMode = None

        self.parser = export.ExportVariableParser()
        self.parser.setup(self.tab.filelist.getCurrentFile(), None)

        config = Config.exportPresets.get(self.EXPORT_PRESET_KEY, {})
        self.pathSettings = export.PathSettings(self.parser)
        self.pathSettings.pathTemplate   = config.get("path_template", "{{path}}_{{w}}x{{h}}.png")
        self.pathSettings.overwriteFiles = config.get("overwrite", False)

        self._build()

    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(0, 0)
        layout.setRowStretch(1, 0)
        layout.setRowStretch(2, 1)
        layout.setRowStretch(3, 0)
        layout.setColumnMinimumWidth(0, 250)

        layout.addWidget(self._buildScaleMode(), 0, 0)
        layout.addWidget(self._buildExportSettings(), 1, 0)
        layout.addWidget(self._buildPathSettings(), 0, 1, 3, 1)
        layout.addLayout(self.taskHandler.startButtonLayout, 3, 0, 1, 2)

        self.setLayout(layout)

    def _buildScaleMode(self):
        self.scaleModeLayout = QtWidgets.QVBoxLayout()

        sizeFunc = lambda: self._imageSize
        self.scaleModes = {
            "fixed":         scale.FixedScaleMode(sizeFunc),
            "fixed_width":   scale.FixedWidthScaleMode(sizeFunc),
            "fixed_height":  scale.FixedHeightScaleMode(sizeFunc),
            "fixed_smaller": scale.FixedSideScaleMode(sizeFunc, False),
            "fixed_larger":  scale.FixedSideScaleMode(sizeFunc, True),
            "factor":        scale.FactorScaleMode(sizeFunc),
            "factor_area":   scale.AreaFactorScaleMode(sizeFunc),
            "pixel_count":   scale.PixelCountScaleMode(sizeFunc),
            "quant_closest": scale.QuantizedScaleMode(sizeFunc, scale.QuantizedScaleMode.CLOSEST),
            "quant_wider":   scale.QuantizedScaleMode(sizeFunc, scale.QuantizedScaleMode.WIDER),
            "quant_taller":  scale.QuantizedScaleMode(sizeFunc, scale.QuantizedScaleMode.TALLER),
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
        self.cboScaleMode.currentIndexChanged.connect(self._onScaleModeChanged)
        self.scaleModeLayout.addWidget(self.cboScaleMode)

        self._onScaleModeChanged(self.cboScaleMode.currentIndex())

        groupBox = QtWidgets.QGroupBox("Target Size")
        groupBox.setLayout(self.scaleModeLayout)
        return groupBox

    def _buildExportSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        self.cboScalePreset = export.ScalePresetComboBox()
        lblScaling = QtWidgets.QLabel("<a href='model_settings'>Scaling</a>:")
        lblScaling.linkActivated.connect(self.cboScalePreset.showModelSettings)
        layout.addWidget(lblScaling, 0, 0)
        layout.addWidget(self.cboScalePreset, 0, 1)

        groupBox = QtWidgets.QGroupBox("Export Settings")
        groupBox.setLayout(layout)
        return groupBox

    def _buildPathSettings(self):
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.pathSettings)

        groupBox = QtWidgets.QGroupBox("Destination")
        groupBox.setLayout(layout)
        return groupBox


    @Slot()
    def _onScaleModeChanged(self, index):
        if self.selectedScaleMode:
            self.scaleModeLayout.removeWidget(self.selectedScaleMode)
            self.selectedScaleMode.hide()
            self.selectedScaleMode.sizeChanged.disconnect(self.updateSize)

        modeKey = self.cboScaleMode.itemData(index)
        if not modeKey:
            return

        self.selectedScaleMode = self.scaleModes[modeKey]
        self.selectedScaleMode.sizeChanged.connect(self.updateSize)
        self.scaleModeLayout.addWidget(self.selectedScaleMode)
        self.selectedScaleMode.show()
        self.selectedScaleMode.updateSize()

    def onFileChanged(self, file: str):
        if pixmap := self.tab.imgview.image.pixmap():
            self._imageSize = scale.Size(pixmap.width(), pixmap.height())
        else:
            self._imageSize = None

        self.parser.setup(file)
        self.selectedScaleMode.updateSize()
        self.updateSize()


    @Slot()
    def updateSize(self):
        w, h = self.selectedScaleMode.targetSize
        self.parser.width  = w
        self.parser.height = h
        self.pathSettings.updatePreview()


    def getConfirmOps(self) -> list[str]:
        ops = [f"Resize the images using the '{self.cboScaleMode.currentText()}' mode"]

        if self.pathSettings.overwriteFiles:
            ops.append( qtlib.htmlRed("Overwrite existing images!") )
        else:
            ops.append("Save images using new filenames with an increasing counter")

        return ops

    def saveExportPreset(self):
        Config.exportPresets[self.EXPORT_PRESET_KEY] = {
            "path_template": self.pathSettings.pathTemplate,
            "overwrite": self.pathSettings.overwriteFiles
        }


    def createTask(self, files: list[str]) -> BatchTask:
        self.saveExportPreset()

        log = self.logWidget.addEntry("Scale")
        scaleFunc = self.selectedScaleMode.getScaleFunc()
        scaleConfigFactory = self.cboScalePreset.getScaleConfigFactory()

        taskClass = BatchInferenceScaleTask if scaleConfigFactory.needsInference() else BatchScaleTask
        return taskClass(log, files, scaleFunc, scaleConfigFactory, self.pathSettings)



class BatchScaleTask(BatchTask):
    def __init__(self, log, files, scaleFunc: Callable, scaleConfigFactory: export.ScaleConfigFactory, pathSettings: export.PathSettings):
        super().__init__("scale", log, files)
        self.scaleFunc      = scaleFunc
        self.scaleConfig    = scaleConfigFactory.getScaleConfig(1.0) # Only use interpolation mode
        self.pathTemplate   = pathSettings.pathTemplate
        self.overwriteFiles = pathSettings.overwriteFiles

    def runPrepare(self):
        self.parser = export.ExportVariableParser()

    def runProcessFile(self, imgFile: str) -> str:
        mat = imagerw.loadMatBGR(imgFile, rgb=True)
        origH, origW = mat.shape[:2]
        targetW, targetH = self.scaleFunc(origW, origH)

        if (targetW != origW) or (targetH != origH):
            scaleFactor = np.sqrt( (targetW * targetH) / (origW * origH) )
            mat = self.resize(mat, self.scaleConfig, targetW, targetH)
            self.log(f"Scaled by {scaleFactor:.2f} from {origW}x{origH} to {targetW}x{targetH}")
        else:
            self.log(f"Kept size {origW}x{origH}")

        self.parser.setup(imgFile)
        self.parser.width = targetW
        self.parser.height = targetH

        path = self.parser.parsePath(self.pathTemplate, self.overwriteFiles)
        export.saveImage(path, mat, self.log, convertFromBGR=False)
        return path

    @staticmethod
    def resize(mat: np.ndarray, scaleConfig: export.ScaleConfig, w: int, h: int) -> np.ndarray:
        srcHeight, srcWidth = mat.shape[:2]
        upscale = w > srcWidth or h > srcHeight
        interp = scaleConfig.getInterpolationMode(upscale)

        # Interpolation mode "Area" already does low-pass filtering when cv.resize is used
        if not upscale and scaleConfig.lpFilter and interp != cv.INTER_AREA:
            mat = export.ImageExportTask.filterLowPass(mat, srcWidth, srcHeight, w, h)

        return cv.resize(mat, (w, h), interpolation=interp)



class BatchInferenceScaleTask(BatchInferenceTask):
    def __init__(self, log, files, scaleFunc: Callable, scaleConfigFactory: export.ScaleConfigFactory, pathSettings: export.PathSettings):
        super().__init__("scale", log, files)
        self.scaleFunc      = scaleFunc
        self.scaleConfigs   = scaleConfigFactory
        self.pathTemplate   = pathSettings.pathTemplate
        self.overwriteFiles = pathSettings.overwriteFiles

    def runPrepare(self, proc):
        self.parser = export.ExportVariableParser()

    def runCheckFile(self, imgFile: str, proc: InferenceProcess) -> Callable | InferenceChain | None:
        mat = imagerw.loadMatBGR(imgFile, rgb=True)
        origH, origW = mat.shape[:2]
        targetW, targetH = self.scaleFunc(origW, origH)

        if (targetW != origW) or (targetH != origH):
            scaleFactor = np.sqrt( (targetW * targetH) / (origW * origH) )
            scaleConfig = self.scaleConfigs.getScaleConfig(scaleFactor)
            if scaleConfig.useUpscaleModel:
                # Upscale backend loads files with PIL, so it will return mat as RGB
                return lambda: self.queue(imgFile, origW, origH, targetW, targetH, scaleConfig, proc)
            else:
                mat = BatchScaleTask.resize(mat, scaleConfig, targetW, targetH)

        return InferenceChain.result((origW, origH, "", mat))

    def queue(self, imgFile: str, origW: int, origH: int, targetW: int, targetH: int, scaleConfig: export.ScaleConfig, proc: InferenceProcess):
        def scale(results: list):
            w, h, imgData = results[0]["w"], results[0]["h"], results[0]["img"]
            channels = len(imgData) // (w*h)

            mat = np.frombuffer(imgData, dtype=np.uint8)
            mat.shape = (h, w, channels)
            if (w != targetW) or (h != targetH):
                mat = BatchScaleTask.resize(mat, scaleConfig, targetW, targetH)

            return InferenceChain.result((origW, origH, scaleConfig.modelPath, mat))

        proc.upscaleImageFile(scaleConfig.toDict(), imgFile)
        return InferenceChain.resultCallback(scale)

    def runProcessFile(self, imgFile: str, results: list) -> str | None:
        if not results:
            return None

        mat: np.ndarray # RGB
        origW, origH, modelPath, mat = results[0]
        h, w = mat.shape[:2]

        if (w != origW) or (h != origH):
            scaleFactor = np.sqrt( (w * h) / (origW * origH) )
            modelText = f" using '{modelPath}'" if modelPath else ""
            self.log(f"Scaled by {scaleFactor:.2f} from {origW}x{origH} to {w}x{h}{modelText}")
        else:
            self.log(f"Kept size {origW}x{origH}")

        self.parser.setup(imgFile)
        self.parser.width = w
        self.parser.height = h

        path = self.parser.parsePath(self.pathTemplate, self.overwriteFiles)
        export.saveImage(path, mat, self.log, convertFromBGR=False)
        return path
