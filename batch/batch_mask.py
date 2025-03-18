import os
from enum import Enum
from typing import Callable
from PySide6 import QtWidgets
from PySide6.QtCore import QSignalBlocker, Qt, Slot
from PySide6.QtGui import QImageReader
import cv2 as cv
import numpy as np
from config import Config
from infer import Inference
from lib import qtlib
from lib.mask_macro import MaskingMacro
from lib.mask_macro_vis import MacroVisualization
import ui.export_settings as export
from .batch_task import BatchSignalHandler, BatchTask, BatchUtil


# TODO: Store detections in json (or separate batch detect?)

class MaskSrcMode(Enum):
    NewBlack       = "new-black"
    NewWhite       = "new-white"
    FileFirstLayer = "file-1"
    File4Layers    = "file-4"
    Alpha          = "alpha"

SRC_MODE_NEW_LAYERS = (MaskSrcMode.NewBlack, MaskSrcMode.NewWhite)

class MaskDestMode(Enum):
    File  = "file"
    Alpha = "alpha"


class BatchMask(QtWidgets.QWidget):
    EXPORT_PRESET_KEY_SRC  = "batch-mask-input"
    EXPORT_PRESET_KEY_DEST = "batch-mask"

    def __init__(self, tab, logSlot, progressBar, statusBar):
        super().__init__()
        self.tab = tab
        self.log = logSlot
        self.progressBar: QtWidgets.QProgressBar = progressBar
        self.statusBar: qtlib.ColoredMessageStatusBar = statusBar

        self.parser = export.ExportVariableParser()
        self.parser.setup(self.tab.filelist.getCurrentFile(), None)

        srcConfig = Config.exportPresets.get(self.EXPORT_PRESET_KEY_SRC, {})
        self.srcPathSettings = export.PathSettings(self.parser, showInfo=False)
        self.srcPathSettings.setAsInput()
        self.srcPathSettings.pathTemplate = srcConfig.get("path_template", "{{path}}-masklabel.png")

        destConfig = Config.exportPresets.get(self.EXPORT_PRESET_KEY_DEST, {})
        self.destPathSettings = export.PathSettings(self.parser, showInfo=False, showSkip=True)
        self.destPathSettings.pathTemplate   = destConfig.get("path_template", "{{path}}-masklabel.png")
        self.destPathSettings.overwriteFiles = destConfig.get("overwrite", True)

        self._task = None
        self._taskSignalHandler = None

        self._build()
        self.reloadMacros()

    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setRowStretch(0, 1)
        layout.setRowStretch(1, 0)
        layout.setRowStretch(2, 0)

        layout.addWidget(self._buildMacroSettings(), 0, 0)
        layout.addWidget(self._buildInputSettings(), 1, 0)
        layout.addWidget(self._buildDestinationSettings(), 2, 0)
        self._onSrcModeChanged(self.cboSrcType.currentIndex())

        self.btnStart = QtWidgets.QPushButton("Start Batch Mask")
        self.btnStart.clicked.connect(self.startStop)
        layout.addWidget(self.btnStart, 3, 0)

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

    def _buildInputSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 1)
        layout.setColumnMinimumWidth(0, 70)
        layout.setColumnMinimumWidth(1, 220)
        layout.setColumnMinimumWidth(2, 8)

        row = 0
        self.cboSrcType = QtWidgets.QComboBox()
        self.cboSrcType.addItem("Create New (1 Layer)", MaskSrcMode.NewBlack)
        #self.cboSrcType.addItem("Create New (1 White Layer)", MaskSrcMode.NewWhite)
        self.cboSrcType.addItem("Separate Image (First Layer)", MaskSrcMode.FileFirstLayer)
        self.cboSrcType.addItem("Separate Image (4 Layers)", MaskSrcMode.File4Layers)
        self.cboSrcType.addItem("Alpha Channel (1 Layer)", MaskSrcMode.Alpha)
        self.cboSrcType.currentIndexChanged.connect(self._onSrcModeChanged)
        layout.addWidget(QtWidgets.QLabel("Load from:"), row, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.cboSrcType, row, 1)

        self.chkSkipNoInput = QtWidgets.QCheckBox("Skip processing if input mask is missing")
        layout.addWidget(self.chkSkipNoInput, row, 3)

        row += 1
        self.srcPathSettings.layout().setColumnMinimumWidth(0, 70)
        layout.addWidget(self.srcPathSettings, row, 0, 1, 4)

        groupBox = QtWidgets.QGroupBox("Input Layers")
        groupBox.setLayout(layout)
        return groupBox

    def _buildDestinationSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)
        layout.setColumnMinimumWidth(0, 70)
        layout.setColumnMinimumWidth(1, 220)

        row = 0
        self.cboDestType = QtWidgets.QComboBox()
        self.cboDestType.addItem("Separate Image  (Max 4 Layers)", MaskDestMode.File)
        self.cboDestType.addItem("Alpha Channel  (Max 1 Layer)", MaskDestMode.Alpha)
        layout.addWidget(QtWidgets.QLabel("Save in:"), row, 0)
        layout.addWidget(self.cboDestType, row, 1)

        row += 1
        self.destPathSettings.layout().setColumnMinimumWidth(0, 70)
        layout.addWidget(self.destPathSettings, row, 0, 1, 3)

        groupBox = QtWidgets.QGroupBox("Destination")
        groupBox.setLayout(layout)
        return groupBox


    def onFileChanged(self, file: str):
        self.parser.setup(file)
        self.parser.setImageDimension(self.tab.imgview.image.pixmap())
        self.destPathSettings.updatePreview()


    @Slot()
    def _onSrcModeChanged(self, index: int):
        mode = self.cboSrcType.itemData(index)
        pathEnabled = (mode in (MaskSrcMode.FileFirstLayer, MaskSrcMode.File4Layers))
        self.srcPathSettings.setEnabled(pathEnabled)

        skipEnabled = (mode not in SRC_MODE_NEW_LAYERS)
        self.chkSkipNoInput.setEnabled(skipEnabled)


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
        if path := self.cboMacro.itemData(index):
            self.macroVis.reload(path)


    def _confirmStart(self) -> bool:
        ops = [f"Generate masks using the '{self.cboMacro.currentText()}' macro"]

        if self.destPathSettings.skipExistingFiles:
            ops.append("Skip the mask generation if the target file already exists")

        srcMode: MaskSrcMode = self.cboSrcType.currentData()
        match srcMode:
            case MaskSrcMode.NewBlack:
                ops.append("Start the mask with 1 new black layer")
            case MaskSrcMode.NewWhite:
                ops.append("Start the mask with 1 new white layer")
            case MaskSrcMode.FileFirstLayer:
                ops.append("Start the mask with the first layer of an existing mask")
            case MaskSrcMode.File4Layers:
                ops.append("Start the mask with 4 layers of an existing mask")
            case MaskSrcMode.Alpha:
                ops.append("Start the mask with the alpha channel from the image")

        if srcMode not in SRC_MODE_NEW_LAYERS:
            if self.chkSkipNoInput.isChecked():
                ops.append("Skip processing if the input mask doesn't exist")
            else:
                ops.append("Start the mask with empty layers if the input mask doesn't exist")

        if self.cboDestType.currentData() == MaskDestMode.File:
            ops.append("Store the mask as a separate image")
        else:
            ops.append("Store the mask as the alpha channel in the image")

        if self.destPathSettings.overwriteFiles:
            ops.append( qtlib.htmlRed("Overwrite existing images!") )
        elif self.destPathSettings.skipExistingFiles:
            ops.append("Save images using new filenames")
        else:
            ops.append("Save images using new filenames with an increasing counter")

        return BatchUtil.confirmStart("Mask", self.tab.filelist.getNumFiles(), ops, self)


    def saveExportPreset(self):
        Config.exportPresets[self.EXPORT_PRESET_KEY_SRC] = {
            "path_template": self.srcPathSettings.pathTemplate
        }

        Config.exportPresets[self.EXPORT_PRESET_KEY_DEST] = {
            "path_template": self.destPathSettings.pathTemplate,
            "overwrite": self.destPathSettings.overwriteFiles
        }

    @Slot()
    def startStop(self):
        if self._task:
            if BatchUtil.confirmAbort(self):
                self._task.abort()
            return

        if not self._confirmStart():
            return

        self.saveExportPreset()
        self.btnStart.setText("Abort")

        macroPath = self.cboMacro.currentData()
        saveMode = self.cboDestType.currentData()
        self._task = BatchMaskTask(self.log, self.tab.filelist, macroPath, saveMode, self.destPathSettings)

        skipNonExistingSource = self.chkSkipNoInput.isChecked()
        srcMode: MaskSrcMode = self.cboSrcType.currentData()
        match srcMode:
            case MaskSrcMode.NewBlack:
                self._task.maskSource = newBlackMaskSource
            case MaskSrcMode.NewWhite:
                self._task.maskSource = newWhiteMaskSource
            case MaskSrcMode.FileFirstLayer:
                self._task.maskSource = createFileMaskSource(self.srcPathSettings.pathTemplate, 1, skipNonExistingSource)
            case MaskSrcMode.File4Layers:
                self._task.maskSource = createFileMaskSource(self.srcPathSettings.pathTemplate, 4, skipNonExistingSource)
            case MaskSrcMode.Alpha:
                self._task.maskSource = createAlphaMaskSource(skipNonExistingSource)
            case _:
                raise ValueError("Invalid mask source mode")

        self._taskSignalHandler = BatchSignalHandler(self.statusBar, self.progressBar, self._task)
        self._taskSignalHandler.finished.connect(self.taskDone)
        Inference().queueTask(self._task)

    def taskDone(self):
        self.btnStart.setText("Start Batch Mask")
        self._task = None
        self._taskSignalHandler = None



