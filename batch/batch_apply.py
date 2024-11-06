import os
from enum import Enum
from PySide6 import QtWidgets
from PySide6.QtCore import QSignalBlocker, Qt, Slot
from config import Config
from infer import Inference
from lib import qtlib
from lib.captionfile import CaptionFile
from lib.template_parser import TemplateVariableParser, VariableHighlighter
from .batch_task import BatchTask


class WriteMode(Enum):
    SeparateReplace = 0
    SeparateSkipExisting = 1
    SingleReplace = 2
    SingleAppend = 3


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

        self._onWriteModeChanged(0)


    def _buildFormatSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)

        row = 0
        self.txtTemplate = QtWidgets.QPlainTextEdit()
        self.txtTemplate.setPlainText(Config.batchTemplate)
        qtlib.setMonospace(self.txtTemplate)
        qtlib.setTextEditHeight(self.txtTemplate, 10, "min")
        qtlib.setShowWhitespace(self.txtTemplate)
        self.txtTemplate.textChanged.connect(self._updatePreview)
        layout.addWidget(QtWidgets.QLabel("Template:"), row, 0, Qt.AlignTop)
        layout.addWidget(self.txtTemplate, row, 1, 1, 2)
        layout.setRowStretch(0, 1)

        row += 1
        self.txtPreview = QtWidgets.QPlainTextEdit()
        self.txtPreview.setReadOnly(True)
        qtlib.setMonospace(self.txtPreview)
        qtlib.setTextEditHeight(self.txtPreview, 10, "min")
        qtlib.setShowWhitespace(self.txtPreview)
        layout.addWidget(QtWidgets.QLabel("Preview:"), row, 0, Qt.AlignTop)
        layout.addWidget(self.txtPreview, row, 1, 1, 2)
        layout.setRowStretch(1, 3)

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
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 0)
        layout.setColumnStretch(4, 1)
        layout.setColumnMinimumWidth(2, 20)

        row = 0
        layout.addWidget(QtWidgets.QLabel("Destination:"), row, 0)

        self.cboWriteMode = QtWidgets.QComboBox()
        self.cboWriteMode.addItem("Separate .txt files (replace)", WriteMode.SeparateReplace)
        self.cboWriteMode.addItem("Separate .txt files (skip existing)", WriteMode.SeparateSkipExisting)
        self.cboWriteMode.addItem("Single .txt file (replace)", WriteMode.SingleReplace)
        self.cboWriteMode.addItem("Single .txt file (append)", WriteMode.SingleAppend)
        self.cboWriteMode.currentIndexChanged.connect(self._onWriteModeChanged)
        layout.addWidget(self.cboWriteMode, row, 1)

        self.btnChooseDestFile = QtWidgets.QPushButton("Choose File...")
        self.btnChooseDestFile.clicked.connect(self._chooseDestFile)
        layout.addWidget(self.btnChooseDestFile, row, 3)

        self.txtDestFilePath = QtWidgets.QLineEdit("caption-list.txt")
        qtlib.setMonospace(self.txtDestFilePath)
        layout.addWidget(self.txtDestFilePath, row, 4)

        row += 1
        layout.addWidget(QtWidgets.QLabel("Post Processing:"), row, 0)

        self.chkDeleteJson = QtWidgets.QCheckBox("Delete .json files")
        self.chkDeleteJson.toggled.connect(self._onDeleteJsonToggled)
        layout.addWidget(self.chkDeleteJson, row, 1)


        groupBox = QtWidgets.QGroupBox("Write to text file(s)")
        groupBox.setLayout(layout)
        return groupBox

    def _buildBackupSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)

        self.txtBackupName = QtWidgets.QLineEdit("backup")
        qtlib.setMonospace(self.txtBackupName)
        layout.addWidget(QtWidgets.QLabel("Storage key:"), 0, 0)
        layout.addWidget(self.txtBackupName, 0, 1)

        groupBox = QtWidgets.QGroupBox("Backup (txt → json)")
        groupBox.setCheckable(True)
        groupBox.setChecked(False)
        groupBox.toggled.connect(self._onBackupToggled)
        groupBox.setLayout(layout)
        return groupBox


    def onFileChanged(self, currentFile):
        self._parser = TemplateVariableParser(currentFile)
        self._updateParser()


    @Slot()
    def _onWriteModeChanged(self, index: int):
        mode = self.cboWriteMode.itemData(index)
        single = mode in (WriteMode.SingleAppend, WriteMode.SingleReplace)

        for widget in (self.btnChooseDestFile, self.txtDestFilePath):
            widget.setEnabled(single)
        
        self.backupSettings.setEnabled(not single)
        if single:
            self.backupSettings.setChecked(False)
    
    @Slot()
    def _chooseDestFile(self):
        path = self.txtDestFilePath.text()
        filter = "Text Files (*.txt)"

        path, filter = QtWidgets.QFileDialog.getSaveFileName(self, "Choose target file", path, filter)
        if path:
            self.txtDestFilePath.setText(path)

    @Slot()
    def _onDeleteJsonToggled(self, state: bool):
        style = "color: #FF0000" if state else None
        self.chkDeleteJson.setStyleSheet(style)

    @Slot()
    def _onBackupToggled(self, state: bool):
        self.chkDeleteJson.setChecked(False)
        self.chkDeleteJson.setEnabled(not state)


    def _updateParser(self):
        if self._parser:
            self._parser.stripAround = self.chkStripAround.isChecked()
            self._parser.stripMultiWhitespace = self.chkStripMulti.isChecked()
            self._updatePreview()


    @Slot()
    def _updatePreview(self):
        text = self.txtTemplate.toPlainText()
        preview, varPositions = self._parser.parseWithPositions(text)
        self.txtPreview.setPlainText(preview)

        with QSignalBlocker(self.txtTemplate):
            self._highlighter.highlight(self.txtTemplate, self.txtPreview, varPositions)


    @Slot()
    def startStop(self):
        if self._task:
            self._task.abort()
        else:
            self.btnStart.setText("Abort")

            template = self.txtTemplate.toPlainText()
            backupName = self.txtBackupName.text().strip() if self.backupSettings.isChecked() else None
            self._task = BatchApplyTask(self.log, self.tab.filelist, template, backupName)
            self._task.stripAround = self.chkStripAround.isChecked()
            self._task.stripMulti  = self.chkStripMulti.isChecked()
            self._task.writeMode   = self.cboWriteMode.currentData()
            self._task.destPath    = self.txtDestFilePath.text()
            self._task.deleteJson  = self.chkDeleteJson.isChecked()

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
    def onProgress(self, numDone, numTotal, textFile):
        self.progressBar.setRange(0, numTotal)
        self.progressBar.setValue(numDone)

        if textFile:
            self.statusBar.showMessage("Wrote " + textFile)

    @Slot()
    def onProgressMessage(self, message):
        self.statusBar.showMessage(message)

    def taskDone(self):
        self.btnStart.setText("Start Batch Apply")
        self.progressBar.setRange(0, 1)
        self.progressBar.reset()
        self._task = None



