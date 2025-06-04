import os, superqt
from difflib import SequenceMatcher
from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal, QSignalBlocker, QRunnable, QObject
import cv2 as cv
import numpy as np
from PIL import Image
from datetime import datetime
from lib import qtlib, template_parser
from infer.model_settings import ModelSettingsWindow, ScaleModelSettings
from config import Config


INTERP_MODES = {
    "Nearest": cv.INTER_NEAREST,
    "Linear":  cv.INTER_LINEAR,
    "Cubic":   cv.INTER_CUBIC,
    "Area":    cv.INTER_AREA,
    "Lanczos": cv.INTER_LANCZOS4
}

INTERP_MODES_PIL = {
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

# https://pillow.readthedocs.io/en/stable/handbook/concepts.html#concept-modes
FORMATS = {
    "PNG":  Format({"optimize": True, "compress_level": 9}),
    "JPG":  Format({"optimize": True, "quality": 100, "subsampling": 0}, {"RGBA": "RGB", "P": "RGB"}),
    "WEBP": Format({"lossless": True, "quality": 100, "exact": True}),
    "TIFF": Format({"compression": "tiff_lzw"})
}

EXTENSION_MAP = {
    "JPEG": "JPG"
}


def getFormat(extension: str):
    key = extension.lstrip('.').upper()
    if format := FORMATS.get(key):
        return format
    key = EXTENSION_MAP.get(key, "")
    return FORMATS.get(key)

def saveImage(path: str, mat: np.ndarray, logger=print, convertFromBGR=True):
    if convertFromBGR:
        mat[..., :3] = mat[..., 2::-1] # Convert BGR(A) -> RGB(A)

    img = Image.fromarray(mat.squeeze()) # No copy!
    saveImagePIL(path, img, logger)

def saveImagePIL(path: str, img: Image.Image, logger=print):
    ext = os.path.splitext(path)[1]
    format = getFormat(ext)

    createFolders(path, logger)
    if not format:
        img.save(path)
        return

    if convertMode := format.conversion.get(img.mode):
        logger(f"Save Image: Converting color mode from {img.mode} to {convertMode}")
        img = img.convert(convertMode)

    img.save(path, **format.saveParams)

def createFolders(filename, logger=print) -> None:
    folder = os.path.dirname(filename)
    if not os.path.exists(folder):
        logger(f"Creating folder: {folder}")
        os.makedirs(folder)



INVALID_CHARS = str.maketrans('', '', '\n\r\t')


class ExportWidget(QtWidgets.QWidget):
    MODE_AUTO = "auto"
    MODE_MANUAL = "manual"

    FILE_FILTER = "Images (*.png *.jpg *.jpeg *.webp);;All Files (*)"


    def __init__(self, configKey: str, filelist, showInterpolation=True):
        super().__init__()
        self.configKey = configKey
        self.filelist = filelist
        self.showInterpolation = showInterpolation
        self._defaultPath = Config.pathExport

        config = Config.exportPresets.get(configKey, {})
        self.pathTemplate   = config.get("path_template", "{{name}}_{{date}}_{{time}}_{{w}}x{{h}}.png")
        self.overwriteFiles = config.get("overwrite", False)

        self.parser = ExportVariableParser()

        self._build()
        self._onSaveModeChanged(self.cboSaveMode.currentIndex())

    def _build(self):
        collapsible = superqt.QCollapsible("Export Settings")
        collapsible.layout().setContentsMargins(2, 2, 2, 0)
        collapsible.setFrameStyle(QtWidgets.QFrame.Shape.NoFrame)
        collapsible.setLineWidth(0)
        collapsible.addWidget(self._buildSettings())

        self.txtPathSample = ClickableTextEdit()
        self.txtPathSample.setToolTip("Click to change export path")
        self.txtPathSample.setReadOnly(True)
        self.txtPathSample.clicked.connect(self.openExportSettings)
        qtlib.setMonospace(self.txtPathSample, 0.9)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(collapsible)
        layout.addWidget(self.txtPathSample)
        self.setLayout(layout)

    def _buildSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.cboScalePreset = ScalePresetComboBox()
        if self.showInterpolation:
            lblScaling = QtWidgets.QLabel("<a href='model_settings'>Scaling</a>:")
            lblScaling.linkActivated.connect(self.cboScalePreset.showModelSettings)
            layout.addWidget(lblScaling, row, 0)
            layout.addWidget(self.cboScalePreset, row, 1)
            row += 1

        lblPath = QtWidgets.QLabel("<a href='export_settings'>Path:</a>")
        lblPath.linkActivated.connect(self.openExportSettings)
        self.cboSaveMode = QtWidgets.QComboBox()
        self.cboSaveMode.addItem("Template", self.MODE_AUTO)
        self.cboSaveMode.addItem("Dialog", self.MODE_MANUAL)
        self.cboSaveMode.currentIndexChanged.connect(self._onSaveModeChanged)
        layout.addWidget(lblPath, row, 0)
        layout.addWidget(self.cboSaveMode, row, 1)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        return widget


    @Slot()
    def _onSaveModeChanged(self, index):
        enabled = (self.cboSaveMode.itemData(index) == self.MODE_AUTO)
        self.txtPathSample.setEnabled(enabled)

    @Slot()
    def openExportSettings(self):
        win = PathSettingsWindow(self, self.parser, self.pathTemplate, self.overwriteFiles)
        if win.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.pathTemplate   = win.pathSettings.pathTemplate
            self.overwriteFiles = win.pathSettings.overwriteFiles
            self.saveToPreset()
            self.updateSample()

    def saveToPreset(self):
        Config.exportPresets[self.configKey] = {
            "path_template": self.pathTemplate,
            "overwrite": self.overwriteFiles
        }

    @Slot()
    def updateSample(self):
        examplePath = self.getAutoExportPath(self.filelist.getCurrentFile())
        stylesheet = ""
        if os.path.exists(examplePath):
            stylesheet = f"color: {qtlib.COLOR_RED}"
        self.txtPathSample.setStyleSheet(stylesheet)

        examplePath = f"{os.sep}\n\n".join(os.path.split(examplePath))
        self.txtPathSample.setPlainText(examplePath)


    def getInterpolationMode(self, upscale):
        return self.cboScalePreset.getInterpolationMode(upscale)

    def getScaleConfig(self, scaleFactor: float):
        return self.cboScalePreset.getScaleConfig(scaleFactor)


    def setExportSize(self, width: int, height: int):
        self.parser.width = width
        self.parser.height = height


    def getExportPath(self, file: str) -> str:
        '''
        Returns empty string if manual saving was aborted.
        '''
        path = self.getAutoExportPath(file)
        if self.cboSaveMode.currentData() == self.MODE_AUTO:
            return path

        # Manually pick destination path: Use filename from path template
        path = os.path.basename(path)
        path = os.path.join(self._defaultPath, path)
        path, selectedFilter = QtWidgets.QFileDialog.getSaveFileName(self, "Save Image", path, self.FILE_FILTER)
        if not path:
            return ""

        path = os.path.abspath(path)
        ext = os.path.splitext(path)[1]
        if not ext:
            # Do not simply append an extension: That would bypass overwrite confirmation.
            QtWidgets.QMessageBox.warning(self, "Invalid Path", "The extension is missing from the filename.")
            return ""

        self._defaultPath = os.path.dirname(path)
        return path

    def getAutoExportPath(self, imgFile, forReading=False) -> str:
        self.parser.setup(imgFile)
        overwriteFiles = self.overwriteFiles or forReading
        return self.parser.parsePath(self.pathTemplate, overwriteFiles)



class PathSettings(QtWidgets.QWidget):
    INFO = """Available variables in path template:
    {{path}}      Image path
    {{path.ext}}  Image path with extension
    {{name}}      Image filename
    {{name.ext}}  Image filename with extension
    {{ext}}       Extension
    {{folder}}    Folder of image
    {{folder-1}}  Parent folder 1 (or 2, 3...)
    {{folder:/}}  Folder hierarchy from given path to image
    {{w}}         Width
    {{h}}         Height
    {{region}}    Crop region number
    {{date}}      Date yyyymmdd
    {{time}}      Time hhmmss

    Functions and values from json/txt file.

An increasing counter is appended when a file exists and overwriting is disabled.
The template must include a file extension.

Examples:
    {{name}}_{{w}}x{{h}}.webp
    {{path}}-masklabel.png
    /home/user/Pictures/{{w}}x{{h}}/{{folder}}/{{name}}_{{date}}.jpg
    {{name}}_{{tags.tags#replace:, :_}}.{{ext}}"""


    def __init__(self, parser, showInfo=True, showSkip=False) -> None:
        super().__init__()
        self._extension = "ext"

        self.parser: ExportVariableParser = parser
        self.highlighter = template_parser.VariableHighlighter()

        self._build(showInfo, showSkip)
        self.updatePreview()

    def _build(self, showInfo: bool, showSkip: bool):
        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)
        layout.setColumnStretch(3, 0)

        row = 0
        if showInfo:
            txtInfo = QtWidgets.QPlainTextEdit(self.INFO)
            txtInfo.setReadOnly(True)
            qtlib.setMonospace(txtInfo)
            layout.addWidget(txtInfo, row, 0, 1, 4)
            row += 1

        self.txtPathTemplate = QtWidgets.QPlainTextEdit()
        self.txtPathTemplate.textChanged.connect(self.updatePreview)
        qtlib.setMonospace(self.txtPathTemplate)
        qtlib.setShowWhitespace(self.txtPathTemplate)
        qtlib.setTextEditHeight(self.txtPathTemplate, 1)
        layout.addWidget(QtWidgets.QLabel("Template:"), row, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.txtPathTemplate, row, 1, 1, 2)

        self.btnChoosePath = QtWidgets.QPushButton("Choose Folder...")
        self.btnChoosePath.clicked.connect(self._choosePath)
        layout.addWidget(self.btnChoosePath, row, 3)

        row += 1
        self.txtPreview = QtWidgets.QPlainTextEdit()
        self.txtPreview.setReadOnly(True)
        qtlib.setMonospace(self.txtPreview)
        qtlib.setShowWhitespace(self.txtPreview)
        qtlib.setTextEditHeight(self.txtPreview, 2)
        layout.addWidget(QtWidgets.QLabel("Preview:"), row, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.txtPreview, row, 1, 1, 3)

        row += 1
        self.chkOverwrite = QtWidgets.QCheckBox("Overwrite existing files")
        self.chkOverwrite.toggled.connect(self._onOverwriteToggled)
        self.chkOverwrite.setChecked(False)
        layout.addWidget(self.chkOverwrite, row, 1)

        self.chkSkipExisting = QtWidgets.QCheckBox("Skip existing files")
        self.chkSkipExisting.toggled.connect(self._onSkipExistingToggled)
        self.chkSkipExisting.setChecked(False)
        if showSkip:
            layout.addWidget(self.chkSkipExisting, row, 2)

    def setAsInput(self):
        self.chkOverwrite.hide()
        self.chkSkipExisting.hide()
        self.overwriteFiles = True # Set to true to suppress adding counter


    @property
    def extension(self) -> str:
        return self._extension

    @extension.setter
    def extension(self, ext: str):
        self._extension = ext.lstrip(".").lower()


    @property
    def pathTemplate(self) -> str:
        template = self.txtPathTemplate.toPlainText()
        return template.translate(INVALID_CHARS)

    @pathTemplate.setter
    def pathTemplate(self, template: str):
        self.txtPathTemplate.setPlainText(template)


    @property
    def overwriteFiles(self) -> bool:
        return self.chkOverwrite.isChecked()

    @overwriteFiles.setter
    def overwriteFiles(self, overwrite: bool):
        self.chkOverwrite.setChecked(overwrite)

    @Slot()
    def _onOverwriteToggled(self, state: bool):
        style = f"color: {qtlib.COLOR_RED}" if state else None
        self.chkOverwrite.setStyleSheet(style)

        if state:
            self.skipExistingFiles = False
        self.chkSkipExisting.setEnabled(not state)


    @property
    def skipExistingFiles(self) -> bool:
        return self.chkSkipExisting.isChecked()

    @skipExistingFiles.setter
    def skipExistingFiles(self, skip: bool):
        self.chkSkipExisting.setChecked(skip)

    @Slot()
    def _onSkipExistingToggled(self, state: bool):
        if state:
            self.overwriteFiles = False
        self.chkOverwrite.setEnabled(not state)


    @Slot()
    def updatePreview(self):
        text = self.txtPathTemplate.toPlainText()
        textLen = len(text)
        text = text.translate(INVALID_CHARS)

        with QSignalBlocker(self.txtPathTemplate):
            # When newlines are pasted and removed, put text cursor at end of pasted text.
            lenDiff = textLen - len(text)
            if lenDiff != 0:
                cursor = self.txtPathTemplate.textCursor()
                cursorPos = cursor.position() - lenDiff
                self.txtPathTemplate.setPlainText(text)
                cursor.setPosition(cursorPos)
                self.txtPathTemplate.setTextCursor(cursor)

            text, varPositions = self.parser.parsePathWithPositions(text)
            self.txtPreview.setPlainText(text)
            self.highlighter.highlight(self.txtPathTemplate, self.txtPreview, varPositions, not self.isEnabled())

    def _choosePath(self):
        path = self.txtPathTemplate.toPlainText()
        path = path.replace("{{path}}", "{{name}}")
        path = path.replace("{{path.ext}}", "{{name.ext}}")

        # Keep dynamic path elements with variables
        head, tail = self.parser.splitPathByVars(path)
        path = head or Config.pathExport

        opts = QtWidgets.QFileDialog.Option.ShowDirsOnly
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose save folder", path, opts)
        if path:
            path = os.path.normpath(path)
            self.txtPathTemplate.setPlainText(os.path.join(path, tail))


    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        if enabled:
            self._onOverwriteToggled(self.chkOverwrite.isChecked())
        else:
            self.chkOverwrite.setStyleSheet("")
        self.updatePreview()