def newBlackMaskSource(imgPath: str, w: int, h: int) -> list[np.ndarray]:
    return [ np.zeros((h, w), dtype=np.uint8) ]

def newWhiteMaskSource(imgPath: str, w: int, h: int) -> list[np.ndarray]:
    return [ np.full((h, w), 255, dtype=np.uint8) ]


def createFileMaskSource(pathTemplate: str, numLayers: int, skipNonExisting: bool):
    parser = export.ExportVariableParser()

    def loadMask(path: str, w: int, h: int) -> list[np.ndarray]:
        maskMat = cv.imread(path, cv.IMREAD_UNCHANGED)
        maskH, maskW = maskMat.shape[:2]
        if maskW != w or maskH != h:
            raise ValueError("Size of loaded mask does not match image size")

        layers = list(cv.split(maskMat))
        layers[:3] = layers[2::-1] # Convert BGR(A) -> RGB(A)

        # Ensure minimum number of layers
        while len(layers) < numLayers:
            layers.append( np.zeros((h, w), dtype=np.uint8) )

        # Ensure maximum number of layers
        return layers[:numLayers]

    def fileMaskSource(imgPath: str, w: int, h: int) -> list[np.ndarray]:
        parser.setup(imgPath)
        parser.width  = w
        parser.height = h

        path = parser.parsePath(pathTemplate, True)
        if os.path.exists(path):
            return loadMask(path, w, h)

        if skipNonExisting:
            raise MaskSkipException()
        return [ np.zeros((h, w), dtype=np.uint8) for _ in range(numLayers) ]

    return fileMaskSource


