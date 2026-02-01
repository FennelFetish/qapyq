import os
from typing import Callable
from enum import Enum, auto
from typing_extensions import override
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
from config import Config
from infer.prompt import PromptWidget
from lib import colorlib, qtlib
from lib.captionfile import CaptionFile, FileTypeSelector
from lib.template_parser import TemplateVariableParser
from ui.tab import ImgTab
from .batch_task import BatchTask, BatchTaskHandler
from .batch_log import BatchLog


class WriteMode(Enum):
    SeparateReplace         = auto()
    SeparateSkipExisting    = auto()
    SingleReplace           = auto()
    SingleAppend            = auto()
    CaptionsReplace         = auto()
    CaptionsSkipExisting    = auto()
    TagsReplace             = auto()
    TagsSkipExisting        = auto()


WRITE_MODE_TYPE = {
    WriteMode.SeparateReplace:      FileTypeSelector.TYPE_TXT,
    WriteMode.SeparateSkipExisting: FileTypeSelector.TYPE_TXT,
    WriteMode.SingleReplace:        FileTypeSelector.TYPE_TXT,
    WriteMode.SingleAppend:         FileTypeSelector.TYPE_TXT,
    WriteMode.CaptionsReplace:      FileTypeSelector.TYPE_CAPTIONS,
    WriteMode.CaptionsSkipExisting: FileTypeSelector.TYPE_CAPTIONS,
    WriteMode.TagsReplace:          FileTypeSelector.TYPE_TAGS,
    WriteMode.TagsSkipExisting:     FileTypeSelector.TYPE_TAGS,
}

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