class PathSettingsWindow(QtWidgets.QDialog):
    def __init__(self, parent, parser, pathTemplate: str, overwriteFiles: bool) -> None:
        super().__init__(parent)
        self.pathSettings = PathSettings(parser)
        self.pathSettings.pathTemplate   = pathTemplate
        self.pathSettings.overwriteFiles = overwriteFiles

        self._build(self.pathSettings)

        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowTitle("Setup Export Path")
        self.resize(800, 600)

    def _build(self, exportSettings):
        layout = QtWidgets.QGridLayout(self)
        layout.addWidget(exportSettings, 0, 0, 1, 2)

        row = 1
        btnCancel = QtWidgets.QPushButton("Cancel")
        btnCancel.clicked.connect(self.reject)
        layout.addWidget(btnCancel, row, 0)

        btnApply = QtWidgets.QPushButton("Apply")
        btnApply.clicked.connect(self.accept)
        layout.addWidget(btnApply, row, 1)

        self.setLayout(layout)



class ExportVariableParser(template_parser.TemplateVariableParser):
    def __init__(self, imgPath: str = None):
        super().__init__(imgPath)
        self.stripAround = False
        self.stripMultiWhitespace = False
        self.width  = 0
        self.height = 0
        self.region = 0

    def setImageDimension(self, pixmap: QtGui.QPixmap | None):
        if pixmap:
            self.width = pixmap.width()
            self.height = pixmap.height()
        else:
            self.width, self.height = 0, 0


    def parsePath(self, pathTemplate: str, overwriteFiles: bool) -> str:
        path = self.parse(pathTemplate)
        path = path.translate(INVALID_CHARS)
        path = os.path.normpath(os.path.join(Config.pathExport, path))

        if overwriteFiles:
            return path

        path, extension = os.path.splitext(path)
        if len(extension) > 5: # Includes dot
            print(f"WARNING: File extension '{extension}' looks invalid")
            path = path + extension
            extension = ""

        head = path
        path = f"{head}{extension}"
        counter = 1
        while os.path.exists(path):
            path = f"{head}_{counter:03}{extension}"
            counter += 1

        return path

    def parsePathWithPositions(self, pathTemplate: str) -> tuple[str, list[list[int]]]:
        firstVarIdx = pathTemplate.find("{{")
        # Templates starting with {{path}} or {{path.ext}} will only become absolute paths after variable replacement.
        # In this case, Config.pathExport would be prefixed, resulting in a wrong path.
        if firstVarIdx < 0 or pathTemplate.startswith("{{path"):
            path, varPositions = self.parseWithPositions(pathTemplate)
        else:
            # Normalize part of path before the first variable
            pathHead = pathTemplate[:firstVarIdx] + "@" # The added character prevents removal of trailing slashes.
            pathHead = os.path.normpath(os.path.join(Config.pathExport, pathHead))
            pathHead = pathHead.removesuffix("@")
            lenHead = len(pathHead)

            pathTail = pathTemplate[firstVarIdx:]
            pathTail, varPositions = self.parseWithPositions(pathTail)
            path = pathHead + pathTail

            for pos in varPositions:
                pos[0] += firstVarIdx
                pos[1] += firstVarIdx
                pos[2] += lenHead
                pos[3] += lenHead

        pathNorm = path.translate(INVALID_CHARS)
        pathNorm = os.path.normpath(os.path.join(Config.pathExport, pathNorm))

        if len(pathNorm) != len(path):
            # Fix positions: Highlighting will be wrong if path elements were removed in normpath()
            varPositions = self._fixVarPositions(varPositions, path, pathNorm)

        return pathNorm, varPositions

    def _fixVarPositions(self, varPositions: list[list[int]], path: str, pathNorm: str) -> list[list[int]]:
        pathSplit = path.split(os.sep)
        pathNormSplit = pathNorm.split(os.sep)
        seqMatcher = SequenceMatcher(None, pathSplit, pathNormSplit, autojunk=False)

        # Accumulate shifts for variable positions.
        # Can't update variable positions in one loop: Need original positions for comparison.
        shifts = [[0, 0] for _ in varPositions]

        for op, i1, i2, j1, j2 in seqMatcher.get_opcodes():
            if op == "equal":
                continue
            if op != "delete":
                # No fix, don't highlight
                return []

            # Most cases work, but there are some where the detections of SequenceMatcher will mess with the highlighting.
            # Test template: /mnt/ai/Datasets/{{basepath}}/../../{{folder}}/./{{name.ext}}
            # Here, when both {{basepath}} and {{folder}} contain the same word ('Pictures') -> wrong color
            # Wrong highlighting is worse than no highlighting. So disable highlighting when there are up-references.
            if ".." in pathSplit[i1:i2]:
                return []

            # Start: Index of first char of removed parts
            # End:   Index of last char of removed parts (including slash)
            removedStart = sum(len(p)+1 for p in pathSplit[:i1])
            removedEnd   = sum(len(p)+1 for p in pathSplit[i1:i2]) + removedStart
            if i2 == len(pathSplit):
                removedEnd -= 1  # Last path component has no slash

            borderLeft  = removedStart - 1
            borderRight = removedEnd - 1

            # Iterate back to front. Break when variable lies completely before deletion: These don't need shifting.
            for i in range(len(varPositions)-1, -1, -1):
                pos = varPositions[i]
                if pos[3] <= borderLeft:
                    break

                # Shift end
                shifts[i][1] += min(pos[3], borderRight) - borderLeft

                # Shift start
                if pos[2] > borderLeft:
                    shifts[i][0] += min(pos[2], borderRight) - borderLeft

        for pos, shift in zip(varPositions, shifts):
            # Check length to account for templates with unset variables in last component
            pos[2] = min(pos[2]-shift[0], len(pathNorm))
            pos[3] = min(pos[3]-shift[1], len(pathNorm))

        return varPositions


    @override
    def _getImgProperties(self, var: str) -> str | None:
        if value := super()._getImgProperties(var):
            return value

        match var:
            case "w": return str(self.width)
            case "h": return str(self.height)
            case "region": return str(self.region)

            case "date": return datetime.now().strftime('%Y%m%d')
            case "time": return datetime.now().strftime('%H%M%S')

        return None



