import os
from typing import Callable, Iterable
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, Slot, Signal, QTimer
from caption.caption_preset import CaptionPreset, CaptionPresetConditional, MutualExclusivity
from caption.caption_filter import CaptionRulesProcessor
from caption.caption_conditionals import ConditionalRule
from caption.caption_wildcard import expandWildcards
from caption.caption_highlight import CaptionHighlight, HighlightDataSource, CaptionGroupData
from config import Config
from infer import Inference
from ui.edit_table import EditableTable
from ui.flow_layout import FlowLayout, SortedStringFlowWidget, ManualStartReorderWidget
from lib import qtlib
from lib.captionfile import CaptionFile, FileTypeSelector
from .batch_task import BatchTask, BatchSignalHandler, BatchUtil


class BatchRules(QtWidgets.QWidget):
    formatsUpdated = Signal()

    def __init__(self, tab, logSlot, progressBar, statusBar):
        super().__init__()
        self.tab = tab
        self.log = logSlot
        self.progressBar: QtWidgets.QProgressBar = progressBar
        self.statusBar: qtlib.ColoredMessageStatusBar = statusBar

        self.bannedSeparator = ", "
        self.captionFile: CaptionFile = None
        self._defaultPresetPath = Config.pathExport
        self._updateEnabled = True

        self.highlight = CaptionHighlight(BatchRulesDataSource(self))
        self.wildcards = dict[str, list[str]]()

        self._task = None
        self._taskSignalHandler = None

        splitter = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._buildSubTabs())
        splitter.addWidget(self._buildSettings())
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 1)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(splitter)

        self.btnStart = QtWidgets.QPushButton("Start Batch Rules")
        self.btnStart.clicked.connect(self.startStop)
        layout.addWidget(self.btnStart)

        self.setLayout(layout)


    def _buildMenuButton(self) -> QtWidgets.QPushButton:
        self._menu = QtWidgets.QMenu("Batch Rules")
        actLoadFromCaptionWin = self._menu.addAction("Load Rules from Caption Window")
        actLoadFromCaptionWin.triggered.connect(self.loadFromCaptionWindow)

        actLoadFromFile = self._menu.addAction("Load Rules from File…")
        actLoadFromFile.triggered.connect(self.loadFromFile)

        self._menu.addSeparator()

        actClearRules = self._menu.addAction("Clear Rules…")
        actClearRules.triggered.connect(self.clearRules)

        btnMenu = QtWidgets.QPushButton("Preset…")
        btnMenu.setMenu(self._menu)
        return btnMenu

    def _buildSubTabs(self):
        self.subtabWidget = QtWidgets.QTabWidget()
        self.subtabWidget.setCornerWidget(self._buildMenuButton(), Qt.Corner.TopLeftCorner)
        self.subtabWidget.addTab(self._buildRules(), "Rules")
        self.subtabWidget.addTab(self._buildGroups(), "Groups")
        self.subtabWidget.addTab(self._buildConditionals(), "Conditionals")
        return self.subtabWidget

    def showSubtab(self, name: str):
        tabIndexes = {
            "rules": 0,
            "groups": 1,
            "conditionals": 2
        }
        self.subtabWidget.setCurrentIndex(tabIndexes[name])


    def _buildRules(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 0)
        layout.setColumnStretch(4, 1)
        layout.setColumnStretch(5, 0)
        layout.setColumnStretch(6, 0)

        row = 0
        self.txtSeparator = QtWidgets.QLineEdit(", ")
        self.txtSeparator.editingFinished.connect(self.updatePreview)
        qtlib.setMonospace(self.txtSeparator)
        layout.addWidget(QtWidgets.QLabel("Separator:"), row, 0)
        layout.addWidget(self.txtSeparator, row, 1)

        self.chkRemoveDup = QtWidgets.QCheckBox("Remove Duplicates/Subsets")
        self.chkRemoveDup.setChecked(False)
        self.chkRemoveDup.checkStateChanged.connect(self.updatePreview)
        layout.addWidget(self.chkRemoveDup, row, 2)

        self.chkSortCaptions = QtWidgets.QCheckBox("Sort Captions")
        self.chkSortCaptions.setChecked(False)
        self.chkSortCaptions.checkStateChanged.connect(self.updatePreview)
        layout.addWidget(self.chkSortCaptions, row, 3, 1, 2)

        row += 1
        self.txtPrefix = QtWidgets.QPlainTextEdit()
        self.txtPrefix.textChanged.connect(self.updatePreview)
        qtlib.setMonospace(self.txtPrefix)
        qtlib.setTextEditHeight(self.txtPrefix, 2)
        qtlib.setShowWhitespace(self.txtPrefix)
        layout.addWidget(QtWidgets.QLabel("Prefix:"), row, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.txtPrefix, row, 1, 1, 5)

        self.chkPrefixSeparator = QtWidgets.QCheckBox("Append Separator")
        self.chkPrefixSeparator.setChecked(True)
        self.chkPrefixSeparator.checkStateChanged.connect(self.updatePreview)
        layout.addWidget(self.chkPrefixSeparator, row, 6, Qt.AlignmentFlag.AlignTop)

        row += 1
        self.txtSuffix = QtWidgets.QPlainTextEdit()
        self.txtSuffix.textChanged.connect(self.updatePreview)
        qtlib.setMonospace(self.txtSuffix)
        qtlib.setTextEditHeight(self.txtSuffix, 2)
        qtlib.setShowWhitespace(self.txtSuffix)
        layout.addWidget(QtWidgets.QLabel("Suffix:"), row, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.txtSuffix, row, 1, 1, 5)

        self.chkSuffixSeparator = QtWidgets.QCheckBox("Prepend Separator")
        self.chkSuffixSeparator.setChecked(True)
        self.chkSuffixSeparator.checkStateChanged.connect(self.updatePreview)
        layout.addWidget(self.chkSuffixSeparator, row, 6, Qt.AlignmentFlag.AlignTop)

        row += 1
        layout.setRowMinimumHeight(row, 8)

        row += 1
        layout.addWidget(QtWidgets.QLabel("Replace:"), row, 0)

        lblBanned = QtWidgets.QLabel("Banned:")
        lblBanned.setMinimumWidth(lblBanned.sizeHint().width() + 12)
        layout.addWidget(lblBanned, row, 3)

        self.chkWhitelistGroups = QtWidgets.QCheckBox("Groups are Whitelists (Ban all other tags)")
        self.chkWhitelistGroups.toggled.connect(lambda checked: self.banWidget.setEnabled(not checked))
        self.chkWhitelistGroups.toggled.connect(self.updatePreview)
        layout.addWidget(self.chkWhitelistGroups, row, 4)

        self.txtBanAdd = QtWidgets.QLineEdit()
        self.txtBanAdd.setMinimumWidth(200)
        self.txtBanAdd.returnPressed.connect(self._addBanned)
        qtlib.setMonospace(self.txtBanAdd)
        layout.addWidget(self.txtBanAdd, row, 5)

        btnBanAdd = QtWidgets.QPushButton("Add Banned")
        btnBanAdd.clicked.connect(self._addBanned)
        layout.addWidget(btnBanAdd, row, 6)

        row += 1
        self.tableReplace = EditableTable(2)
        self.tableReplace.contentChanged.connect(self.updatePreview)
        self.tableReplace.setHorizontalHeaderLabels(["Search Pattern", "Replacement"])
        layout.addWidget(self.tableReplace, row, 0, 1, 3)

        self.banWidget = SortedStringFlowWidget()
        self.banWidget.changed.connect(self._onBannedChanged)
        layout.addWidget(qtlib.BaseColorScrollArea(self.banWidget), row, 3, 1, 4)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        return widget

    def _buildGroups(self):
        self.groupLayout = QtWidgets.QVBoxLayout()
        self.groupLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.groupLayout.setSpacing(8)

        widget = QtWidgets.QWidget()
        widget.setLayout(self.groupLayout)
        scrollArea = qtlib.RowScrollArea(widget)
        scrollArea.setFrameStyle(QtWidgets.QFrame.Shape.NoFrame)
        return scrollArea

    def _buildConditionals(self):
        self.conditionalsLayout = QtWidgets.QVBoxLayout()
        self.conditionalsLayout.setContentsMargins(0, 0, 0, 0)
        self.conditionalsLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.conditionalsLayout.setSpacing(8)

        condReorderWidget = ManualStartReorderWidget()
        condReorderWidget.setLayout(self.conditionalsLayout)
        condReorderWidget.orderChanged.connect(self.updatePreview)
        scrollArea = qtlib.RowScrollArea(condReorderWidget)
        scrollArea.setFrameStyle(QtWidgets.QFrame.Shape.NoFrame)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scrollArea, 1)

        btnAddConditional = QtWidgets.QPushButton("✚ Add Conditional Rule")
        btnAddConditional.clicked.connect(lambda: self.addConditional(None))
        layout.addWidget(btnAddConditional, 0, Qt.AlignmentFlag.AlignBottom)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        return widget

    def _buildSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)

        row = 0
        layout.addWidget(QtWidgets.QLabel("Load key:"), row, 0, Qt.AlignmentFlag.AlignTop)

        self.srcSelector = FileTypeSelector(showTxtType=False)
        self.srcSelector.fileTypeUpdated.connect(self.updatePreview)
        layout.addLayout(self.srcSelector, row, 1)

        row += 1
        layout.addWidget(QtWidgets.QLabel("Storage key:"), row, 0, Qt.AlignmentFlag.AlignTop)

        self.destSelector = FileTypeSelector(showTxtType=False, defaultValue="refined")
        layout.addLayout(self.destSelector, row, 1)

        self.chkSkipExisting = QtWidgets.QCheckBox("Skip file if key exists")
        layout.addWidget(self.chkSkipExisting, row, 2)

        row += 1
        layout.setRowStretch(row, 1)

        self.txtPreview = QtWidgets.QPlainTextEdit()
        self.txtPreview.setReadOnly(True)
        qtlib.setMonospace(self.txtPreview)
        qtlib.setTextEditHeight(self.txtPreview, 3, mode="min")
        qtlib.setShowWhitespace(self.txtPreview)
        layout.addWidget(QtWidgets.QLabel("Preview:"), row, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.txtPreview, row, 1, 1, 2)

        groupBox = QtWidgets.QGroupBox("Batch Settings")
        groupBox.setLayout(layout)
        return groupBox


    def onFileChanged(self, currentFile):
        self.captionFile = CaptionFile(currentFile)
        self.captionFile.loadFromJson()
        self.updatePreview()


    @property
    def bannedCaptions(self) -> list[str]:
        return [b.strip() for b in self.banWidget.getItems()]

    @Slot()
    def _onBannedChanged(self):
        self.formatsUpdated.emit()
        self.updatePreview()

    @Slot()
    def _addBanned(self):
        if tag := self.txtBanAdd.text().strip():
            self.banWidget.addItem(tag)
            self.txtBanAdd.clear()


    @property
    def groups(self):
        for i in range(self.groupLayout.count()):
            widget = self.groupLayout.itemAt(i).widget()
            if widget and isinstance(widget, BatchRulesGroup):
                yield widget

    def addGroup(self, title: str, color: str, exclusivity: MutualExclusivity, combine: bool, captions: list[str]):
        group = BatchRulesGroup(title, color, exclusivity, combine, captions, self.updatePreview)
        self.groupLayout.addWidget(group, 0, Qt.AlignmentFlag.AlignTop)

        # TODO: When loading large number of groups 2 times, they are squished. Fix FlowLayout so this isn't needed.
        QTimer.singleShot(1, group.updateHeight)

    def removeAllGroups(self):
        for i in reversed(range(self.groupLayout.count())):
            item = self.groupLayout.takeAt(i)
            if item and (widget := item.widget()):
                widget.deleteLater()


    @property
    def conditionals(self):
        for i in range(self.conditionalsLayout.count()):
            widget = self.conditionalsLayout.itemAt(i).widget()
            if widget and isinstance(widget, ConditionalRule):
                yield widget

    def addConditional(self, cond: CaptionPresetConditional | None):
        condWidget = ConditionalRule()
        if cond:
            condWidget.loadFromPreset(cond)
        condWidget.ruleUpdated.connect(self.updatePreview)
        condWidget.removeClicked.connect(self.removeConditional)
        self.conditionalsLayout.addWidget(condWidget, 0, Qt.AlignmentFlag.AlignTop)

    @Slot()
    def removeConditional(self, condWidget: ConditionalRule):
        self.conditionalsLayout.removeWidget(condWidget)
        condWidget.deleteLater()
        self.updatePreview()

    def removeAllConditionals(self):
        for i in reversed(range(self.conditionalsLayout.count())):
            item = self.conditionalsLayout.takeAt(i)
            if item and (widget := item.widget()):
                widget.deleteLater()


    def applyPreset(self, preset: CaptionPreset):
        try:
            self._updateEnabled = False

            self.txtPrefix.setPlainText(preset.prefix)
            self.txtSuffix.setPlainText(preset.suffix)
            self.txtSeparator.setText(preset.separator)
            self.chkPrefixSeparator.setChecked(preset.prefixSeparator)
            self.chkSuffixSeparator.setChecked(preset.suffixSeparator)
            self.chkRemoveDup.setChecked(preset.removeDuplicates)
            self.chkSortCaptions.setChecked(preset.sortCaptions)
            self.chkWhitelistGroups.setChecked(preset.whitelistGroups)
            self.tableReplace.setContent(preset.searchReplace)
            self.banWidget.setItems(preset.banned)
            self.wildcards = preset.wildcards

            self.removeAllGroups()
            for group in preset.groups:
                self.addGroup(group.name, group.color, group.exclusivity, group.combineTags, group.captions)

            self.removeAllConditionals()
            for cond in preset.conditionals:
                self.addConditional(cond)
        finally:
            self._updateEnabled = True
            self.formatsUpdated.emit()
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

    @Slot()
    def clearRules(self):
        dialog = QtWidgets.QMessageBox(self)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Question)
        dialog.setWindowTitle("Confirm Reset")
        dialog.setText(f"Clear all rules and groups?")
        dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)

        if dialog.exec() == QtWidgets.QMessageBox.StandardButton.Yes:
            preset = CaptionPreset()
            preset.removeDuplicates = False
            preset.sortCaptions = False
            self.applyPreset(preset)


    def setupProcessor(self) -> CaptionRulesProcessor:
        separator = self.txtSeparator.text()

        prefix = self.txtPrefix.toPlainText()
        if prefix and self.chkPrefixSeparator.isChecked():
            prefix += separator

        suffix = self.txtSuffix.toPlainText()
        if suffix and self.chkSuffixSeparator.isChecked():
            suffix = separator + suffix

        rulesProcessor = CaptionRulesProcessor()
        rulesProcessor.setup(prefix, suffix, separator, self.chkRemoveDup.isChecked(), self.chkSortCaptions.isChecked(), self.chkWhitelistGroups.isChecked())
        rulesProcessor.setSearchReplacePairs(self.tableReplace.getContent())
        rulesProcessor.setBannedCaptions(self.bannedCaptions)
        rulesProcessor.setCaptionGroups( (group.captionsExpandWildcards(self.wildcards), group.exclusivity, group.combineTags) for group in self.groups )
        rulesProcessor.setConditionalRules(condRule.getFilterRule() for condRule in self.conditionals)
        return rulesProcessor

    @Slot()
    def updatePreview(self):
        if not self._updateEnabled:
            return

        text = None
        srcType = self.srcSelector.type
        srcKey = self.srcSelector.name.strip()
        if srcType == FileTypeSelector.TYPE_TAGS:
            text = self.captionFile.getTags(srcKey)
        elif srcType == FileTypeSelector.TYPE_CAPTIONS:
            text = self.captionFile.getCaption(srcKey)

        if text:
            rulesProcessor = self.setupProcessor()
            text = rulesProcessor.process(text)
        else:
            text = ""

        self.txtPreview.setPlainText(text)
        self.highlight.highlight(text, self.txtSeparator.text(), self.txtPreview)


    def _confirmStart(self) -> bool:
        loadKey = f"{self.srcSelector.type}.{self.srcSelector.name.strip()}"
        ops = [
            f"Load values from .json files [{loadKey}]",
            f"Transform the {self.srcSelector.type.capitalize()} according to the selected rules"
        ]

        storeKey = f"{self.destSelector.type}.{self.destSelector.name.strip()}"
        storeText = f"Write to .json files [{storeKey}]"
        if self.chkSkipExisting.isChecked():
            storeText += " if the key doesn't exist"
        else:
            storeText = qtlib.htmlRed(storeText + " and overwrite the content!")
        ops.append(storeText)

        return BatchUtil.confirmStart("Rules", self.tab.filelist.getNumFiles(), ops, self)


    @Slot()
    def startStop(self):
        if self._task:
            if BatchUtil.confirmAbort(self):
                self._task.abort()
            return

        if not self._confirmStart():
            return

        self.btnStart.setText("Abort")

        self._task = BatchRulesTask(self.log, self.tab.filelist, self.setupProcessor())
        self._task.srcType = self.srcSelector.type
        self._task.srcKey  = self.srcSelector.name.strip()
        self._task.targetType = self.destSelector.type
        self._task.targetKey  = self.destSelector.name.strip()
        self._task.skipExisting = self.chkSkipExisting.isChecked()

        self._taskSignalHandler = BatchSignalHandler(self.statusBar, self.progressBar, self._task)
        self._taskSignalHandler.finished.connect(self.taskDone)
        Inference().queueTask(self._task)

    def taskDone(self):
        self.btnStart.setText("Start Batch Rules")
        self._task = None
        self._taskSignalHandler = None



