import os
from typing import Callable
from enum import Enum, auto
from typing_extensions import override
from PySide6 import QtWidgets
from PySide6.QtCore import QSignalBlocker, Qt, Slot
from config import Config
from infer import Inference, PromptWidget
from lib import qtlib
from lib.captionfile import CaptionFile
from lib.template_parser import TemplateVariableParser, VariableHighlighter
from .batch_task import BatchTask, BatchSignalHandler, BatchUtil


class WriteMode(Enum):
    SeparateReplace         = auto()
    SeparateSkipExisting    = auto()
    SingleReplace           = auto()
    SingleAppend            = auto()
    CaptionsReplace         = auto()
    CaptionsSkipExisting    = auto()
    TagsReplace             = auto()
    TagsSkipExisting        = auto()

JSON_WRITE_MODES = (WriteMode.CaptionsReplace, WriteMode.CaptionsSkipExisting, WriteMode.TagsReplace, WriteMode.TagsSkipExisting)

WRITE_MODE_TEXT = {
    WriteMode.SeparateReplace:      "Write to .txt files and overwrite their content!",
    WriteMode.SeparateSkipExisting: "Write to .txt files if they don't exist",
    WriteMode.SingleReplace:        "Write all captions to a single .txt file and overwrite its content!",
    WriteMode.SingleAppend:         "Append all captions to a single .txt file",
    WriteMode.CaptionsReplace:      "Write to .json files [captions.{key}] and overwrite the content!",
    WriteMode.CaptionsSkipExisting: "Write to .json files [captions.{key}] if the key doesn't exist",
    WriteMode.TagsReplace:          "Write to .json files [tags.{key}] and overwrite the content!",
    WriteMode.TagsSkipExisting:     "Write to .json files [tags.{key}] if the key doesn't exist",
}


BACKUP_TYPE_CAPTION = "caption"
BACKUP_TYPE_TAGS    = "tags"