class ClickableTextEdit(QtWidgets.QPlainTextEdit):
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        self._pressPos = None

    @override
    def mousePressEvent(self, e) -> None:
        super().mousePressEvent(e)
        self._pressPos = e.position()

        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)

    @override
    def mouseReleaseEvent(self, e) -> None:
        super().mouseReleaseEvent(e)
        if not self._pressPos:
            return

        pos = e.position()
        dx = pos.x() - self._pressPos.x()
        dy = pos.y() - self._pressPos.y()
        dist2 = dx*dx + dy*dy
        if dist2 < 16 and e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

        self._pressPos = None



class ScaleConfig:
    def __init__(self, interpUp: str, interpDown: str, modelPath: str | None = None):
        self.interpUp   = INTERP_MODES[interpUp]
        self.interpDown = INTERP_MODES[interpDown]
        self.modelPath  = modelPath

    @property
    def useUpscaleModel(self) -> bool:
        return self.modelPath is not None

    def getInterpolationMode(self, upscale: bool) -> int:
        return self.interpUp if upscale else self.interpDown

    def toDict(self) -> dict:
        config = {
            ScaleModelSettings.KEY_BACKEND:     ScaleModelSettings.DEFAULT_BACKEND,
            ScaleModelSettings.KEY_INTERP_UP:   self.interpUp,
            ScaleModelSettings.KEY_INTERP_DOWN: self.interpDown
        }

        if self.modelPath:
            config[ScaleModelSettings.LEVELKEY_MODELPATH] = self.modelPath
        return config


