import os
from typing import ForwardRef
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, Slot
from caption import CaptionPreset, CaptionRulesProcessor
from config import Config
from infer import Inference
from lib import qtlib, util
from lib.captionfile import CaptionFile
from .batch_task import BatchTask


BatchRulesGroup = ForwardRef("BatchRulesGroup")


class BatchRules(QtWidgets.QWidget):
    def __init__(self, tab, logSlot, progressBar, statusBar):
        super().__init__()
        self.tab = tab
        self.log = logSlot
        self.progressBar: QtWidgets.QProgressBar = progressBar
        self.statusBar: qtlib.ColoredMessageStatusBar = statusBar

        self.bannedSeparator = ", "
        self.captionFile: CaptionFile = None
        self._task = None
        self._defaultPresetPath = Config.pathExport
        self._highlightFormats = dict()
        self._updateEnabled = True

        self.btnStart = QtWidgets.QPushButton("Start Batch Rules")
        self.btnStart.clicked.connect(self.startStop)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._buildRules())
        layout.addWidget(self._buildGroups())
        layout.addWidget(self._buildSettings())
        layout.addWidget(self.btnStart)

        layout.setStretch(0, 0)
        layout.setStretch(1, 0)
        layout.setStretch(2, 1)
        layout.setStretch(3, 0)
        self.setLayout(layout)


    def _buildRules(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)
        layout.setColumnStretch(3, 0)

        row = 0
        self.txtSeparator = QtWidgets.QLineEdit(", ")
        self.txtSeparator.editingFinished.connect(self.updatePreview)
        qtlib.setMonospace(self.txtSeparator)
        layout.addWidget(QtWidgets.QLabel("Separator:"), row, 0)
        layout.addWidget(self.txtSeparator, row, 1)

        btnLoadFromCaption = QtWidgets.QPushButton("Load from Caption window")
        btnLoadFromCaption.clicked.connect(self.loadFromCaptionWindow)
        layout.addWidget(btnLoadFromCaption, row, 2, Qt.AlignRight)

        btnLoadFromFile = QtWidgets.QPushButton("Load from file...")
        btnLoadFromFile.clicked.connect(self.loadFromFile)
        layout.addWidget(btnLoadFromFile, row, 3)

        row += 1
        self.txtPrefix = QtWidgets.QPlainTextEdit()
        self.txtPrefix.textChanged.connect(self.updatePreview)
        qtlib.setMonospace(self.txtPrefix)
        qtlib.setTextEditHeight(self.txtPrefix, 2)
        qtlib.setShowWhitespace(self.txtPrefix)
        layout.addWidget(QtWidgets.QLabel("Prefix:"), row, 0, Qt.AlignTop)
        layout.addWidget(self.txtPrefix, row, 1, 1, 2)

        self.chkPrefixSeparator = QtWidgets.QCheckBox("Append separator")
        self.chkPrefixSeparator.setChecked(True)
        self.chkPrefixSeparator.checkStateChanged.connect(self.updatePreview)
        layout.addWidget(self.chkPrefixSeparator, row, 3, Qt.AlignTop)

        row += 1
        self.txtSuffix = QtWidgets.QPlainTextEdit()
        self.txtSuffix.textChanged.connect(self.updatePreview)
        qtlib.setMonospace(self.txtSuffix)
        qtlib.setTextEditHeight(self.txtSuffix, 2)
        qtlib.setShowWhitespace(self.txtSuffix)
        layout.addWidget(QtWidgets.QLabel("Suffix:"), row, 0, Qt.AlignTop)
        layout.addWidget(self.txtSuffix, row, 1, 1, 2)

        self.chkSuffixSeparator = QtWidgets.QCheckBox("Prepend separator")
        self.chkSuffixSeparator.setChecked(True)
        self.chkSuffixSeparator.checkStateChanged.connect(self.updatePreview)
        layout.addWidget(self.chkSuffixSeparator, row, 3, Qt.AlignTop)

        row += 1
        self.txtBanned = QtWidgets.QPlainTextEdit()
        self.txtBanned.textChanged.connect(self._onBannedChanged)
        qtlib.setMonospace(self.txtBanned)
        qtlib.setTextEditHeight(self.txtBanned, 5)
        qtlib.setShowWhitespace(self.txtBanned)
        layout.addWidget(QtWidgets.QLabel("Banned:"), row, 0, Qt.AlignTop)
        layout.addWidget(self.txtBanned, row, 1, 1, 3)

        row += 1
        self.chkRemoveDup = QtWidgets.QCheckBox("Remove duplicates")
        self.chkRemoveDup.setChecked(True)
        self.chkRemoveDup.checkStateChanged.connect(self.updatePreview)
        layout.addWidget(self.chkRemoveDup, row, 1)

        groupBox = QtWidgets.QGroupBox("Rules")
        groupBox.setLayout(layout)
        return groupBox


    def _buildGroups(self):
        self.groupLayout = QtWidgets.QVBoxLayout()
        self.groupLayout.setSpacing(8)
        groupBox = QtWidgets.QGroupBox("Groups")
        groupBox.setLayout(self.groupLayout)
        return groupBox


    def _buildSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 1)

        row = 0
        layout.addWidget(QtWidgets.QLabel("Load key:"), row, 0, Qt.AlignTop)

        self.cboSrcType = QtWidgets.QComboBox()
        self.cboSrcType.addItem("tags")
        self.cboSrcType.addItem("captions")
        self.cboSrcType.currentIndexChanged.connect(self.updatePreview)
        qtlib.setMonospace(self.cboSrcType)
        layout.addWidget(self.cboSrcType, row, 1)

        self.txtSourceKey = QtWidgets.QLineEdit("tags")
        self.txtSourceKey.editingFinished.connect(self.updatePreview)
        qtlib.setMonospace(self.txtSourceKey)
        layout.addWidget(self.txtSourceKey, row, 2)

        row += 1
        layout.addWidget(QtWidgets.QLabel("Storage key:"), row, 0, Qt.AlignTop)

        self.cboTargetType = QtWidgets.QComboBox()
        self.cboTargetType.addItem("tags")
        self.cboTargetType.addItem("captions")
        qtlib.setMonospace(self.cboTargetType)
        layout.addWidget(self.cboTargetType, row, 1)

        self.txtTargetKey = QtWidgets.QLineEdit("tags")
        qtlib.setMonospace(self.txtTargetKey)
        layout.addWidget(self.txtTargetKey, row, 2)

        self.chkSkipExisting = QtWidgets.QCheckBox("Skip file if key exists")
        layout.addWidget(self.chkSkipExisting, row, 3)

        row += 1
        layout.setRowStretch(row, 1)

        self.txtPreview = QtWidgets.QPlainTextEdit()
        self.txtPreview.setReadOnly(True)
        qtlib.setMonospace(self.txtPreview)
        qtlib.setTextEditHeight(self.txtPreview, 3, mode="min")
        qtlib.setShowWhitespace(self.txtPreview)
        layout.addWidget(QtWidgets.QLabel("Preview:"), row, 0, Qt.AlignTop)
        layout.addWidget(self.txtPreview, row, 1, 1, 3)


        groupBox = QtWidgets.QGroupBox("Batch Settings")
        groupBox.setLayout(layout)
        return groupBox


    def onFileChanged(self, currentFile):
        self.captionFile = CaptionFile(currentFile)
        self.captionFile.loadFromJson()
        self.updatePreview()


    @property
    def bannedCaptions(self) -> list[str]:
        return [b.strip() for b in self.txtBanned.toPlainText().split(self.bannedSeparator.strip())]

    @Slot()
    def _onBannedChanged(self):
        self._updateHighlightFormats()
        self.updatePreview()


    @property
    def groups(self):
        for i in range(self.groupLayout.count()):
            widget = self.groupLayout.itemAt(i).widget()
            if widget and isinstance(widget, BatchRulesGroup):
                yield widget

    def addGroup(self, title: str, color: str, exclusive: bool, captions: list):
        group = BatchRulesGroup(title, color, exclusive, captions, self.updatePreview)
        index = self.groupLayout.count()
        self.groupLayout.insertWidget(index, group)


    def removeAllGroups(self):
        for i in reversed(range(self.groupLayout.count())):
            widget = self.groupLayout.itemAt(i).widget()
            if widget:
                self.groupLayout.removeWidget(widget)
                widget.deleteLater()


    def applyPreset(self, preset):
        try:
            self._updateEnabled = False
            
            self.txtPrefix.setPlainText(preset.prefix)
            self.txtSuffix.setPlainText(preset.suffix)
            self.txtSeparator.setText(preset.separator)
            self.chkPrefixSeparator.setChecked(preset.prefixSeparator)
            self.chkSuffixSeparator.setChecked(preset.suffixSeparator)
            self.chkRemoveDup.setChecked(preset.removeDuplicates)
            self.txtBanned.setPlainText( self.bannedSeparator.join(preset.banned) )

            self.removeAllGroups()
            for group in preset.groups:
                self.addGroup(group.name, group.color, group.mutuallyExclusive, group.captions)
        finally:
            self._updateEnabled = True
            self._updateHighlightFormats()
            self.updatePreview()

    @Slot()
    def loadFromFile(self):
        fileFilter = "JSON (*.json)"
        path, selectedFilter = QtWidgets.QFileDialog.getOpenFileName(self, "Load preset", self._defaultPresetPath, fileFilter)
        if path:
            self._defaultPresetPath = os.path.dirname(path)

            preset = CaptionPreset()
            preset.loadFrom(path)
            self.applyPreset(preset)

    @Slot()
    def loadFromCaptionWindow(self):
        if captionContainer := self.tab.getWindowContent("caption"):
            preset = captionContainer.ctx.settings.getPreset()
            self.applyPreset(preset)
        else:
            self.statusBar.showColoredMessage("Caption window not open", False)


    def setupProcessor(self) -> CaptionRulesProcessor:
        separator = self.txtSeparator.text()

        prefix = self.txtPrefix.toPlainText()
        if prefix and self.chkPrefixSeparator.isChecked():
            prefix += separator

        suffix = self.txtSuffix.toPlainText()
        if suffix and self.chkSuffixSeparator.isChecked():
            suffix = separator + suffix

        rulesProcessor = CaptionRulesProcessor()
        rulesProcessor.setup(prefix, suffix, separator, self.chkRemoveDup.isChecked())
        rulesProcessor.setBannedCaptions(self.bannedCaptions)
        rulesProcessor.setCaptionGroups(
            (group.captions for group in self.groups),
            (group.captions for group in self.groups if group.mutuallyExclusive)
        )
        return rulesProcessor

    @Slot()
    def updatePreview(self):
        if not self._updateEnabled:
            return

        text = None
        srcType = self.cboSrcType.currentText()
        srcKey = self.txtSourceKey.text().strip()
        if srcType == "tags":
            text = self.captionFile.getTags(srcKey)
        elif srcType == "captions":
            text = self.captionFile.getCaption(srcKey)

        if text:
            rulesProcessor = self.setupProcessor()
            text = rulesProcessor.process(text)
        else:
            text = ""
        
        self.txtPreview.setPlainText(text)
        self._highlight(text)

    def _highlight(self, text: str):
        cursor = self.txtPreview.textCursor()
        cursor.setPosition(0)
        cursor.movePosition(QtGui.QTextCursor.End, QtGui.QTextCursor.KeepAnchor)
        cursor.setCharFormat(QtGui.QTextCharFormat())

        start = 0
        sep = self.txtSeparator.text().strip()
        for caption in text.split(sep):
            if format := self._highlightFormats.get(caption.strip()):
                cursor.setPosition(start)
                cursor.setPosition(start+len(caption), QtGui.QTextCursor.KeepAnchor)
                cursor.setCharFormat(format)
            start += len(caption) + len(sep)

    def _updateHighlightFormats(self):
        colorV = QtWidgets.QApplication.palette().color(QtGui.QPalette.ColorRole.Text).valueF()
        colorV = max(colorV, 0.2)

        self._highlightFormats.clear()
        for group in self.groups:
            groupFormat = QtGui.QTextCharFormat()
            groupFormat.setForeground(QtGui.QColor.fromHsvF(util.get_hue(group.color), 0.35, colorV))
            for cap in group.captions:
                self._highlightFormats[cap] = groupFormat
        
        bannedFormat = QtGui.QTextCharFormat()
        bannedFormat.setForeground(QtGui.QColor.fromHsvF(0, 0, 0.5))
        for cap in self.bannedCaptions:
            self._highlightFormats[cap] = bannedFormat


    @Slot()
    def startStop(self):
        if self._task:
            self._task.abort()
        else:
            self.btnStart.setText("Abort")

            self._task = BatchRulesTask(self.log, self.tab.filelist, self.setupProcessor())
            self._task.srcType = self.cboSrcType.currentText()
            self._task.srcKey  = self.txtSourceKey.text().strip()
            self._task.targetType = self.cboTargetType.currentText()
            self._task.targetKey  = self.txtTargetKey.text().strip()
            self._task.skipExisting = self.chkSkipExisting.isChecked()

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
    def onProgress(self, numDone, numTotal, jsonFile):
        self.progressBar.setRange(0, numTotal)
        self.progressBar.setValue(numDone)

        if jsonFile:
            self.statusBar.showMessage("Wrote " + jsonFile)

    @Slot()
    def onProgressMessage(self, message):
        self.statusBar.showMessage(message)

    def taskDone(self):
        self.btnStart.setText("Start Batch Rules")
        self.progressBar.setRange(0, 1)
        self.progressBar.reset()
        self._task = None