class BatchApply(QtWidgets.QWidget):
    def __init__(self, tab, logSlot, progressBar, statusBar):
        super().__init__()
        self.tab = tab
        self.log = logSlot
        self.progressBar: QtWidgets.QProgressBar = progressBar
        self.statusBar: qtlib.ColoredMessageStatusBar = statusBar

        self.writeSettings = self._buildWriteSettings()
        self.backupSettings = self._buildBackupSettings()

        self.btnStart = QtWidgets.QPushButton("Start Batch Apply")
        self.btnStart.clicked.connect(self.startStop)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._buildFormatSettings())
        layout.addWidget(self.writeSettings)
        layout.addWidget(self.backupSettings)
        layout.addWidget(self.btnStart)
        self.setLayout(layout)

        self._parser = None
        self._highlighter = VariableHighlighter()
        self._task = None
        self._taskSignalHandler = None

        self._onWriteModeChanged(0)


    def _buildFormatSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)

        row = 0
        self.promptWidget = PromptWidget("templateApplyPresets", "templateApplyDefault")
        qtlib.setTextEditHeight(self.promptWidget.txtPrompts, 10, "min")
        self.promptWidget.hideSystemPrompt()
        self.promptWidget.lblPreset.setText("Template Preset")
        self.promptWidget.lblPrompts.setText("Template:")
        self.promptWidget.txtPrompts.textChanged.connect(self._updatePreview)
        layout.addWidget(self.promptWidget, row, 0, 1, 3)
        layout.setRowStretch(row, 1)

        row += 1
        self.txtPreview = QtWidgets.QPlainTextEdit()
        self.txtPreview.setReadOnly(True)
        qtlib.setMonospace(self.txtPreview)
        qtlib.setTextEditHeight(self.txtPreview, 10, "min")
        qtlib.setShowWhitespace(self.txtPreview)
        layout.addWidget(QtWidgets.QLabel("Preview:"), row, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.txtPreview, row, 1, 1, 2)
        layout.setRowStretch(row, 1)

        row += 1
        layout.addWidget(QtWidgets.QLabel("Strip:"), row, 0)

        self.chkStripAround = QtWidgets.QCheckBox("Surrounding whitespace")
        self.chkStripAround.setChecked(True)
        self.chkStripAround.checkStateChanged.connect(self._updateParser)
        layout.addWidget(self.chkStripAround, row, 1)

        self.chkStripMulti = QtWidgets.QCheckBox("Repeating whitespace")
        self.chkStripMulti.setChecked(True)
        self.chkStripMulti.checkStateChanged.connect(self._updateParser)
        layout.addWidget(self.chkStripMulti, row, 2)


        groupBox = QtWidgets.QGroupBox("Format")
        groupBox.setLayout(layout)
        return groupBox

    def _buildWriteSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 0)
        layout.setColumnStretch(4, 0)
        layout.setColumnStretch(5, 1)
        layout.setColumnMinimumWidth(2, 20)
        layout.setColumnMinimumWidth(4, 4)

        row = 0
        layout.addWidget(QtWidgets.QLabel("Storage type:"), row, 0)

        self.cboWriteMode = QtWidgets.QComboBox()
        self.cboWriteMode.addItem("Separate .txt files (replace)", WriteMode.SeparateReplace)
        self.cboWriteMode.addItem("Separate .txt files (skip existing)", WriteMode.SeparateSkipExisting)
        self.cboWriteMode.addItem("Single .txt file (replace)", WriteMode.SingleReplace)
        self.cboWriteMode.addItem("Single .txt file (append)", WriteMode.SingleAppend)
        self.cboWriteMode.addItem(".json Captions (replace)", WriteMode.CaptionsReplace)
        self.cboWriteMode.addItem(".json Captions (skip existing)", WriteMode.CaptionsSkipExisting)
        self.cboWriteMode.addItem(".json Tags (replace)", WriteMode.TagsReplace)
        self.cboWriteMode.addItem(".json Tags (skip existing)", WriteMode.TagsSkipExisting)
        self.cboWriteMode.currentIndexChanged.connect(self._onWriteModeChanged)
        layout.addWidget(self.cboWriteMode, row, 1)

        self.btnChooseDestFile = QtWidgets.QPushButton("Choose File...")
        self.btnChooseDestFile.clicked.connect(self._chooseDestFile)
        layout.addWidget(self.btnChooseDestFile, row, 3)

        self.txtDestFilePath = QtWidgets.QLineEdit("caption-list.txt")
        qtlib.setMonospace(self.txtDestFilePath)
        layout.addWidget(self.txtDestFilePath, row, 5)

        row += 1
        self.lblDestKey = QtWidgets.QLabel("Storage key:")
        layout.addWidget(self.lblDestKey, row, 0)

        self.txtDestKey = QtWidgets.QLineEdit("tags")
        qtlib.setMonospace(self.txtDestKey)
        layout.addWidget(self.txtDestKey, row, 1)

        layout.addWidget(QtWidgets.QLabel("Post Processing:"), row, 3)

        self.chkDeleteJson = QtWidgets.QCheckBox("Delete .json files")
        self.chkDeleteJson.toggled.connect(self._updateDeleteJson)
        layout.addWidget(self.chkDeleteJson, row, 5)

        group = QtWidgets.QGroupBox("Destination")
        group.setLayout(layout)
        return group

    def _buildBackupSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 1)

        layout.addWidget(QtWidgets.QLabel("Storage key:"), 0, 0, Qt.AlignmentFlag.AlignTop)

        self.cboBackupType = QtWidgets.QComboBox()
        self.cboBackupType.addItem(BACKUP_TYPE_CAPTION)
        self.cboBackupType.addItem(BACKUP_TYPE_TAGS)
        qtlib.setMonospace(self.cboBackupType)
        layout.addWidget(self.cboBackupType, 0, 1)

        self.txtBackupKey = QtWidgets.QLineEdit("backup")
        qtlib.setMonospace(self.txtBackupKey)
        layout.addWidget(self.txtBackupKey, 0, 2)

        groupBox = QtWidgets.QGroupBox("Backup current value (txt/json → json)")
        groupBox.setCheckable(True)
        groupBox.setChecked(False)
        groupBox.toggled.connect(self._updateDeleteJson)
        groupBox.setLayout(layout)
        return groupBox


    def onFileChanged(self, currentFile):
        self._parser = TemplateVariableParser(currentFile)
        self._updateParser()


    @Slot()
    def _onWriteModeChanged(self, index: int):
        mode = self.cboWriteMode.itemData(index)

        singleTxt = mode in (WriteMode.SingleAppend, WriteMode.SingleReplace)
        for widget in (self.btnChooseDestFile, self.txtDestFilePath):
            widget.setEnabled(singleTxt)

        jsonKey = mode in JSON_WRITE_MODES
        for widget in (self.lblDestKey, self.txtDestKey):
            widget.setEnabled(jsonKey)

        backupPossible = not singleTxt
        self.backupSettings.setEnabled(backupPossible)
        if not backupPossible:
            self.backupSettings.setChecked(False)
        
        self._updateDeleteJson()

    @Slot()
    def _chooseDestFile(self):
        path = self.txtDestFilePath.text()
        filter = "Text Files (*.txt)"

        path, filter = QtWidgets.QFileDialog.getSaveFileName(self, "Choose target file", path, filter)
        if path:
            self.txtDestFilePath.setText(path)

    @Slot()
    def _updateDeleteJson(self):
        writeMode = self.cboWriteMode.currentData()
        deletePossible = writeMode not in JSON_WRITE_MODES
        deletePossible &= not self.backupSettings.isChecked()

        deleteChecked = deletePossible and self.chkDeleteJson.isChecked()
        self.chkDeleteJson.setChecked(deleteChecked)
        self.chkDeleteJson.setEnabled(deletePossible)

        style = f"color: {qtlib.COLOR_RED}" if deleteChecked else None
        self.chkDeleteJson.setStyleSheet(style)


    def _updateParser(self):
        if self._parser:
            self._parser.stripAround = self.chkStripAround.isChecked()
            self._parser.stripMultiWhitespace = self.chkStripMulti.isChecked()
            self._updatePreview()


    @Slot()
    def _updatePreview(self):
        text = self.promptWidget.prompts
        preview, varPositions = self._parser.parseWithPositions(text)
        self.txtPreview.setPlainText(preview)

        with QSignalBlocker(self.promptWidget.txtPrompts):
            self._highlighter.highlight(self.promptWidget.txtPrompts, self.txtPreview, varPositions)


    def _confirmStart(self) -> bool:
        ops = []

        if self.backupSettings.isChecked():
            backupKey = f"{self.cboBackupType.currentText()}.{self.txtBackupKey.text().strip()}"
            ops.append(f"Backup the current value from the destination into the '{backupKey}' key")

        writeMode = self.cboWriteMode.currentData()
        writeModeText = WRITE_MODE_TEXT.get(writeMode, "").format(key=self.txtDestKey.text())
        if writeMode in (WriteMode.SeparateReplace, WriteMode.SingleReplace, WriteMode.CaptionsReplace, WriteMode.TagsReplace):
            writeModeText = qtlib.htmlRed(writeModeText)
        ops.append(writeModeText)

        if self.chkDeleteJson.isChecked():
            ops.append(qtlib.htmlRed('Delete all .json files!'))

        return BatchUtil.confirmStart("Apply", self.tab.filelist.getNumFiles(), ops, self)


    @Slot()
    def startStop(self):
        if self._task:
            if BatchUtil.confirmAbort(self):
                self._task.abort()
            return

        if not self._confirmStart():
            return

        self.btnStart.setText("Abort")

        template = self.promptWidget.prompts
        self._task = BatchApplyTask(self.log, self.tab.filelist, template)

        if self.backupSettings.isChecked():
            self._task.backupType = self.cboBackupType.currentText()
            self._task.backupKey  = self.txtBackupKey.text().strip()

        self._task.stripAround = self.chkStripAround.isChecked()
        self._task.stripMulti  = self.chkStripMulti.isChecked()
        self._task.writeMode   = self.cboWriteMode.currentData()
        self._task.destPath    = self.txtDestFilePath.text()
        self._task.destKey     = self.txtDestKey.text()
        self._task.deleteJson  = self.chkDeleteJson.isChecked()

        self._taskSignalHandler = BatchSignalHandler(self.statusBar, self.progressBar, self._task)
        self._taskSignalHandler.finished.connect(self.taskDone)
        Inference().queueTask(self._task)

    def taskDone(self):
        self.btnStart.setText("Start Batch Apply")
        self._task = None
        self._taskSignalHandler = None