class ScalePresetComboBox(QtWidgets.QComboBox):
    CONFIG_ATTR = "inferScalePresets"

    def __init__(self):
        super().__init__()
        self.reloadPresets(Config.inferSelectedPresets.get(self.CONFIG_ATTR))
        self.currentTextChanged.connect(self._onPresetChanged)
        ModelSettingsWindow.signals.presetListUpdated.connect(self._onPresetListChanged)

    def reloadPresets(self, selectedText: str | None = None):
        if selectedText is None:
            selectedText = self.currentText()

        self.clear()

        presets: dict = Config.inferScalePresets
        for name in sorted(presets.keys()):
            self.addItem(name)

        index = self.findText(selectedText)
        index = max(index, 0)
        self.setCurrentIndex(index)

    @Slot()
    def _onPresetChanged(self, presetName: str):
        Config.inferSelectedPresets[self.CONFIG_ATTR] = presetName

    @Slot()
    def _onPresetListChanged(self, attr):
        if attr == self.CONFIG_ATTR:
            with QSignalBlocker(self):
                self.reloadPresets()


    def getSelectedPreset(self) -> dict:
        # Don't store presets as item data. Updating the stored data would require another signal when presets change.
        # Instead, retrieve up-to-date values as needed.
        presetName = self.currentText()
        return Config.inferScalePresets[presetName]

    def getInterpolationMode(self, upscale: bool) -> int:
        preset = self.getSelectedPreset()
        interpName: str = ScaleModelSettings.getInterpUp(preset) if upscale else ScaleModelSettings.getInterpDown(preset)
        return INTERP_MODES[ interpName ]

    def getScaleConfig(self, scaleFactor: float) -> ScaleConfig:
        scaleFactor = round(scaleFactor, 2)

        preset = self.getSelectedPreset()
        interpUp   = ScaleModelSettings.getInterpUp(preset)
        interpDown = ScaleModelSettings.getInterpDown(preset)

        modelPath = None
        levels: list[dict] = preset.get(ScaleModelSettings.KEY_LEVELS, [])
        for level in levels:
            if scaleFactor > round(level.get(ScaleModelSettings.LEVELKEY_THRESHOLD), 2):
                modelPath = level.get(ScaleModelSettings.LEVELKEY_MODELPATH)

        return ScaleConfig(interpUp, interpDown, modelPath)


    @Slot()
    def showModelSettings(self):
        ModelSettingsWindow.openInstance(self, self.CONFIG_ATTR, self.currentText())



