import os
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Signal, Slot, QSignalBlocker, QTimer
from lib import qtlib
from lib.filelist import DataKeys
from lib.captionfile import FileTypeSelector
from ui.tab import ImgTab
from .caption_bubbles import CaptionBubbles
from .caption_filter import CaptionRulesProcessor
from .caption_generate import CaptionGenerate
from .caption_groups import CaptionGroups
from .caption_settings import CaptionSettings
from .caption_list import CaptionList


class CaptionContext(QtWidgets.QTabWidget):
    captionClicked      = Signal(str)
    separatorChanged    = Signal(str)
    controlUpdated      = Signal()
    needsRulesApplied   = Signal()
    captionGenerated    = Signal(str, str)


    def __init__(self, container, tab: ImgTab):
        super().__init__()
        self.tab = tab
        self.getSelectedCaption = container.getSelectedCaption
        self.isAutoApplyRules = container.isAutoApplyRules
        self.setAutoApplyRules = container.setAutoApplyRules

        self.settings = CaptionSettings(self)
        self.groups   = CaptionGroups(self)
        self.generate = CaptionGenerate(self)

        from .caption_focus import CaptionFocus
        self.focus = CaptionFocus(container, self)

        self.addTab(self.settings, "Rules")
        self.addTab(self.groups, "Groups")
        self.addTab(self.focus, "Focus")
        #self.addTab(QtWidgets.QWidget(), "Variables (json)")
        #self.addTab(QtWidgets.QWidget(), "Folder Overrides") # Let variables from json override settings?
        self.addTab(self.generate, "Generate")
        self.addTab(CaptionList(self), "List")



