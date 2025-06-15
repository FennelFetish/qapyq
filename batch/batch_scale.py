from PySide6 import QtWidgets
from PySide6.QtCore import Slot
from PIL import Image
from config import Config
from lib import qtlib
import tools.scale as scale
import ui.export_settings as export
from .batch_task import BatchTask, BatchTaskHandler, BatchUtil
from .batch_log import BatchLog


class BatchScale(QtWidgets.QWidget):
    EXPORT_PRESET_KEY = "batch-scale"

    def __init__(self, tab, logWidget: BatchLog, bars):
        super().__init__()
        self.tab = tab
        self.logWidget = logWidget
        self.taskHandler = BatchTaskHandler(bars, "Scale", self.createTask)

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
        layout.addWidget(self.taskHandler.btnStart, 3, 0, 1, 2)

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

        groupBox = QtWidgets.QGroupBox("Target Size")
        groupBox.setLayout(self.scaleModeLayout)
        return groupBox

    def _buildExportSettings(self):
        layout = QtWidgets.QFormLayout()

        self.cboInterpUp = QtWidgets.QComboBox()
        self.cboInterpUp.addItems(export.INTERP_MODES_PIL.keys())
        self.cboInterpUp.setCurrentIndex(4) # Default: Lanczos
        layout.addRow("Interpolation Up:", self.cboInterpUp)

        self.cboInterpDown = QtWidgets.QComboBox()
        self.cboInterpDown.addItems(export.INTERP_MODES_PIL.keys())
        self.cboInterpDown.setCurrentIndex(3) # Default: Area
        layout.addRow("Interpolation Down:", self.cboInterpDown)

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


    def _confirmStart(self) -> bool:
        ops = [f"Resize the images using the '{self.cboScaleMode.currentText()}' mode"]

        if self.pathSettings.overwriteFiles:
            ops.append( qtlib.htmlRed("Overwrite existing images!") )
        else:
            ops.append("Save images using new filenames with an increasing counter")

        return BatchUtil.confirmStart("Scale", self.tab.filelist.getNumFiles(), ops, self)

    def saveExportPreset(self):
        Config.exportPresets[self.EXPORT_PRESET_KEY] = {
            "path_template": self.pathSettings.pathTemplate,
            "overwrite": self.pathSettings.overwriteFiles
        }


    def createTask(self) -> BatchTask | None:
        if not self._confirmStart():
            return

        self.saveExportPreset()

        log = self.logWidget.addEntry("Scale")
        scaleFunc = self.selectedScaleMode.getScaleFunc()
        task = BatchScaleTask(log, self.tab.filelist, scaleFunc, self.pathSettings)
        task.interpUp   = export.INTERP_MODES_PIL[ self.cboInterpUp.currentText() ]
        task.interpDown = export.INTERP_MODES_PIL[ self.cboInterpDown.currentText() ]
        return task



class BatchScaleTask(BatchTask):
    def __init__(self, log, filelist, scaleFunc, pathSettings: export.PathSettings):
        super().__init__("scale", log, filelist)
        self.scaleFunc      = scaleFunc
        self.pathTemplate   = pathSettings.pathTemplate
        self.overwriteFiles = pathSettings.overwriteFiles

        self.interpUp       = None
        self.interpDown     = None

    def runPrepare(self):
        self.parser = export.ExportVariableParser()

    def runProcessFile(self, imgFile: str) -> str:
        image = Image.open(imgFile)
        w, h = self.scaleFunc(image.width, image.height)

        if (w != image.width) or (h != image.height):
            interp = self.interpUp if (w>image.width or h>image.height) else self.interpDown
            image = image.resize((w, h), resample=interp)

        self.parser.setup(imgFile)
        self.parser.width = w
        self.parser.height = h

        path = self.parser.parsePath(self.pathTemplate, self.overwriteFiles)
        export.saveImagePIL(path, image, self.log)
        return path
