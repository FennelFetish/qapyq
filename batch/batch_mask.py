from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QSignalBlocker
from PySide6.QtGui import QImageReader
import cv2 as cv
import numpy as np
from config import Config
from lib import qtlib
from lib.mask_macro import MaskingMacro
from lib.mask_macro_vis import MacroVisualization
from infer import Inference
from .batch_task import BatchTask
import ui.export_settings as export


# TODO: Store detections in json (or separate batch detect?)


class BatchMask(QtWidgets.QWidget):
    EXPORT_PRESET_KEY = "batch-mask"

    def __init__(self, tab, logSlot, progressBar, statusBar):
        super().__init__()
        self.tab = tab
        self.log = logSlot
        self.progressBar: QtWidgets.QProgressBar = progressBar
        self.statusBar: qtlib.ColoredMessageStatusBar = statusBar

        self.parser = export.ExportVariableParser()
        self.parser.setup(self.tab.filelist.getCurrentFile(), None)

        config = Config.exportPresets.get(self.EXPORT_PRESET_KEY, {})
        self.pathSettings = export.PathSettings(self.parser, showInfo=False)
        self.pathSettings.pathTemplate   = config.get("path_template", "{{path}}-masklabel")
        self.pathSettings.overwriteFiles = config.get("overwrite", True)

        self._task = None
        self._build()
        self.reloadMacros()

    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setRowStretch(0, 1)
        layout.setRowStretch(1, 0)
        layout.setRowStretch(2, 0)

        layout.addWidget(self._buildMacroSettings(), 0, 0)
        layout.addWidget(self._buildDestinationSettings(), 1, 0)

        self.btnStart = QtWidgets.QPushButton("Start Batch Mask")
        self.btnStart.clicked.connect(self.startStop)
        layout.addWidget(self.btnStart, 2, 0)

        self.setLayout(layout)

    def _buildMacroSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 0)

        row = 0
        self.cboMacro = QtWidgets.QComboBox()
        self.cboMacro.currentIndexChanged.connect(self._onMacroChanged)
        layout.addWidget(QtWidgets.QLabel("Macro:"), row, 0)
        layout.addWidget(self.cboMacro, row, 1)

        btnReloadMacros = QtWidgets.QPushButton("Reload Macros")
        btnReloadMacros.clicked.connect(self.reloadMacros)
        layout.addWidget(btnReloadMacros, row, 2)

        row += 1
        self.macroVis = MacroVisualization()
        layout.addWidget(self.macroVis, row, 0, 1, 3)

        groupBox = QtWidgets.QGroupBox("Generate Mask")
        groupBox.setLayout(layout)
        return groupBox

    def _buildDestinationSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 1)
        layout.setColumnMinimumWidth(2, 20)
        layout.setRowStretch(0, 0)
        layout.setRowStretch(1, 0)
        layout.setRowStretch(2, 0)

        row = 0
        self.cboDestType = QtWidgets.QComboBox()
        self.cboDestType.addItem("Separate Image  (Max 4 Layers)", "file")
        self.cboDestType.addItem("Alpha Channel  (Max 1 Layer)", "alpha")
        layout.addWidget(QtWidgets.QLabel("Save in:"), row, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.cboDestType, row, 1)

        layout.addWidget(self.pathSettings, row, 3, 3, 1)

        row += 1
        self.lblFormat = QtWidgets.QLabel("Format:")
        layout.addWidget(self.lblFormat, row, 0, Qt.AlignmentFlag.AlignTop)

        self.cboFormat = QtWidgets.QComboBox()
        self.cboFormat.addItems(["PNG", "WEBP"])
        self.cboFormat.currentTextChanged.connect(self._onExtensionChanged)
        self._onExtensionChanged(self.cboFormat.currentText())
        layout.addWidget(self.cboFormat, row, 1)

        groupBox = QtWidgets.QGroupBox("Destination")
        groupBox.setLayout(layout)
        return groupBox


    def onFileChanged(self, file: str):
        self.parser.setup(file)

        if pixmap := self.tab.imgview.image.pixmap():
            self.parser.width = pixmap.width()
            self.parser.height = pixmap.height()
        else:
            self.parser.width, self.parser.height = 0, 0

        self.pathSettings.updatePreview()


    @Slot()
    def _onExtensionChanged(self, ext: str):
        self.pathSettings.extension = ext
        self.pathSettings.updatePreview()


    @Slot()
    def reloadMacros(self):
        with QSignalBlocker(self.cboMacro):
            selectedText = self.cboMacro.currentText()
            self.cboMacro.clear()
            for name, path in MaskingMacro.loadMacros():
                self.cboMacro.addItem(name, path)

            index = max(0, self.cboMacro.findText(selectedText))
            self.cboMacro.setCurrentIndex(index)
        
        self._onMacroChanged(index)

    def _onMacroChanged(self, index):
        path = self.cboMacro.itemData(index)
        self.macroVis.reload(path)


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

            macroPath = self.cboMacro.currentData()
            saveMode = self.cboDestType.currentData()
            self._task = BatchMaskTask(self.log, self.tab.filelist, macroPath, saveMode, self.pathSettings)

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
    def onProgress(self, numDone, numTotal, maskFile):
        self.progressBar.setRange(0, numTotal)
        self.progressBar.setValue(numDone)

        if maskFile:
            self.statusBar.showMessage("Wrote " + maskFile)

    @Slot()
    def onProgressMessage(self, message):
        self.statusBar.showMessage(message)

    def taskDone(self):
        self.btnStart.setText("Start Batch Mask")
        self.progressBar.setRange(0, 1)
        self.progressBar.reset()
        self._task = None