class BatchRulesGroup(QtWidgets.QWidget):
    def __init__(self, title: str, color: str, exclusivity: MutualExclusivity, combine: bool, captions: list[str], updatePreview):
        super().__init__()
        self.color = color
        self.charFormat = QtGui.QTextCharFormat()
        self.charFormat.setForeground( qtlib.getHighlightColor(color) )

        self.captions = list(captions)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        lblTitle = QtWidgets.QLabel(f"{title}:")
        lblTitle.setMinimumWidth(Config.batchWinLegendWidth)
        qtlib.setMonospace(lblTitle, 1.0, True)
        layout.addWidget(lblTitle, 0, Qt.AlignmentFlag.AlignTop)

        flowLayout = FlowLayout(spacing=2)

        self.cboExclusive = QtWidgets.QComboBox()
        self.cboExclusive.addItem("Keep All", MutualExclusivity.Disabled)
        self.cboExclusive.addItem("Keep Last", MutualExclusivity.KeepLast)
        self.cboExclusive.addItem("Keep First", MutualExclusivity.KeepFirst)
        self.cboExclusive.addItem("Priority", MutualExclusivity.Priority)

        exclusivityIndex = self.cboExclusive.findData(exclusivity)
        self.cboExclusive.setCurrentIndex(exclusivityIndex)

        self.cboExclusive.currentIndexChanged.connect(updatePreview)
        flowLayout.addWidget(self.cboExclusive)

        self.chkCombine = QtWidgets.QCheckBox("Combine Tags")
        self.chkCombine.setChecked(combine)
        self.chkCombine.checkStateChanged.connect(updatePreview)
        flowLayout.addWidget(self.chkCombine)

        for cap in captions:
            label = QtWidgets.QLabel(cap)
            qtlib.setMonospace(label)
            label.setStyleSheet(qtlib.bubbleStylePad(color))
            flowLayout.addWidget(label)

        self.flowWidget = QtWidgets.QWidget()
        self.flowWidget.setLayout(flowLayout)
        layout.addWidget(self.flowWidget, 1)

        self.setLayout(layout)


    @property
    def exclusivity(self) -> MutualExclusivity:
        return self.cboExclusive.currentData()

    @property
    def combineTags(self) -> bool:
        return self.chkCombine.isChecked()

    def captionsExpandWildcards(self, wildcards: dict) -> list[str]:
        return [
            expandedCap
            for cap in self.captions
            for expandedCap in expandWildcards(cap, wildcards)
        ]

    @Slot()
    def updateHeight(self):
        self.flowWidget.setMinimumHeight(self.flowWidget.sizeHint().height())

    def resizeEvent(self, event) -> None:
        self.updateHeight()
        return super().resizeEvent(event)



