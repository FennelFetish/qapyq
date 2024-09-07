import os
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
import qtlib
from config import Config
from infer import Inference
from template_parser import TemplateParser
from .batch_task import BatchTask
from .captionfile import CaptionFile


class BatchApply(QtWidgets.QWidget):
    def __init__(self, tab, logSlot, progressBar, statusBar):
        super().__init__()
        self.tab = tab
        self.log = logSlot
        self.progressBar: QtWidgets.QProgressBar = progressBar
        self.statusBar: QtWidgets.QStatusBar = statusBar

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._buildFormatSettings())
        layout.addWidget(self._buildBackupSettings())
        layout.addWidget(self._buildApplySettings())
        self.setLayout(layout)

        self._parser = None
        self._task = None

    def _buildFormatSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)

        self.txtTemplate = QtWidgets.QPlainTextEdit()
        self.txtTemplate.setPlainText(Config.batchTemplate)
        qtlib.setMonospace(self.txtTemplate)
        qtlib.setTextEditHeight(self.txtTemplate, 10)
        qtlib.setShowWhitespace(self.txtTemplate)
        self.txtTemplate.textChanged.connect(self._updatePreview)
        layout.addWidget(QtWidgets.QLabel("Template:"), 0, 0, Qt.AlignTop)
        layout.addWidget(self.txtTemplate, 0, 1, 1, 2)

        self.txtPreview = QtWidgets.QPlainTextEdit()
        self.txtPreview.setReadOnly(True)
        qtlib.setMonospace(self.txtPreview)
        qtlib.setShowWhitespace(self.txtPreview)
        layout.addWidget(QtWidgets.QLabel("Preview:"), 1, 0, Qt.AlignTop)
        layout.addWidget(self.txtPreview, 1, 1, 1, 2)

        self.chkStripAround = QtWidgets.QCheckBox("Surrounding whitespace")
        self.chkStripAround.setChecked(True)
        self.chkStripAround.checkStateChanged.connect(self._updateParser)

        self.chkStripMulti = QtWidgets.QCheckBox("Repeating whitespace")
        self.chkStripMulti.setChecked(True)
        self.chkStripMulti.checkStateChanged.connect(self._updateParser)

        layout.addWidget(QtWidgets.QLabel("Strip:"), 2, 0, Qt.AlignTop)
        layout.addWidget(self.chkStripAround, 2, 1)
        layout.addWidget(self.chkStripMulti, 2, 2)

        #self.chkApplyRules = QtWidgets.QCheckBox("Apply Caption Rules")

        groupBox = QtWidgets.QGroupBox("Format")
        groupBox.setLayout(layout)
        return groupBox

    def _buildBackupSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnStretch(0, 0)

        self.txtBackupName = QtWidgets.QLineEdit()
        self.txtBackupName.setEnabled(False)
        layout.addWidget(QtWidgets.QLabel("Store as:"), 0, 0, Qt.AlignTop)
        layout.addWidget(self.txtBackupName, 0, 1)

        self.chkBackup = QtWidgets.QCheckBox("Enable backup from .txt into .json file")
        self.chkBackup.checkStateChanged.connect(lambda state: self.txtBackupName.setEnabled(state == Qt.Checked))
        layout.addWidget(self.chkBackup, 1, 1)

        groupBox = QtWidgets.QGroupBox("Backup")
        groupBox.setLayout(layout)
        return groupBox

    def _buildApplySettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnStretch(0, 0)

        self.btnStart = QtWidgets.QPushButton("Start")
        self.btnStart.clicked.connect(self.startStop)
        layout.addWidget(self.btnStart, 1, 0, 1, 2)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        return widget


    def onFileChanged(self, currentFile):
        self._parser = TemplateParser(currentFile)
        self._updateParser()

    def _updateParser(self):
        if self._parser:
            self._parser.stripAround = self.chkStripAround.isChecked()
            self._parser.stripMultiWhitespace = self.chkStripMulti.isChecked()
            self._updatePreview()


    @Slot()
    def _updatePreview(self):
        text = self.txtTemplate.toPlainText()
        preview = self._parser.parse(text)
        self.txtPreview.setPlainText(preview)


    @Slot()
    def startStop(self):
        if self._task:
            self._task.abort()
        else:
            self.btnStart.setText("Abort")
            self.statusBar.showMessage("Starting batch apply ...")

            template = self.txtTemplate.toPlainText()
            backupName = self.txtBackupName.text().strip() if self.chkBackup.isChecked() else None
            self._task = BatchApplyTask(self.log, self.tab.filelist, template, self.chkStripAround.isChecked(), self.chkStripMulti.isChecked(), backupName)
            self._task.signals.progress.connect(self.onProgress)
            self._task.signals.done.connect(self.onFinished)
            self._task.signals.fail.connect(self.onFail)
            Inference().threadPool.start(self._task)

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

    def taskDone(self):
        self.btnStart.setText("Start")
        self.progressBar.reset()
        self._task = None



class BatchApplyTask(BatchTask):
    def __init__(self, log, filelist, template, stripAround, stripMulti, backupName):
        super().__init__("apply", log, filelist)
        self.template    = template
        self.stripAround = stripAround
        self.stripMulti  = stripMulti
        self.backupName  = backupName

    def runPrepare(self):
        self.parser = TemplateParser(None)
        self.parser.stripAround = self.stripAround
        self.parser.stripMultiWhitespace = self.stripMulti

    def runProcessFile(self, imgFile) -> str:
        captionFile = CaptionFile(imgFile)
        if captionFile.loadFromJson():
            txtFile = self.getTextFile(imgFile)
            if self.backupName:
                self.backup(txtFile, captionFile)

            self.parser.setup(imgFile, captionFile)
            caption = self.parser.parse(self.template)

            with open(txtFile, 'w') as file:
                file.write(caption)
            return txtFile
        else:
            self.log(f"WARNING: Couldn't read captions from {captionFile.jsonPath}")
            return None

    def backup(self, txtFile, captionFile):
        if os.path.exists(txtFile):
            with open(txtFile, 'r') as file:
                caption = file.read()
            captionFile.addCaption(self.backupName, caption)
            captionFile.saveToJson()

    def getTextFile(self, imgFile):
        path, ext = os.path.splitext(imgFile)
        return f"{path}.txt"