class BatchRulesGroup(QtWidgets.QWidget):
    def __init__(self, title: str, color: str, exclusive: bool, captions: list, updatePreview):
        super().__init__()
        self.color = color
        self.captions = list(captions)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        lblTitle = QtWidgets.QLabel(f"{title}:")
        lblTitle.setMinimumWidth(Config.batchWinLegendWidth)
        qtlib.setMonospace(lblTitle, 1.0, True)
        layout.addWidget(lblTitle, 0, Qt.AlignTop)

        flowLayout = qtlib.FlowLayout(spacing=1)

        self.chkExclusive = QtWidgets.QCheckBox("Mutually exclusive")
        self.chkExclusive.setChecked(exclusive)
        self.chkExclusive.checkStateChanged.connect(updatePreview)
        flowLayout.addWidget(self.chkExclusive)

        for cap in captions:
            label = QtWidgets.QLabel(cap)
            qtlib.setMonospace(label)
            label.setStyleSheet("color: #fff; background-color: " + color + "; border: 3px solid " + color + "; border-radius: 8px")
            flowLayout.addWidget(label)

        self.flowWidget = QtWidgets.QWidget()
        self.flowWidget.setLayout(flowLayout)
        layout.addWidget(self.flowWidget, 1)

        self.setLayout(layout)


    @property
    def mutuallyExclusive(self) -> bool:
        return self.chkExclusive.isChecked()

    def resizeEvent(self, event) -> None:
        self.flowWidget.setMinimumHeight(self.flowWidget.sizeHint().height())
        return super().resizeEvent(event)



