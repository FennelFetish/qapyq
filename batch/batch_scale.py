from PySide6 import QtWidgets
from PySide6.QtCore import Slot
from PIL import Image
from config import Config
from lib import qtlib
from infer import Inference
from .batch_task import BatchTask
import tools.scale as scale
import ui.export_settings as export


INTERP_MODES = {
    "Nearest": Image.Resampling.NEAREST,
    "Linear":  Image.Resampling.BILINEAR,
    "Cubic":   Image.Resampling.BICUBIC,
    "Area":    Image.Resampling.BOX,
    "Lanczos": Image.Resampling.LANCZOS,
    "Hamming": Image.Resampling.HAMMING
}


class Format:
    def __init__(self, saveParams: dict, conversion: dict = {}):
        self.saveParams = saveParams
        self.conversion = conversion

FORMATS = {
    "PNG":  Format({"optimize": True, "compress_level": 9}),
    "JPG":  Format({"optimize": True, "quality": 95}, {"RGBA": "RGB", "P": "RGB"}),
    "WEBP": Format({"lossless": True, "quality": 100})
}


class BatchScale(QtWidgets.QWidget):
    EXPORT_PRESET_KEY = "batch-scale"

    def __init__(self, tab, logSlot, progressBar, statusBar):
        super().__init__()
        self.tab = tab
        self.log = logSlot
        self.progressBar: QtWidgets.QProgressBar = progressBar
        self.statusBar: qtlib.ColoredMessageStatusBar = statusBar

        self._imageSize = None
        self.scaleModes = {}
        self.selectedScaleMode: scale.ScaleMode = None

        self.parser = export.ExportVariableParser()
        self.parser.setup(self.tab.filelist.getCurrentFile(), None)

        config = Config.exportPresets.get(self.EXPORT_PRESET_KEY, {})
        self.pathSettings = export.PathSettings(self.parser)
        self.pathSettings.pathTemplate   = config.get("path_template", "{{path}}_{{w}}x{{h}}")
        self.pathSettings.overwriteFiles = config.get("overwrite", False)

        self._task = None
        self._build()

    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(0, 0)
        layout.setRowStretch(1, 0)
        layout.setRowStretch(2, 1)
        layout.setRowStretch(3, 0)
        layout.setColumnMinimumWidth(0, 240)

        layout.addWidget(self._buildScaleMode(), 0, 0)
        layout.addWidget(self._buildExportSettings(), 1, 0)
        layout.addWidget(self._buildPathSettings(), 0, 1, 3, 1)

        self.btnStart = QtWidgets.QPushButton("Start Batch Scale")
        self.btnStart.clicked.connect(self.startStop)
        layout.addWidget(self.btnStart, 3, 0, 1, 2)

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
        self.cboScaleMode.addItem("Pixel Count", "pixel_count")
        self.cboScaleMode.addItem("Quantized Closest", "quant_closest")
        self.cboScaleMode.addItem("Quantized Wider", "quant_wider")
        self.cboScaleMode.addItem("Quantized Taller", "quant_taller")
        #self.cboScaleMode.addItem("Quantized Crop", "quant_crop")
        self.cboScaleMode.currentIndexChanged.connect(self._onScaleModeChanged)
        self.scaleModeLayout.addWidget(self.cboScaleMode)

        self._onScaleModeChanged(self.cboScaleMode.currentIndex())

        groupBox = QtWidgets.QGroupBox("Scale Mode")
        groupBox.setLayout(self.scaleModeLayout)
        return groupBox

    def _buildExportSettings(self):
        layout = QtWidgets.QFormLayout()

        self.cboInterpUp = QtWidgets.QComboBox()
        self.cboInterpUp.addItems(INTERP_MODES.keys())
        self.cboInterpUp.setCurrentIndex(4) # Default: Lanczos
        layout.addRow("Interpolation Up:", self.cboInterpUp)

        self.cboInterpDown = QtWidgets.QComboBox()
        self.cboInterpDown.addItems(INTERP_MODES.keys())
        self.cboInterpDown.setCurrentIndex(3) # Default: Area
        layout.addRow("Interpolation Down:", self.cboInterpDown)

        self.cboFormat = QtWidgets.QComboBox()
        self.cboFormat.addItems(FORMATS.keys())
        self.cboFormat.currentTextChanged.connect(self._onExtensionChanged)
        layout.addRow("Format:", self.cboFormat)
        self._onExtensionChanged(self.cboFormat.currentText())

        groupBox = QtWidgets.QGroupBox("Export Settings")
        groupBox.setLayout(layout)
        return groupBox

    def _buildPathSettings(self):
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.pathSettings)

        groupBox = QtWidgets.QGroupBox("Path")
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

    @Slot()
    def _onExtensionChanged(self, ext: str):
        self.pathSettings.extension = ext
        self.pathSettings.updatePreview()

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


    def saveExportPreset(self):
        Config.exportPresets[self.EXPORT_PRESET_KEY] = {
            "path_template": self.pathSettings.pathTemplate,
            "overwrite": self.pathSettings.overwriteFiles
        }

    @Slot()
    def startStop(self):
        if self._task:
            self._task.abort()
        else:
            self.saveExportPreset()
            self.btnStart.setText("Abort")

            scaleFunc = self.selectedScaleMode.getScaleFunc()
            self._task = BatchScaleTask(self.log, self.tab.filelist, scaleFunc, self.pathSettings)
            self._task.interpUp   = INTERP_MODES[ self.cboInterpUp.currentText() ]
            self._task.interpDown = INTERP_MODES[ self.cboInterpDown.currentText() ]
            self._task.format     = FORMATS[ self.cboFormat.currentText() ]

            self._task.signals.progress.connect(self.onProgress)
            self._task.signals.progressMessage.connect(self.onProgressMessage)
            self._task.signals.done.connect(self.onFinished)
            self._task.signals.fail.connect(self.onFail)
            Inference().queueTask(self._task)

    @Slot()
    def onFinished(self, numFiles):
        self.statusBar.showColoredMessage(f"Processed {numFiles} files", True, 0)
        self.taskDone()

    @Slot()
    def onFail(self, reason):
        self.statusBar.showColoredMessage(reason, False, 0)
        self.taskDone()

    @Slot()
    def onProgress(self, numDone, numTotal, imgFile):
        self.progressBar.setRange(0, numTotal)
        self.progressBar.setValue(numDone)

        if imgFile:
            self.statusBar.showMessage("Wrote " + imgFile)

    @Slot()
    def onProgressMessage(self, message):
        self.statusBar.showMessage(message)

    def taskDone(self):
        self.btnStart.setText("Start Batch Scale")
        self.progressBar.setRange(0, 1)
        self.progressBar.reset()
        self._task = None



