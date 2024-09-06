from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
import qtlib
from config import Config
from prompt_parser import PromptTemplateParser


class BatchApply(QtWidgets.QWidget):
    def __init__(self, tab, progressBar, statusBar):
        super().__init__()
        self.tab = tab
        self.progressBar: QtWidgets.QProgressBar = progressBar
        self.statusBar: QtWidgets.QStatusBar = statusBar

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._buildFormatSettings())
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

        self.txtTemplate = QtWidgets.QTextEdit()
        self.txtTemplate.setPlainText(Config.batchTemplate)
        qtlib.setMonospace(self.txtTemplate)
        qtlib.setTextEditHeight(self.txtTemplate, 10)
        qtlib.setShowWhitespace(self.txtTemplate)
        self.txtTemplate.textChanged.connect(self._updatePreview)
        layout.addWidget(QtWidgets.QLabel("Template:"), 0, 0, Qt.AlignTop)
        layout.addWidget(self.txtTemplate, 0, 1, 1, 2)

        self.txtPreview = QtWidgets.QTextEdit()
        self.txtPreview.setReadOnly(True)
        qtlib.setMonospace(self.txtPreview)
        #qtlib.setTextEditHeight(self.txtPreview, 10)
        qtlib.setShowWhitespace(self.txtPreview)
        layout.addWidget(QtWidgets.QLabel("Preview:"), 1, 0, Qt.AlignTop)
        layout.addWidget(self.txtPreview, 1, 1, 1, 2)

        self.chkStripAround = QtWidgets.QCheckBox("Strip surrounding whitespace")
        self.chkStripAround.setChecked(True)
        self.chkStripAround.checkStateChanged.connect(self._updateParser)
        layout.addWidget(self.chkStripAround, 2, 1)

        self.chkStripMulti = QtWidgets.QCheckBox("Strip repeating whitespace")
        self.chkStripMulti.setChecked(True)
        self.chkStripMulti.checkStateChanged.connect(self._updateParser)
        layout.addWidget(self.chkStripMulti, 2, 2)

        #self.chkApplyRules = QtWidgets.QCheckBox("Apply Caption Rules")

        groupBox = QtWidgets.QGroupBox("Format")
        groupBox.setLayout(layout)
        return groupBox

    def _buildApplySettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnStretch(0, 0)

        self.btnStart = QtWidgets.QPushButton("Start")
        #self.btnStart.clicked.connect(self.startStop)
        layout.addWidget(self.btnStart, 1, 0, 1, 2)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        return widget


    def onFileChanged(self, currentFile):
        self._parser = PromptTemplateParser(currentFile)
        self._updateParser()

    def _updateParser(self):
        if self._parser:
            self._parser.stripAround = self.chkStripAround.isChecked()
            self._parser.stripMultiWhitespace = self.chkStripMulti.isChecked()
            self._updatePreview()


    @Slot()
    def _updatePreview(self):
        text = self.txtTemplate.toPlainText()
        prompt = self._parser.parse(text)
        self.txtPreview.setPlainText(prompt)