class ImageExportTask(QRunnable):
    class ExportTaskSignals(QObject):
        done     = Signal(str, str)
        progress = Signal(str)
        fail     = Signal(str)

        def __init__(self):
            super().__init__()


    def __init__(self, srcFile, destFile, pixmap, targetWidth: int, targetHeight: int, scaleConfig: ScaleConfig):
        super().__init__()
        self.signals        = self.ExportTaskSignals()

        self.srcFile        = srcFile
        self.destFile       = destFile

        self.img            = self.toImage(pixmap)
        self.targetWidth    = targetWidth
        self.targetHeight   = targetHeight
        self.scaleConfig    = scaleConfig

        self.borderMode     = cv.BORDER_REPLICATE


    def toImage(self, pixmap):
        return pixmap.toImage()

    def processImage(self, mat: np.ndarray) -> np.ndarray:
        return mat


    @Slot()
    def run(self):
        try:
            matSrc = qtlib.qimageToNumpy(self.img)
            if self.scaleConfig.useUpscaleModel:
                matSrc = self.inferUpscale(matSrc)

            self.signals.progress.emit("Saving image...")
            matDest = self.processImage(matSrc)

            saveImage(self.destFile, matDest)
            self.signals.done.emit(self.srcFile, self.destFile)

            del matSrc
            del matDest
        except Exception as ex:
            print(f"Export failed: {ex}")
            self.signals.fail.emit(str(ex))
        finally:
            del self.img

    def inferUpscale(self, mat: np.ndarray) -> np.ndarray:
        from infer.inference import Inference
        inferProc = Inference().proc
        inferProc.start()

        modelName = os.path.basename(self.scaleConfig.modelPath)
        modelName = os.path.splitext(modelName)[0]

        self.signals.progress.emit(f"Loading upscale model ({modelName}) ...")
        upscaleConfig = self.scaleConfig.toDict()
        inferProc.setupUpscale(upscaleConfig)
        self.signals.progress.emit(f"Upscaling with model ({modelName}) ...")

        hOrig, wOrig = mat.shape[:2]
        w, h, imgData = inferProc.upscaleImage(upscaleConfig, mat.tobytes(), wOrig, hOrig)
        channels = len(imgData) // (w*h)
        mat = np.frombuffer(imgData, dtype=np.uint8)
        mat.shape = (h, w, channels)
        return mat

    def resize(self, mat: np.ndarray) -> np.ndarray:
        srcHeight, srcWidth = mat.shape[:2]
        dsize  = (self.targetWidth, self.targetHeight)
        interp = self.scaleConfig.getInterpolationMode(self.targetWidth > srcWidth or self.targetHeight > srcHeight)
        return cv.resize(mat, dsize, interpolation=interp)

    def warpAffine(self, mat: np.ndarray, ptsSrc: list[list[float]], ptsDest: list[list[float]]) -> np.ndarray:
        srcWidth  = self.distance(ptsSrc[1], ptsSrc[0])
        srcHeight = self.distance(ptsSrc[2], ptsSrc[1])

        # https://docs.opencv.org/3.4/da/d6e/tutorial_py_geometric_transformations.html
        matrix = cv.getAffineTransform(np.float32(ptsSrc), np.float32(ptsDest))
        dsize  = (self.targetWidth, self.targetHeight)
        interp = self.scaleConfig.getInterpolationMode(self.targetWidth > srcWidth or self.targetHeight > srcHeight)
        return cv.warpAffine(src=mat, M=matrix, dsize=dsize, flags=interp, borderMode=self.borderMode)

    @staticmethod
    def distance(p0: list[float], p1: list[float]) -> float:
        dx = p0[0] - p1[0]
        dy = p0[1] - p1[1]
        return np.sqrt(dx*dx + dy*dy)