def createAlphaMaskSource(skipNonExisting: bool):
    def alphaMaskSource(imgPath: str, w: int, h: int) -> list[np.ndarray]:
        imgMat = cv.imread(imgPath, cv.IMREAD_UNCHANGED)
        channels = imgMat.shape[2] if len(imgMat.shape) > 2 else 1
        if channels >= 4:
            return [ np.ascontiguousarray(imgMat[..., 3].copy()) ]

        if skipNonExisting:
            raise MaskSkipException()
        return [ np.zeros((h, w), dtype=np.uint8) ]

    return alphaMaskSource



class MaskSkipException(Exception): pass

class BatchMaskTask(BatchTask):
    def __init__(self, log, filelist, macroPath: str, saveMode: MaskDestMode, destPathSettings: export.PathSettings):
        super().__init__("mask", log, filelist)
        self.macroPath      = macroPath
        self.saveMode       = saveMode

        self.pathTemplate   = destPathSettings.pathTemplate
        self.overwriteFiles = destPathSettings.overwriteFiles
        self.skipExistingFiles = destPathSettings.skipExistingFiles

        self.maskSource: Callable = None
        self.maskProcessFunc: Callable = None


    def runPrepare(self):
        self.parser = export.ExportVariableParser()
        self.macro = MaskingMacro()
        self.macro.loadFrom(self.macroPath)

        match self.saveMode:
            case MaskDestMode.File:  self.maskProcessFunc = self.processAsSeparateFile
            case MaskDestMode.Alpha: self.maskProcessFunc = self.processAsAlpha
            case _: raise ValueError("Invalid destination mode")

    def runProcessFile(self, imgFile: str) -> str | None:
        self.parser.setup(imgFile)

        try:
            path, layers = self.maskProcessFunc(imgFile)
        except MaskSkipException:
            return None

        # BGRA, shape: (h, w, channels)
        # Creates a copy of the data.
        combined = np.dstack(layers)

        export.saveImage(path, combined, self.log)
        return path

    def checkDestinationPath(self, w: int, h: int) -> str:
        self.parser.width = w
        self.parser.height = h

        noCounter = self.overwriteFiles or self.skipExistingFiles
        path = self.parser.parsePath(self.pathTemplate, noCounter)
        if self.skipExistingFiles and os.path.exists(path):
            raise MaskSkipException()
        return path


    def processAsSeparateFile(self, imgFile: str) -> tuple[str, list[np.ndarray]]:
        imgReader = QImageReader(imgFile)
        imgSize = imgReader.size()
        w, h = imgSize.width(), imgSize.height()

        path = self.checkDestinationPath(w, h)

        layers = self.maskSource(imgFile, w, h)
        layers, layerChanged = self.macro.run(imgFile, layers)
        layers = layers[:4]

        # Can't write images with only 2 channels. Need 1/3/4 channels.
        if len(layers) == 2:
            layers.append( np.zeros_like(layers[0]) )

        # Reverse order of first 3 layers to convert from BGR(A) to RGB(A)
        layers[:3] = layers[2::-1]
        return path, layers


    def processAsAlpha(self, imgFile: str) -> tuple[str, list[np.ndarray]]:
        mat = cv.imread(imgFile, cv.IMREAD_UNCHANGED)
        h, w = mat.shape[:2]

        path = self.checkDestinationPath(w, h)

        layers = self.maskSource(imgFile, w, h)
        layers, layerChanged = self.macro.run(imgFile, layers)

        channels = mat.shape[2] if len(mat.shape) > 2 else 1
        if channels == 1:
            imgChannels = [mat] * 3
        else:
            imgChannels = list(cv.split(mat))[:3]

        imgChannels.append(layers[0])
        return path, imgChannels
