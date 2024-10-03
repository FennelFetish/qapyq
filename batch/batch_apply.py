import os
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QSignalBlocker
import qtlib
from config import Config
from infer import Inference
from template_parser import TemplateVariableParser, VariableHighlighter
from .batch_task import BatchTask
from .captionfile import CaptionFile


class BatchApply(QtWidgets.QWidget):
    def __init__(self, tab, logSlot, progressBar, statusBar):
        super().__init__()
        self.tab = tab
        self.log = logSlot
        self.progressBar: QtWidgets.QProgressBar = progressBar
        self.statusBar: qtlib.ColoredMessageStatusBar = statusBar

        self.backupSettings = self._buildBackupSettings()

        self.btnStart = QtWidgets.QPushButton("Start Batch Apply")
        self.btnStart.clicked.connect(self.startStop)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._buildFormatSettings())
        layout.addWidget(self.backupSettings)
        layout.addWidget(self.btnStart)
        self.setLayout(layout)

        self._parser = None
        self._highlighter = VariableHighlighter()
        self._task = None

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

        row += 1
        layout.addWidget(QtWidgets.QLabel("Processing:"), row, 0)

        self.chkOverwrite = QtWidgets.QCheckBox("Overwrite .txt")
        self.chkOverwrite.setChecked(True)
        layout.addWidget(self.chkOverwrite, row, 1)

        self.chkDeleteJson = QtWidgets.QCheckBox("Delete .json")
        self.chkDeleteJson.toggled.connect(self._onDeleteJsonToggled)
        layout.addWidget(self.chkDeleteJson, row, 2)


        groupBox = QtWidgets.QGroupBox("Write to Text File")
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
            self._task.overwrite   = self.chkOverwrite.isChecked()
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

        self.overwrite   = True
        self.deleteJson  = False


    def runPrepare(self):
        self.parser = TemplateVariableParser(None)
        self.parser.stripAround = self.stripAround
        self.parser.stripMultiWhitespace = self.stripMulti

    def runProcessFile(self, imgFile) -> str:
        captionFile = CaptionFile(imgFile)
        if not captionFile.loadFromJson():
            self.log(f"WARNING: Couldn't read captions from {captionFile.jsonPath}")
            return None

        writtenFile = self.processFile(imgFile, captionFile)

        if self.deleteJson and not self.backupName:
            self.deleteFile(captionFile.jsonPath)

        return writtenFile


    def processFile(self, imgFile: str, captionFile: CaptionFile):
        txtFile = self.getTextFile(imgFile)
        if self.backupName:
            self.backup(txtFile, captionFile)

        if (not self.overwrite) and os.path.exists(txtFile):
            return None

        self.parser.setup(imgFile, captionFile)
        caption = self.parser.parse(self.template)

        if self.parser.missingVars:
            self.log(f"WARNING: {captionFile.jsonPath} is missing values for variables: {', '.join(self.parser.missingVars)}")

        with open(txtFile, 'w') as file:
            file.write(caption)
        return txtFile


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