class BatchApplyTask(BatchTask):
    def __init__(self, log, filelist, template: str):
        super().__init__("apply", log, filelist)
        self.template    = template
        self.stripAround = True
        self.stripMulti  = True

        self.backupType  = "" # Empty if backup disabled
        self.backupKey   = "" # Empty if backup disabled

        self.writeMode   = WriteMode.SeparateSkipExisting
        self.destPath    = "" # For writing to single .txt file
        self.destKey     = "" # For writing to .json
        self.dest: CaptionDest = None

        self.deleteJson  = False


    def runPrepare(self):
        if self.backupType and not self.backupKey:
            raise ValueError("Backup key is empty")
        if self.deleteJson and self.backupType:
            raise ValueError("Cannot delete json files when backup is enabled")
        if self.deleteJson and (self.writeMode in JSON_WRITE_MODES):
            raise ValueError("Cannot delete json files when writing to json files")

        self.parser = TemplateVariableParser(None)
        self.parser.stripAround = self.stripAround
        self.parser.stripMultiWhitespace = self.stripMulti

        match self.writeMode:
            case WriteMode.SeparateReplace | WriteMode.SeparateSkipExisting:
                self.dest = TxtFileDest(self.writeMode)
            case WriteMode.SingleReplace | WriteMode.SingleAppend:
                self.dest = SingleTxtFileDest(self.writeMode, self.destPath)
            case _:
                self.dest = JsonDest(self.writeMode, self.destKey)
    
    def runCleanup(self):
        self.dest.cleanup()


    def runProcessFile(self, imgFile: str) -> str | None:
        imgPathNoExt = os.path.splitext(imgFile)[0]

        captionFile = CaptionFile(imgPathNoExt)
        if captionFile.jsonExists() and not captionFile.loadFromJson():
            self.log(f"WARNING: Couldn't read captions from {captionFile.jsonPath}")
            return None

        saveJson = False
        if self.backupType:
            saveJson = self.backup(imgPathNoExt, captionFile)

        writtenFile, jsonModified = self.dest.write(imgPathNoExt, captionFile, self.parseCaption)
        saveJson |= jsonModified

        if self.deleteJson:
            self.deleteJsonFile(captionFile.jsonPath)
        
        if saveJson:
            captionFile.saveToJson()
        return writtenFile

    def parseCaption(self, imgPathNoExt: str, captionFile: CaptionFile) -> str:
        self.parser.setup(imgPathNoExt, captionFile)
        caption = self.parser.parse(self.template)

        if self.parser.missingVars:
            self.log(f"WARNING: {captionFile.jsonPath} is missing values for variables: {', '.join(self.parser.missingVars)}")
        
        return caption

    def backup(self, imgPathNoExt: str, captionFile: CaptionFile) -> bool:
        oldCaption = self.dest.read(imgPathNoExt, captionFile)
        if not oldCaption:
            return False

        if self.backupType == BACKUP_TYPE_CAPTION:
            captionFile.addCaption(self.backupKey, oldCaption)
        else:
            captionFile.addTags(self.backupKey, oldCaption)
        return True

    def deleteJsonFile(self, path: str) -> None:
        if path.endswith(".json") and os.path.isfile(path):
            os.remove(path)
            self.log(f"Deleted {path}")
        else:
            self.log(f"WARNING: Could not delete {path}")