class BatchRulesTask(BatchTask):
    def __init__(self, log, filelist, rulesProcessor: CaptionRulesProcessor):
        super().__init__("rules", log, filelist)
        self.rulesProcessor = rulesProcessor

        self.srcType = ""
        self.srcKey = ""
        self.targetType = ""
        self.targetKey = ""

        self.skipExisting = False


    def runPrepare(self):
        pass


    def runProcessFile(self, imgFile: str) -> str:
        captionFile = CaptionFile(imgFile)
        if captionFile.jsonExists() and not captionFile.loadFromJson():
            self.log(f"WARNING: Failed to load captions from {captionFile.jsonPath}")
            return None

        if self.skipExisting and self.targetKeyExists(captionFile):
            return None

        if self.srcType == "tags":
            text = captionFile.getTags(self.srcKey)
        else:
            text = captionFile.getCaption(self.srcKey)

        if not text:
            self.log(f"WARNING: {captionFile.jsonPath} is missing value for {self.srcType}.{self.srcKey}")
            return None

        text = self.rulesProcessor.process(text)
        if not text:
            self.log(f"WARNING: Caption is empty for {imgFile}, ignoring")
            return None

        if self.targetType == "tags":
            captionFile.addTags(self.targetKey, text)
        else:
            captionFile.addCaption(self.targetKey, text)

        captionFile.saveToJson()
        return captionFile.jsonPath


    def targetKeyExists(self, captionFile: CaptionFile) -> bool:
        if self.targetType == "tags":
            return self.targetKey in captionFile.tags
        else:
            return self.targetKey in captionFile.captions