class BatchApplyTask(BatchTask):
    def __init__(self, log, filelist, template: str, backupName: str | None):
        super().__init__("apply", log, filelist)
        self.template    = template
        self.backupName  = backupName # None if backup disabled

        self.stripAround = True
        self.stripMulti  = True

        self.writeMode   = WriteMode.SeparateSkipExisting
        self.destPath    = ""
        self.destFile    = None

        self.deleteJson  = False


    def runPrepare(self):
        self.parser = TemplateVariableParser(None)
        self.parser.stripAround = self.stripAround
        self.parser.stripMultiWhitespace = self.stripMulti

        match self.writeMode:
            case WriteMode.SingleReplace:
                self.destFile = open(self.destPath, 'w')
            case WriteMode.SingleAppend:
                self.destFile = open(self.destPath, 'a')
    
    def runCleanup(self):
        if self.destFile:
            self.destFile.flush()
            self.destFile.close()


    def runProcessFile(self, imgFile) -> str:
        captionFile = CaptionFile(imgFile)
        if not captionFile.loadFromJson():
            self.log(f"WARNING: Couldn't read captions from {captionFile.jsonPath}")
            return None

        if self.destFile:
            writtenFile = self.processFileSingleDest(imgFile, captionFile)
        else:
            writtenFile = self.processFile(imgFile, captionFile)

        if self.deleteJson and not self.backupName:
            self.deleteFile(captionFile.jsonPath)

        return writtenFile


    def processFile(self, imgFile: str, captionFile: CaptionFile):
        txtFile = self.getTextFile(imgFile)
        if self.backupName:
            self.backup(txtFile, captionFile)

        if (self.writeMode != WriteMode.SeparateReplace) and os.path.exists(txtFile):
            return None

        caption = self.parseCaption(imgFile, captionFile)
        with open(txtFile, 'w') as file:
            file.write(caption)
        return txtFile

    def processFileSingleDest(self, imgFile: str, captionFile: CaptionFile):
        caption = self.parseCaption(imgFile, captionFile)
        self.destFile.write(caption)
        return self.destPath


    def parseCaption(self, imgFile: str, captionFile: CaptionFile) -> str:
        self.parser.setup(imgFile, captionFile)
        caption = self.parser.parse(self.template)

        if self.parser.missingVars:
            self.log(f"WARNING: {captionFile.jsonPath} is missing values for variables: {', '.join(self.parser.missingVars)}")
        
        return caption


    def backup(self, txtFile, captionFile: CaptionFile):
        if os.path.exists(txtFile):
            with open(txtFile, 'r') as file:
                caption = file.read()
            captionFile.addCaption(self.backupName, caption)
            captionFile.saveToJson()

    def getTextFile(self, imgFile):
        path, ext = os.path.splitext(imgFile)
        return f"{path}.txt"

    def deleteFile(self, path) -> None:
        if os.path.isfile(path):
            os.remove(path)
            self.log(f"Deleted {path}")