class CaptionDest:
    def read(self, imgPathNoExt: str, captionFile: CaptionFile) -> str | None:
        return None

    def write(self, imgPathNoExt: str, captionFile: CaptionFile, captionFunc: Callable[[str, CaptionFile], str]) -> tuple[str|None, bool]:
        'Returns the written filename and a boolean indicating if json was modified.'
        raise NotImplementedError()

    def cleanup(self):
        pass



class TxtFileDest(CaptionDest):
    def __init__(self, writeMode: WriteMode):
        if writeMode not in (WriteMode.SeparateReplace, WriteMode.SeparateSkipExisting):
            raise ValueError(f"Invalid WriteMode: {writeMode}")
        self.writeMode = writeMode

    @override
    def read(self, imgPathNoExt: str, captionFile: CaptionFile) -> str | None:
        txtPath = imgPathNoExt + ".txt"
        if os.path.exists(txtPath):
            with open(txtPath, 'r') as file:
                return file.read()
        return None

    @override
    def write(self, imgPathNoExt: str, captionFile: CaptionFile, captionFunc: Callable[[str, CaptionFile], str]) -> tuple[str|None, bool]:
        txtPath = imgPathNoExt + ".txt"
        if (self.writeMode != WriteMode.SeparateReplace) and os.path.exists(txtPath):
            return None, False

        caption = captionFunc(imgPathNoExt, captionFile)
        with open(txtPath, 'w') as file:
            file.write(caption)
        return txtPath, False