class BatchMaskTask(BatchTask):
    def __init__(self, log, filelist, macroPath: str, saveMode: str, pathSettings: export.PathSettings):
        super().__init__("mask", log, filelist)
        self.macroPath      = macroPath
        self.saveMode       = saveMode # file / alpha

        self.pathTemplate   = pathSettings.pathTemplate
        self.extension      = pathSettings.extension
        self.overwriteFiles = pathSettings.overwriteFiles


    def runPrepare(self):
        self.parser = export.ExportVariableParser()
        self.macro = MaskingMacro()
        self.macro.loadFrom(self.macroPath)

    def runProcessFile(self, imgFile: str) -> str:
        if self.saveMode == "file":
            layers = self.processAsSeparateFile(imgFile)
        else:
            layers = self.processAsAlpha(imgFile)

        # BGRA, shape: (h, w, channels)
        # Creates a copy of the data.
        combined = np.dstack(layers)
        h, w = combined.shape[:2]

        self.parser.setup(imgFile)
        self.parser.width = w
        self.parser.height = h

        path = self.parser.parsePath(self.pathTemplate, self.extension, self.overwriteFiles)
        export.saveImage(path, combined, self.log)
        return path


    def processAsSeparateFile(self, imgFile: str) -> list[np.ndarray]:
        imgReader = QImageReader(imgFile)
        imgSize = imgReader.size()
        w, h = imgSize.width(), imgSize.height()

        layers = [ np.zeros((h, w), dtype=np.uint8) ]
        layers, layerChanged = self.macro.run(imgFile, layers)
        layers = layers[:4]

        # Can't write images with only 2 channels. Need 1/3/4 channels.
        if len(layers) == 2:
            layers.append( np.zeros_like(layers[0]) )

        # Reverse order of first 3 layers to convert from BGR(A) to RGB(A)
        layers[:3] = layers[2::-1]
        return layers


    def processAsAlpha(self, imgFile: str) -> list[np.ndarray]:
        mat = cv.imread(imgFile, cv.IMREAD_UNCHANGED)
        h, w = mat.shape[:2]

        channels = mat.shape[2] if len(mat.shape) > 2 else 1
        if channels == 1:
            imgChannels = [mat] * 3
        else:
            imgChannels = list(cv.split(mat))[:3]

        layers = [ np.zeros((h, w), dtype=np.uint8) ]
        layers, layerChanged = self.macro.run(imgFile, layers)
        imgChannels.append(layers[0])
        return imgChannels
