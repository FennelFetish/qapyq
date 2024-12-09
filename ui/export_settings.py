import os, superqt
from typing_extensions import override
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, Signal, QSignalBlocker
import cv2 as cv
import numpy as np
from PIL import Image
from datetime import datetime
from lib import qtlib, template_parser
from config import Config


INTERP_MODES = {
    "Nearest": cv.INTER_NEAREST,
    "Linear":  cv.INTER_LINEAR,
    "Cubic":   cv.INTER_CUBIC,
    "Area":    cv.INTER_AREA,
    "Lanczos": cv.INTER_LANCZOS4
}


class Format:
    def __init__(self, saveParams: dict, conversion: dict = {}):
        self.saveParams = saveParams
        self.conversion = conversion

# https://pillow.readthedocs.io/en/stable/handbook/concepts.html#concept-modes
FORMATS = {
    "PNG":  Format({"optimize": True, "compress_level": 9}),
    "JPG":  Format({"optimize": True, "quality": 100, "subsampling": 0}, {"RGBA": "RGB", "P": "RGB"}),
    "WEBP": Format({"lossless": True, "quality": 100, "exact": True})
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

def saveImage(path, mat: np.ndarray, logger=print):
    _, ext = os.path.splitext(path)
    format = getFormat(ext)

    mat[..., :3] = mat[..., 2::-1] # Convert BGR(A) -> RGB(A)
    img = Image.fromarray(mat.squeeze()) # No copy!

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

    def __init__(self, configKey: str, filelist, showInterpolation=True, formats: list[str]=[]):
        super().__init__()
        self.configKey = configKey
        self.filelist = filelist
        self.showInterpolation = showInterpolation
        self._defaultPath = Config.pathExport

        config = Config.exportPresets.get(configKey, {})
        self.pathTemplate   = config.get("path_template", "{{name}}_{{date}}_{{time}}_{{w}}x{{h}}")
        self.overwriteFiles = config.get("overwrite", False)
        self._extension = "png"

        self.parser = ExportVariableParser()

        self._build(formats)
        self._onSaveModeChanged(self.cboSaveMode.currentIndex())
        
    def _build(self, formats: list[str]):
        collapsible = superqt.QCollapsible("Export Settings")
        collapsible.layout().setContentsMargins(2, 2, 2, 0)
        collapsible.setFrameStyle(QtWidgets.QFrame.Shape.NoFrame)
        collapsible.setLineWidth(0)
        collapsible.addWidget(self._buildParams(formats))
        collapsible.addWidget(self._buildPathSettings())

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

    def _buildParams(self, formats: list[str]):
        self.cboInterpUp = QtWidgets.QComboBox()
        self.cboInterpUp.addItems(INTERP_MODES.keys())
        self.cboInterpUp.setCurrentIndex(4) # Default: Lanczos

        self.cboInterpDown = QtWidgets.QComboBox()
        self.cboInterpDown.addItems(INTERP_MODES.keys())
        self.cboInterpDown.setCurrentIndex(3) # Default: Area

        self.cboFormat = QtWidgets.QComboBox()
        self.cboFormat.addItems(formats if formats else FORMATS.keys())
        self.cboFormat.currentTextChanged.connect(self._onExtensionChanged)

        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        if self.showInterpolation:
            layout.addRow("Interp 🠕:", self.cboInterpUp)
            layout.addRow("Interp 🠗:", self.cboInterpDown)
        layout.addRow("Format:", self.cboFormat)

        group = QtWidgets.QGroupBox("Parameter")
        group.setLayout(layout)
        return group

    def _buildPathSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        self.cboSaveMode = QtWidgets.QComboBox()
        self.cboSaveMode.addItem("Template", self.MODE_AUTO)
        self.cboSaveMode.addItem("Dialog", self.MODE_MANUAL)
        self.cboSaveMode.currentIndexChanged.connect(self._onSaveModeChanged)
        layout.addWidget(QtWidgets.QLabel("Path:"), 0, 0)
        layout.addWidget(self.cboSaveMode, 0, 1)
        
        self.btnOpenSettings = QtWidgets.QPushButton("Edit Path...")
        self.btnOpenSettings.clicked.connect(self.openExportSettings)
        layout.addWidget(self.btnOpenSettings, 1, 0, 1, 2)

        group = QtWidgets.QGroupBox("Destination")
        group.setLayout(layout)
        return group

    @Slot()
    def _onExtensionChanged(self, ext: str):
        self.extension = ext # property assignment with sanitization

    @Slot()
    def _onSaveModeChanged(self, index):
        enabled = (self.cboSaveMode.itemData(index) == self.MODE_AUTO)
        self.btnOpenSettings.setEnabled(enabled)
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
            stylesheet = "color: #ff1616"
        self.txtPathSample.setStyleSheet(stylesheet)

        examplePath = "/\n\n".join(os.path.split(examplePath))
        self.txtPathSample.setPlainText(examplePath)


    @property
    def extension(self) -> str:
        return self._extension

    @extension.setter
    def extension(self, ext: str) -> None:
        self._extension = ext.lstrip('.').lower()
        self.updateSample()


    def getInterpolationMode(self, upscale):
        cbo = self.cboInterpUp if upscale else self.cboInterpDown
        return INTERP_MODES[ cbo.currentText() ]


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

        fileFilter = f"All Files (*.*)"
        path, selectedFilter = QtWidgets.QFileDialog.getSaveFileName(self, "Save Image", path, fileFilter)
        if not path:
            return ""
        
        _, ext = os.path.splitext(path)
        if not ext:
            # Do not simply append an extension: That would bypass overwrite confirmation.
            QtWidgets.QMessageBox.warning(self, "Invalid Path", "The extension is missing from the filename.")
            return ""

        self._defaultPath = os.path.dirname(path)
        return path
    
    def getAutoExportPath(self, imgFile, forReading=False) -> str:
        self.parser.setup(imgFile)
        overwriteFiles = self.overwriteFiles or forReading
        return self.parser.parsePath(self.pathTemplate, self._extension, overwriteFiles)



class PathSettings(QtWidgets.QWidget):
    INFO = """Available variables in path template:
    {{path}}      Image path
    {{path.ext}}  Image path with extension
    {{name}}      Image filename
    {{name.ext}}  Image filename with extension
    {{folder}}    Folder of image
    {{folder-1}}  Parent folder 1 (or 2, 3...)
    {{w}}         Width
    {{h}}         Height
    {{region}}    Crop region number
    {{date}}      Date yyyymmdd
    {{time}}      Time hhmmss

The file extension is always added.
An increasing counter is appended when a file exists and overwriting is disabled.

Examples:
    {{name}}_{{w}}x{{h}}
    {{path}}-masklabel
    /home/user/Pictures/{{folder}}/{{date}}_{{time}}_{{w}}x{{h}}"""


    def __init__(self, parser, showInfo=True) -> None:
        super().__init__()
        self._extension = "ext"

        self.parser: ExportVariableParser = parser
        self.highlighter = template_parser.VariableHighlighter()

        self._build(showInfo)
        self.updatePreview()

    def _build(self, showInfo: bool):
        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
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
        style = "color: #FF1616" if state else None
        self.chkOverwrite.setStyleSheet(style)

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
            self.txtPreview.setPlainText(text + f".{self._extension}")
            self.highlighter.highlight(self.txtPathTemplate, self.txtPreview, varPositions, not self.isEnabled())

    def _choosePath(self):
        path = self.txtPathTemplate.toPlainText()
        path = path.replace("{{path}}", "{{name}}")

        # Keep dynamic path elements with variables
        head, tail = os.path.split(path)
        while head:
            head, tempTail = os.path.split(head)
            if "{{" not in tempTail:
                break
            tail = os.path.join(tempTail, tail)

        opts = QtWidgets.QFileDialog.Option.ShowDirsOnly
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose save folder", head, opts)
        if path:
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

        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowTitle("Setup Export Path")
        self.resize(800, 500)

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

    def parsePath(self, pathTemplate: str, extension: str, overwriteFiles: bool) -> str:
        path = self.parse(pathTemplate)
        path = path.translate(INVALID_CHARS)
        path = os.path.normpath(os.path.join(Config.pathExport, path))

        if overwriteFiles:
            path = f"{path}.{extension}"
        else:
            head = path
            path = f"{head}.{extension}"
            counter = 1
            while os.path.exists(path):
                path = f"{head}_{counter:03}.{extension}"
                counter += 1

        return path
    
    def parsePathWithPositions(self, pathTemplate: str) -> tuple[str, list[list[int]]]:
        firstVarIdx = pathTemplate.find("{{")
        if firstVarIdx < 0:
            path, varPositions = self.parseWithPositions(pathTemplate)
        else:
            # Normalize part of path before the first variable
            pathHead = pathTemplate[:firstVarIdx] + "@" # The added character prevents removal of trailing slashes.
            pathHead = os.path.normpath(os.path.join(Config.pathExport, pathHead))
            pathHead = pathHead[:-1] # Cut '@'
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

        # Highlighting will be wrong if path elements were removed in normpath().
        if len(pathNorm) != len(path):
            return pathNorm, []
        return pathNorm, varPositions

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