class SingleTxtFileDest(CaptionDest):
    def __init__(self, writeMode: WriteMode, txtPath: str):
        if not txtPath:
            raise ValueError("Target path is empty")

        match writeMode:
            case WriteMode.SingleReplace: openMode = 'w'
            case WriteMode.SingleAppend:  openMode = 'a'
            case _: raise ValueError(f"Invalid WriteMode: {writeMode}")

        self.txtPath = txtPath
        self.txtFile = open(txtPath, openMode)

    @override
    def write(self, imgPathNoExt: str, captionFile: CaptionFile, captionFunc: Callable[[str, CaptionFile], str]) -> tuple[str|None, bool]:
        caption = captionFunc(imgPathNoExt, captionFile)
        self.txtFile.write(caption)
        return self.txtPath, False

    @override
    def cleanup(self):
        self.txtFile.flush()
        self.txtFile.close()



class JsonDest(CaptionDest):
    def __init__(self, writeMode: WriteMode, key: str):
        if not key:
            raise ValueError("Target key is empty")

        match writeMode:
            case WriteMode.CaptionsReplace | WriteMode.CaptionsSkipExisting:
                self.captionGetter = CaptionFile.getCaption
                self.captionSetter = CaptionFile.addCaption
            case WriteMode.TagsReplace | WriteMode.TagsSkipExisting:
                self.captionGetter = CaptionFile.getTags
                self.captionSetter = CaptionFile.addTags
            case _:
                raise ValueError(f"Invalid WriteMode: {writeMode}")

        self.key = key
        self.skipExisting: bool = writeMode in (WriteMode.CaptionsSkipExisting, WriteMode.TagsSkipExisting)

    @override
    def read(self, imgPathNoExt: str, captionFile: CaptionFile) -> str | None:
        return self.captionGetter(captionFile, self.key)

    @override
    def write(self, imgPathNoExt: str, captionFile: CaptionFile, captionFunc: Callable[[str, CaptionFile], str]) -> tuple[str|None, bool]:
        if self.skipExisting and self.captionGetter(captionFile, self.key):
            return None, False

        caption = captionFunc(imgPathNoExt, captionFile)
        self.captionSetter(captionFile, self.key, caption)
        return captionFile.jsonPath, True