class BatchApply(QtWidgets.QWidget):
    def __init__(self, tab: ImgTab, logWidget: BatchLog, bars):
        super().__init__()
        self.tab = tab
        self.logWidget = logWidget
        self.taskHandler = BatchTaskHandler("Apply", bars, tab.filelist, self.getConfirmOps, self.createTask)

        self.writeSettings = self._buildWriteSettings()
        self.backupSettings = self._buildBackupSettings()

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._buildFormatSettings())
        layout.addWidget(self.writeSettings)
        layout.addWidget(self.backupSettings)
        layout.addLayout(self.taskHandler.startButtonLayout)
        self.setLayout(layout)

        self._onWriteModeChanged(0)


    def _buildFormatSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(2, 1)

        row = 0
        self.promptWidget = PromptWidget("templateApplyPresets", "templateApplyDefault", self.tab.templateAutoCompleteSources, showSystemPrompt=False)
        qtlib.setTextEditHeight(self.promptWidget.txtPrompts, 5, "min")
        qtlib.setTextEditHeight(self.promptWidget.txtPreview, 5, "min")
        self.promptWidget.lblPreset.setText("Template Preset:")
        self.promptWidget.lblPrompts.setText("Template:")
        self.promptWidget.lblPreview.setText("Preview:")
        self.promptWidget.connectDefaultPreviewUpdate(False)
        self.promptWidget.refreshPreviewClicked.connect(self.refreshPreview)
        layout.addWidget(self.promptWidget, row, 0, 1, 3)
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
        self.cboWriteMode.addItem(".json Caption (replace)", WriteMode.CaptionsReplace)
        self.cboWriteMode.addItem(".json Caption (skip existing)", WriteMode.CaptionsSkipExisting)
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

        self.destSelector = FileTypeSelector()
        self.destSelector.setFixedType(FileTypeSelector.TYPE_TXT)
        layout.addLayout(self.destSelector, row, 1)

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
        layout.setColumnStretch(3, 1)
        layout.setColumnMinimumWidth(2, 4)

        layout.addWidget(QtWidgets.QLabel("Storage key:"), 0, 0, Qt.AlignmentFlag.AlignTop)

        self.backupDestSelector = FileTypeSelector(showTxtType=False, defaultValue="backup")
        self.backupDestSelector.type = FileTypeSelector.TYPE_CAPTIONS
        layout.addLayout(self.backupDestSelector, 0, 1)

        self.chkOverwriteBackup = QtWidgets.QCheckBox("Overwrite backup")
        self.chkOverwriteBackup.toggled.connect(self._updateOverwriteBackup)
        layout.addWidget(self.chkOverwriteBackup, 0, 3)

        groupBox = QtWidgets.QGroupBox("Backup old value (txt/json → json)")
        groupBox.setCheckable(True)
        groupBox.setChecked(False)
        groupBox.toggled.connect(self._updateDeleteJson)
        groupBox.toggled.connect(self._updateOverwriteBackup)
        groupBox.setLayout(layout)
        return groupBox


    def onFileChanged(self, currentFile):
        self.promptWidget.parser.setup(currentFile)
        self._updateParser()

    @Slot()
    def refreshPreview(self):
        self.onFileChanged(self.tab.filelist.getCurrentFile())


    @Slot()
    def _onWriteModeChanged(self, index: int):
        mode = self.cboWriteMode.itemData(index)

        singleTxt = mode in (WriteMode.SingleAppend, WriteMode.SingleReplace)
        for widget in (self.btnChooseDestFile, self.txtDestFilePath):
            widget.setEnabled(singleTxt)

        modeType = WRITE_MODE_TYPE[mode]
        self.destSelector.setFixedType(modeType)
        for widget in (self.lblDestKey, self.destSelector):
            widget.setEnabled(modeType != FileTypeSelector.TYPE_TXT)

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
            path = os.path.abspath(path)
            self.txtDestFilePath.setText(path)

    @Slot()
    def _updateDeleteJson(self):
        writeMode = self.cboWriteMode.currentData()
        deletePossible = WRITE_MODE_TYPE[writeMode] == FileTypeSelector.TYPE_TXT
        deletePossible &= not self.backupSettings.isChecked()

        deleteChecked = deletePossible and self.chkDeleteJson.isChecked()
        self.chkDeleteJson.setChecked(deleteChecked)
        self.chkDeleteJson.setEnabled(deletePossible)

        style = f"color: {colorlib.RED}" if deleteChecked else None
        self.chkDeleteJson.setStyleSheet(style)

    @Slot()
    def _updateOverwriteBackup(self):
        red = self.backupSettings.isChecked() and self.chkOverwriteBackup.isChecked()
        style = f"color: {colorlib.RED}" if red else None
        self.chkOverwriteBackup.setStyleSheet(style)

    @Slot()
    def _updateParser(self):
        self.promptWidget.parser.stripAround = self.chkStripAround.isChecked()
        self.promptWidget.parser.stripMultiWhitespace = self.chkStripMulti.isChecked()
        self.promptWidget.updatePreview(False)


    def getConfirmOps(self) -> list[str]:
        ops = []

        if self.backupSettings.isChecked():
            backupKey = f"{self.backupDestSelector.type}.{self.backupDestSelector.name.strip()}"
            ops.append("Read the old content from the destination")

            if self.chkOverwriteBackup.isChecked():
                ops.append(colorlib.htmlRed(f"Write the old content to .json files [{backupKey}] and overwrite the content!"))
            else:
                ops.append(f"Write the old content to .json files [{backupKey}] and append an increasing counter if the key already exists")

        writeMode = self.cboWriteMode.currentData()
        writeModeText = WRITE_MODE_TEXT.get(writeMode, "").format(key=self.destSelector.name.strip())
        if writeMode in (WriteMode.SeparateReplace, WriteMode.SingleReplace, WriteMode.CaptionsReplace, WriteMode.TagsReplace):
            writeModeText = colorlib.htmlRed(writeModeText)
        ops.append(writeModeText)

        if self.chkDeleteJson.isChecked():
            ops.append(colorlib.htmlRed('Delete all .json files!'))

        return ops


    def createTask(self, files: list[str]) -> BatchTask:
        log = self.logWidget.addEntry("Apply", BatchLog.GROUP_CAPTION)
        template = self.promptWidget.prompts
        task = BatchApplyTask(log, files, template)

        if self.backupSettings.isChecked():
            task.backupType = self.backupDestSelector.type
            task.backupKey  = self.backupDestSelector.name.strip()
            task.overwriteBackup = self.chkOverwriteBackup.isChecked()

        task.stripAround = self.chkStripAround.isChecked()
        task.stripMulti  = self.chkStripMulti.isChecked()
        task.writeMode   = self.cboWriteMode.currentData()
        task.destPath    = self.txtDestFilePath.text()
        task.destKey     = self.destSelector.name.strip()
        task.deleteJson  = self.chkDeleteJson.isChecked()
        return task



class BatchApplyTask(BatchTask):
    def __init__(self, log, files, template: str):
        super().__init__("apply", log, files)
        self.template    = template
        self.stripAround = True
        self.stripMulti  = True

        self.backupType  = "" # Empty if backup disabled
        self.backupKey   = "" # Empty if backup disabled
        self.overwriteBackup = False

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
        if self.deleteJson and (WRITE_MODE_TYPE[self.writeMode] != FileTypeSelector.TYPE_TXT):
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
        captionFile = CaptionFile(imgFile)
        if captionFile.jsonExists() and not captionFile.loadFromJson():
            self.log(f"WARNING: Couldn't read captions from {captionFile.jsonPath}")
            return None

        imgPathNoExt = os.path.splitext(imgFile)[0]

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

        if self.backupType == FileTypeSelector.TYPE_CAPTIONS:
            backupKey = self.getBackupKey(captionFile, CaptionFile.getCaption)
            captionFile.addCaption(backupKey, oldCaption)
        elif self.backupType == FileTypeSelector.TYPE_TAGS:
            backupKey = self.getBackupKey(captionFile, CaptionFile.getTags)
            captionFile.addTags(backupKey, oldCaption)
        return True

    def getBackupKey(self, captionFile: CaptionFile, getter: Callable) -> str:
        if self.overwriteBackup:
            return self.backupKey

        key = self.backupKey
        counter = 2
        while getter(captionFile, key):
            key = f"{self.backupKey}_{counter}"
            counter += 1
        return key

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