class BatchRulesDataSource(HighlightDataSource):
    def __init__(self, batchRules: BatchRules):
        super().__init__()
        self.rules = batchRules

    def connectClearCache(self, slot: Slot):
        self.rules.formatsUpdated.connect(slot)

    def getBanned(self) -> Iterable[str]:
        return self.rules.bannedCaptions

    def getGroups(self) -> Iterable[CaptionGroupData]:
        return (
            CaptionGroupData(group.captionsExpandWildcards(self.rules.wildcards), group.charFormat, group.color)
            for group in self.rules.groups
        )



class BatchRulesTask(BatchTask):
    def __init__(self, log, filelist, rulesProcessor: CaptionRulesProcessor):
        super().__init__("rules", log, filelist)
        self.rulesProcessor = rulesProcessor

        self.srcType = ""
        self.srcKey = ""
        self.targetType = ""
        self.targetKey = ""

        self.skipExisting = False

        self._captionGetter: Callable[[CaptionFile, str], str | None]  = None
        self._captionSetter: Callable[[CaptionFile, str, str], None]   = None
        self._keyExists:     Callable[[CaptionFile], bool]             = None


    def runPrepare(self):
        match self.srcType:
            case FileTypeSelector.TYPE_TAGS:
                self._captionGetter = CaptionFile.getTags
            case FileTypeSelector.TYPE_CAPTIONS:
                self._captionGetter = CaptionFile.getCaption
            case _:
                raise ValueError("Invalid caption load type")

        match self.targetType:
            case FileTypeSelector.TYPE_TAGS:
                self._captionSetter = CaptionFile.addTags
                self._keyExists = self._hasTagsKey
            case FileTypeSelector.TYPE_CAPTIONS:
                self._captionSetter = CaptionFile.addCaption
                self._keyExists = self._hasCaptionsKey
            case _:
                raise ValueError("Invalid caption storage type")


    def runProcessFile(self, imgFile: str) -> str | None:
        captionFile = CaptionFile(imgFile)
        if captionFile.jsonExists() and not captionFile.loadFromJson():
            self.log(f"WARNING: Failed to load captions from {captionFile.jsonPath}")
            return None

        if self.skipExisting and self._keyExists(captionFile):
            return None

        text = self._captionGetter(captionFile, self.srcKey)
        if not text:
            self.log(f"WARNING: {captionFile.jsonPath} is missing value for {self.srcType}.{self.srcKey}, skipping")
            return None

        text = self.rulesProcessor.process(text)
        if not text:
            self.log(f"WARNING: Caption is empty for {imgFile}, skipping")
            return None

        self._captionSetter(captionFile, self.targetKey, text)
        captionFile.saveToJson()
        return captionFile.jsonPath


    def _hasTagsKey(self, captionFile: CaptionFile) -> bool:
        return self.targetKey in captionFile.tags

    def _hasCaptionsKey(self, captionFile: CaptionFile) -> bool:
        return self.targetKey in captionFile.captions
