from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QSignalBlocker
from PySide6.QtGui import QImageReader
import cv2 as cv
import numpy as np
from config import Config
from lib import qtlib
from lib.mask_macro import MaskingMacro, MacroOp
from infer import Inference
from .batch_task import BatchTask
import ui.export_settings as export


SAVE_PARAMS = {
    "PNG":  [cv.IMWRITE_PNG_COMPRESSION, 9],
    "WEBP": [cv.IMWRITE_WEBP_QUALITY, 100]
}


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
        self.cboDestType.currentIndexChanged.connect(self._onDestTypeChanged)
        layout.addWidget(QtWidgets.QLabel("Save in:"), row, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.cboDestType, row, 1)

        layout.addWidget(self.pathSettings, row, 3, 3, 1)

        row += 1
        self.lblFormat = QtWidgets.QLabel("Format:")
        layout.addWidget(self.lblFormat, row, 0, Qt.AlignmentFlag.AlignTop)

        self.cboFormat = QtWidgets.QComboBox()
        self.cboFormat.addItems(SAVE_PARAMS.keys())
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
    def _onDestTypeChanged(self, index):
        target = self.cboDestType.itemData(index)
        enabled = (target == "file")

        # for widget in (self.lblFormat, self.cboFormat, self.pathSettings):
        #     widget.setEnabled(enabled)

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
            saveParams = SAVE_PARAMS[ self.cboFormat.currentText() ]
            self._task = BatchMaskTask(self.log, self.tab.filelist, macroPath, saveMode, saveParams, self.pathSettings)

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



# TODO: Visualization with layers in columns. Operations in rows.
#       Layer blending with arrows, like Sequence Diagram.
#       Layout above path settings.
class MacroVisualization(QtWidgets.QScrollArea):
    def __init__(self):
        super().__init__()
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setWidgetResizable(True)

        #self.layerColors = ["#1f3b3f", "#3f1f31", "#283f1f", "#201f3f"]

        self.gridLayout = QtWidgets.QGridLayout()

        widget = QtWidgets.QWidget()
        widget.setLayout(self.gridLayout)
        self.setWidget(widget)
    
    def clear(self):
        while self.gridLayout.count():
            item = self.gridLayout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def reload(self, path: str):
        macro = MaskingMacro()
        macro.loadFrom(path)

        self.clear()
        self.gridLayout.addWidget(MacroOpLabel("Layer 0", bold=True), 0, 0)
        self.gridLayout.addWidget(MacroOpLabel("Layer 1", bold=True), 0, 1)
        self.gridLayout.addWidget(MacroOpLabel("Layer 2", bold=True), 0, 2)
        self.gridLayout.addWidget(MacroOpLabel("Layer 3", bold=True), 0, 3)

        colors = ["#1f3b3f", "#3f1f31", "#283f1f", "#201f3f"]

        row = 1
        col = 0
        maxCol = 0

        for op in macro.operations:
            color = colors[col]
            c = col
            match op.op:
                case MacroOp.AddLayer:
                    maxCol += 1
                    color = colors[maxCol]
                    c = maxCol
                case MacroOp.DeleteLayer:
                    maxCol -= 1
                    c = int(op.args.get("index", 0))
                    del colors[c] # TODO: Refill color array after deletion
                    col = min(maxCol, col)
                case MacroOp.SetLayer:
                    col = int(op.args.get("index", 0))
                    continue
                case MacroOp.BlendLayers:
                    color = [color, colors[ int(op.args.get("srcLayer", 0)) ]]

            opLabel = MacroOpLabel(op.op.name, color, args=op.args)
            self.gridLayout.addWidget(opLabel, row, c)
            row += 1

        self.gridLayout.addWidget(QtWidgets.QWidget(), row, 0)

    # def reload(self, path: str):
    #     macro = MaskingMacro()
    #     macro.loadFrom(path)

    #     self.clear()
    #     self.gridLayout.addWidget(MacroOpLabel("Layer 0", self.layerColors[0], True), 0, 0)
    #     self.gridLayout.addWidget(MacroOpLabel("Layer 1", self.layerColors[1], True), 0, 1)
    #     self.gridLayout.addWidget(MacroOpLabel("Layer 2", self.layerColors[2], True), 0, 2)
    #     self.gridLayout.addWidget(MacroOpLabel("Layer 3", self.layerColors[3], True), 0, 3)

    #     row = 1
    #     col = 0
    #     maxCol = 0
    #     colMap = {0:0, 1:1, 2:2, 3:3}

    #     for op in macro.operations:
    #         color = "#161616"
    #         c = colMap[col]
    #         match op.op:
    #             case MacroOp.AddLayer:
    #                 maxCol += 1
    #                 colMap[maxCol] = maxCol
    #                 c = maxCol
    #             case MacroOp.DeleteLayer:
    #                 i = int(op.args.get("index", 0))
    #                 c = colMap[i]
    #                 for k, v in colMap.items():
    #                     if k>=i:
    #                         colMap[k] = v+1
    #             case MacroOp.SetLayer:
    #                 col = int(op.args.get("index", 0))
    #                 continue
    #             case MacroOp.BlendLayers:
    #                 color = self.layerColors[ int(op.args.get("srcLayer", 0)) ]

    #         opLabel = MacroOpLabel(op.op.name, color, args=op.args)
    #         self.gridLayout.addWidget(opLabel, row, c)
    #         row += 1

    #     self.gridLayout.addWidget(QtWidgets.QWidget(), row, 0)


class MacroOpLabel(QtWidgets.QLabel):
    def __init__(self, title, color: str | list = "#161616", bold=False, args: dict={}):
        params = []
        for k, v in args.items():
            if type(v) == float:
                params.append(f"{k}={v:.2f}")
            else:
                params.append(f"{k}={v}")
        
        if params:
            title += ": " + ", ".join(params)

        super().__init__(title)
        fontWeight = "900" if bold else "400"
        if type(color) == list:
            background = "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 " + color[0] + ", stop:1 " + color[1] + ")"
            #background = "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 " + color[1] + ", stop:0.5 " + color[0] + ", stop:1 " + color[1] + ")"
            #background = "background: qradialgradient(cx:0.5, cy:0.5, fx:0.5, fy:0.5, radius:1, stop:0 " + color[0] + ", stop:1 " + color[1] + ")"
        else:
            background = "background-color: " + str(color)

        self.setStyleSheet("QLabel{font-weight:" + fontWeight + "; color: #fff; " + background + "; border: 1px solid #161616; border-radius: 8px}")
        self.setFixedHeight(30 if bold else 24)



class BatchMaskTask(BatchTask):
    def __init__(self, log, filelist, macroPath: str, saveMode: str, saveParams: list, pathSettings: export.PathSettings):
        super().__init__("mask", log, filelist)
        self.macroPath      = macroPath
        self.saveMode       = saveMode # file / alpha
        self.saveParams     = saveParams

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
        export.createFolders(path, self.log)
        cv.imwrite(path, combined, self.saveParams)
        return path


    def processAsSeparateFile(self, imgFile: str) -> list[np.ndarray]:
        imgReader = QImageReader(imgFile)
        imgSize = imgReader.size()
        w, h = imgSize.width(), imgSize.height()

        layers = [ np.zeros((h, w), dtype=np.uint8) ]
        layers, layerChanged = self.macro.run(imgFile, layers, 0)
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
        layers, layerChanged = self.macro.run(imgFile, layers, 0)
        imgChannels.append(layers[0])
        return imgChannels