class BatchScaleTask(BatchTask):
    def __init__(self, log, filelist, scaleFunc, pathSettings: export.PathSettings):
        super().__init__("scale", log, filelist)
        self.scaleFunc      = scaleFunc
        self.pathTemplate   = pathSettings.pathTemplate
        self.extension      = pathSettings.extension
        self.overwriteFiles = pathSettings.overwriteFiles

        self.interpUp       = None
        self.interpDown     = None
        self.format: Format = None

    def runPrepare(self):
        self.parser = export.ExportVariableParser()

    def runProcessFile(self, imgFile: str) -> str:
        image = Image.open(imgFile)
        w, h = self.scaleFunc(image.width, image.height)

        if (w != image.width) or (h != image.height):
            interp = self.interpUp if (w>image.width or h>image.height) else self.interpDown
            image = image.resize((w, h), resample=interp)

        if convertMode := self.format.conversion.get(image.mode):
            self.log(f"Converting mode from {image.mode} to {convertMode}")
            image = image.convert(convertMode)

        self.parser.setup(imgFile)
        self.parser.width = w
        self.parser.height = h

        path = self.parser.parsePath(self.pathTemplate, self.extension, self.overwriteFiles)
        export.createFolders(path, self.log)
        image.save(path, **self.format.saveParams)
        return path