class CaptionContainer(QtWidgets.QWidget):
    def __init__(self, tab):
        super().__init__()
        self.captionCache = CaptionCache(tab.filelist)
        self._cachedRulesProcessor: CaptionRulesProcessor | None = None

        self.captionSeparator = ', '

        self.ctx = CaptionContext(self, tab)
        self._build(self.ctx)

        self.ctx.captionClicked.connect(self.toggleCaption)
        self.ctx.captionGenerated.connect(self._onCaptionGenerated)
        self.ctx.separatorChanged.connect(self._onSeparatorChanged)
        self.ctx.controlUpdated.connect(self._onControlUpdated)
        self.ctx.needsRulesApplied.connect(self.applyRulesIfAuto)

        tab.filelist.addListener(self)
        self.onFileChanged( tab.filelist.getCurrentFile() )

        self.ctx.settings._loadDefaultPreset()

    def _build(self, ctx):
        row = 0
        splitter = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(12)
        splitter.addWidget(ctx)
        splitter.setStretchFactor(row, 1)
        self._splitter = splitter

        row += 1
        self.txtRulesPreview = QtWidgets.QPlainTextEdit()
        self.txtRulesPreview.setReadOnly(True)
        qtlib.setMonospace(self.txtRulesPreview)
        qtlib.setShowWhitespace(self.txtRulesPreview)
        qtlib.setTextEditHeight(self.txtRulesPreview, 2, "min")
        self.txtRulesPreview.hide()
        splitter.addWidget(self.txtRulesPreview)
        splitter.setStretchFactor(row, 1)

        row += 1
        self.bubbles = CaptionBubbles(self.ctx.groups.getCaptionColors, showWeights=False, showRemove=True, editable=False)
        self.bubbles.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        self.bubbles.setContentsMargins(4, 4, 4, 4)
        self.bubbles.setFocusProxy(self)
        self.bubbles.remove.connect(self.removeCaption)
        self.bubbles.orderChanged.connect(lambda: self.setCaption( self.captionSeparator.join(self.bubbles.getCaptions()) ))
        self.bubbles.dropped.connect(self.appendToCaption)
        splitter.addWidget(self.bubbles)
        splitter.setStretchFactor(row, 1)

        row += 1
        self.txtCaption = DropTextEdit()
        qtlib.setMonospace(self.txtCaption, 1.2)
        self.txtCaption.textChanged.connect(self._onCaptionEdited)
        splitter.addWidget(self.txtCaption)
        splitter.setStretchFactor(row, 1)

        mainLayout = QtWidgets.QVBoxLayout()
        mainLayout.setContentsMargins(0, 0, 0, 0)
        mainLayout.addWidget(splitter)
        mainLayout.addWidget(self._buildBottomRow())
        self.setLayout(mainLayout)

        self._onDestLockChanged(self.btnDestLocked.isChecked())

    def _buildBottomRow(self):
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(4, 0, 4, 2)

        col = 0
        btnMenu = QtWidgets.QPushButton("☰")
        btnMenu.setFixedWidth(40)
        btnMenu.setMenu(self._buildMenu())
        layout.addWidget(btnMenu, 0, col)
        layout.setColumnStretch(col, 0)

        col += 1
        self.btnApplyRules = QtWidgets.QPushButton("Apply Rules")
        self.btnApplyRules.setMinimumWidth(120)
        self.btnApplyRules.clicked.connect(self.applyRules)
        layout.addWidget(self.btnApplyRules, 0, col)
        layout.setColumnStretch(col, 0)

        col += 1
        self.chkAutoApply = QtWidgets.QCheckBox("Auto Apply")
        layout.addWidget(self.chkAutoApply, 0, col)
        layout.setColumnStretch(col, 0)

        col += 1
        layout.setColumnStretch(col, 1)

        col += 1
        self.btnReset = qtlib.SaveButton("Reload From:")
        self.btnReset.setFixedWidth(100)
        self.btnReset.clicked.connect(self.resetCaption)
        layout.addWidget(self.btnReset, 0, col)
        layout.setColumnStretch(col, 0)

        col += 1
        self.srcSelector = FileTypeSelector()
        self.srcSelector.type = FileTypeSelector.TYPE_TAGS
        self.srcSelector.setTextFieldFixedWidth(140)
        self.srcSelector.fileTypeUpdated.connect(self._onSourceChanged)
        layout.addLayout(self.srcSelector, 0, col)
        layout.setColumnStretch(col, 0)

        col += 1
        layout.addWidget(qtlib.VerticalSeparator(), 0, col)
        layout.setColumnStretch(col, 0)

        col += 1
        self.btnDestLocked = qtlib.ToggleButton("🔒")
        self.btnDestLocked.setToolTip("Sync destination to source")
        self.btnDestLocked.setChecked(True)
        qtlib.setMonospace(self.btnDestLocked, 1.2)
        self.btnDestLocked.setFixedWidth(26)
        self.btnDestLocked.toggled.connect(self._onDestLockChanged)
        layout.addWidget(self.btnDestLocked, 0, col)

        col += 1
        self.btnSave = qtlib.SaveButton("Save To:")
        self.btnSave.setFixedWidth(100)
        self.btnSave.clicked.connect(self.saveCaption)
        layout.addWidget(self.btnSave, 0, col)
        layout.setColumnStretch(col, 0)

        col += 1
        self.destSelector = FileTypeSelector()
        self.destSelector.type = FileTypeSelector.TYPE_TAGS
        self.destSelector.setTextFieldFixedWidth(140)
        layout.addLayout(self.destSelector, 0, col)
        layout.setColumnStretch(col, 0)

        col += 1
        self.chkSkipOnSave = qtlib.ToggleButton("⏭️")
        self.chkSkipOnSave.setToolTip("Skip to next image after saving (no looping)")
        self.chkSkipOnSave.setChecked(False)
        self.chkSkipOnSave.setFixedWidth(26)
        layout.addWidget(self.chkSkipOnSave, 0, col)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        return widget

    def _buildMenu(self):
        menu = QtWidgets.QMenu(self)
        menu.addSection("Rules and Groups")

        actSaveDefaults = menu.addAction("Save as Defaults...")
        actSaveDefaults.triggered.connect(self.ctx.settings.saveAsDefaultPreset)

        actLoadDefaults = menu.addAction("Reset to Defaults...")
        actLoadDefaults.triggered.connect(self.ctx.settings.loadDefaultPreset)

        actClear = menu.addAction("Clear...")
        actClear.triggered.connect(self.ctx.settings.clearPreset)

        menu.addSeparator()

        actSave = menu.addAction("Save As...")
        actSave.triggered.connect(self.ctx.settings.savePreset)

        actLoad = menu.addAction("Load from File...")
        actLoad.triggered.connect(self.ctx.settings.loadPreset)

        menu.addSeparator()

        actPreview = menu.addAction("Show refined preview")
        actPreview.setCheckable(True)
        actPreview.toggled.connect(self._onPreviewToggled)

        return menu


    def getCaption(self) -> str:
        return self.txtCaption.toPlainText()

    def setCaption(self, text):
        self.txtCaption.setPlainText(text)
        self.txtCaption.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    @Slot()
    def _onCaptionEdited(self):
        text = self.txtCaption.toPlainText()
        self._highlight(text, self.txtCaption)
        self.bubbles.setText(text)
        self.updateSelectionState(text)
        self._updatePreview(text)

        self.captionCache.put(text)
        self.captionCache.setState(DataKeys.IconStates.Changed)
        self.btnSave.setChanged(True)

    @Slot()
    def _onSourceChanged(self):
        self.btnReset.setChanged(True)

        if self.btnDestLocked.isChecked():
            self._syncDestSelector()

    @Slot()
    def _onDestLockChanged(self, checked: bool):
        if checked:
            self._syncDestSelector()
            self.btnDestLocked.setText("🔒")
        else:
            self.destSelector.setEnabled(True)
            self.btnDestLocked.setText("🔓")

    def _syncDestSelector(self):
        self.destSelector.type = self.srcSelector.type
        self.destSelector.name = self.srcSelector.name
        self.destSelector.setEnabled(False)


    @Slot()
    def _onPreviewToggled(self, enabled: bool):
        self.txtRulesPreview.setVisible(enabled)
        if enabled:
            self._updatePreview(self.getCaption())

            splitterSizes = self._splitter.sizes()
            idx = self._splitter.indexOf(self.txtRulesPreview)
            splitterSizes[idx] = self.txtRulesPreview.minimumHeight()
            self._splitter.setSizes(splitterSizes)

    def _updatePreview(self, text: str, invalidateRules=False):
        if not self.txtRulesPreview.isVisible():
            return

        if invalidateRules or self._cachedRulesProcessor is None:
            self._cachedRulesProcessor = self.createRulesProcessor()

        textNew = self._cachedRulesProcessor.process(text)
        self.txtRulesPreview.setPlainText(textNew)
        self._highlight(textNew, self.txtRulesPreview)


    def _highlight(self, text: str, txtWidget: QtWidgets.QPlainTextEdit):
        formats = self.ctx.groups.getCaptionCharFormats()
        with QSignalBlocker(txtWidget):
            cursor = txtWidget.textCursor()
            cursor.setPosition(0)
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.End, QtGui.QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(QtGui.QTextCharFormat())

            start = 0
            sep = self.captionSeparator.strip()
            for caption in text.split(sep):
                if format := formats.get(caption.strip()):
                    cursor.setPosition(start)
                    cursor.setPosition(start+len(caption), QtGui.QTextCursor.MoveMode.KeepAnchor)
                    cursor.setCharFormat(format)
                start += len(caption) + len(sep)


    def getSelectedCaption(self) -> str:
        text = self.txtCaption.toPlainText()
        splitSeparator = self.captionSeparator.strip()
        lenSplitSeparator = len(splitSeparator)
        cursorPos = self.txtCaption.textCursor().position()

        accumulatedLength = 0
        for part in text.split(splitSeparator):
            accumulatedLength += len(part) + lenSplitSeparator
            if cursorPos < accumulatedLength:
                return part.strip()

        return ""


    def isAutoApplyRules(self) -> bool:
        return self.chkAutoApply.isChecked()

    def setAutoApplyRules(self, enabled: bool):
        self.chkAutoApply.setChecked(enabled)


    @Slot()
    def _onControlUpdated(self):
        text = self.txtCaption.toPlainText()
        self._highlight(text, self.txtCaption)
        self.bubbles.updateBubbles()
        self.updateSelectionState(text)
        self._updatePreview(text, invalidateRules=True)

    def updateSelectionState(self, captionText: str):
        separator = self.captionSeparator.strip()
        captionSet = { cap for c in captionText.split(separator) if (cap := c.strip()) }
        self.ctx.groups.updateSelectedState(captionSet)
        self.ctx.focus.updateSelectionState(captionSet)


    @Slot()
    def appendToCaption(self, text: str):
        caption = self.txtCaption.toPlainText()
        if caption:
            caption += self.captionSeparator
        caption += text
        self.setCaption(caption)

        if self.isAutoApplyRules():
            self.applyRules()

    @Slot()
    def toggleCaption(self, caption: str):
        caption = caption.strip()
        captions = []
        removed = False

        text = self.txtCaption.toPlainText()
        if text:
            for current in text.split(self.captionSeparator.strip()):
                current = current.strip()
                if caption == current:
                    removed = True
                else:
                    captions.append(current)

        if not removed:
            captions.append(caption)

        self.setCaption( self.captionSeparator.join(captions) )
        if self.isAutoApplyRules():
            self.applyRules()

    @Slot()
    def removeCaption(self, index: int):
        text = self.txtCaption.toPlainText()
        splitSeparator = self.captionSeparator.strip()
        captions = [c.strip() for c in text.split(splitSeparator)]
        del captions[index]
        self.setCaption( self.captionSeparator.join(captions) )


    @Slot()
    def _onCaptionGenerated(self, text, mode):
        caption = self.txtCaption.toPlainText()
        if caption:
            if mode == "Append":
                caption += os.linesep + text
            elif mode == "Prepend":
                caption = text + os.linesep + caption
            elif mode == "Replace":
                caption = text
        else:
            caption = text

        self.setCaption(caption)
        if self.isAutoApplyRules():
            self.applyRules()


    @Slot()
    def applyRulesIfAuto(self):
        if self.isAutoApplyRules():
            self.applyRules()

    @Slot()
    def applyRules(self):
        rulesProcessor = self.createRulesProcessor()
        text = self.txtCaption.toPlainText()
        textNew = rulesProcessor.process(text)

        # Only set when text has changed to prevent save button turning red
        if textNew != text:
            self.setCaption(textNew)

    def createRulesProcessor(self):
        removeDup = self.ctx.settings.isRemoveDuplicates
        sortCaptions = self.ctx.settings.isSortCaptions

        rulesProcessor = CaptionRulesProcessor()
        rulesProcessor.setup(self.ctx.settings.prefix, self.ctx.settings.suffix, self.captionSeparator, removeDup, sortCaptions)
        rulesProcessor.setSearchReplacePairs(self.ctx.settings.searchReplacePairs)
        rulesProcessor.setBannedCaptions(self.ctx.settings.bannedCaptions)
        rulesProcessor.setCaptionGroups( (group.captions, group.exclusivity, group.combineTags) for group in self.ctx.groups.groups )
        return rulesProcessor


    @Slot()
    def saveCaption(self):
        # Skip to next file when saving succeds and skip-on-save is enabled. Don't loop.
        filelist = self.ctx.tab.filelist
        if self.saveCaptionNoSkip() and self.chkSkipOnSave.isChecked() and not filelist.isLastFile():
            filelist.setNextFile()

    def saveCaptionNoSkip(self) -> bool:
        text = self.txtCaption.toPlainText()
        currentFile = self.ctx.tab.filelist.getCurrentFile()

        if self.destSelector.saveCaption(currentFile, text):
            self.captionCache.remove()
            self.captionCache.setState(DataKeys.IconStates.Saved)
            self.btnSave.setChanged(False)
            return True

        return False


    def loadCaption(self):
        # Use cached caption if it exists in dictionary
        cachedCaption = self.captionCache.get()
        if cachedCaption:
            self.setCaption(cachedCaption)
            self.captionCache.setState(DataKeys.IconStates.Changed)
        else:
            self.resetCaption()

    @Slot()
    def resetCaption(self):
        currentFile = self.ctx.tab.filelist.getCurrentFile()
        text = self.srcSelector.loadCaption(currentFile)

        if text:
            self.setCaption(text)
            self.captionCache.setState(DataKeys.IconStates.Exists)
        else:
            self.setCaption("")
            self.captionCache.setState(None)

        # When setting the text, _onCaptionEdited() will make a cache entry and turn the save button red. So we revert that here.
        self.captionCache.remove()
        self.btnSave.setChanged(False)
        self.btnReset.setChanged(False)


    @Slot()
    def _onSeparatorChanged(self, separator):
        self.captionSeparator = separator
        self.bubbles.separator = separator
        self._onControlUpdated()


    def onFileChanged(self, currentFile):
        self.loadCaption()
        if self.isAutoApplyRules():
            self.applyRules()

        self.ctx.generate.onFileChanged(currentFile)

    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)


    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.matches(QtGui.QKeySequence.StandardKey.Save):
            self.saveCaption()
            event.accept()
            return

        event.ignore()
        return super().keyPressEvent(event)



class CaptionCache:
    def __init__(self, filelist):
        self.filelist = filelist

    def get(self):
        file = self.filelist.getCurrentFile()
        return self.filelist.getData(file, DataKeys.Caption)

    def put(self, text):
        file = self.filelist.getCurrentFile()
        self.filelist.setData(file, DataKeys.Caption, text)

    def remove(self):
        file = self.filelist.getCurrentFile()
        self.filelist.removeData(file, DataKeys.Caption)

    def setState(self, state: DataKeys.IconStates | None):
        file = self.filelist.getCurrentFile()
        if state:
            self.filelist.setData(file, DataKeys.CaptionState, state)
        else:
            self.filelist.removeData(file, DataKeys.CaptionState)



class DropTextEdit(QtWidgets.QPlainTextEdit):
    def __init__(self):
        super().__init__()

    def dropEvent(self, event: QtGui.QDropEvent):
        with QSignalBlocker(self):
            super().dropEvent(event)

        # Don't remove buttons from CaptionControlGroup
        event.setDropAction(Qt.DropAction.CopyAction)

        # Postpone updates when dropping so they don't interfere with ongoing drag operations in ReorderWidget.
        # But don't postpone normal updates to prevent flickering.
        QTimer.singleShot(0, self.textChanged.emit)
