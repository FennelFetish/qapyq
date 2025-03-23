from __future__ import annotations
import os
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Signal, Slot, QSignalBlocker, QTimer
from lib import qtlib
from lib.filelist import DataKeys
from lib.captionfile import FileTypeSelector
from lib.util import stripCountPadding
from ui.tab import ImgTab
from config import Config
from .caption_menu import CaptionMenu, RulesLoadMode
from .caption_bubbles import CaptionBubbles
from .caption_filter import CaptionRulesProcessor
from .caption_settings import CaptionSettings
from .caption_groups import CaptionGroups
from .caption_conditionals import CaptionConditionals
from .caption_generate import CaptionGenerate
from .caption_list import CaptionList


class CaptionContext(QtWidgets.QTabWidget):
    captionEdited       = Signal(str)
    separatorChanged    = Signal(str)
    controlUpdated      = Signal()
    needsRulesApplied   = Signal()
    captionGenerated    = Signal(str, str)


    def __init__(self, container: CaptionContainer, tab: ImgTab):
        super().__init__()
        self.container = container
        self.tab = tab

        self._cachedRulesProcessor: CaptionRulesProcessor | None = None
        self.controlUpdated.connect(self._invalidateRulesProcessor) # First Slot for controlUpdated

        self.settings     = CaptionSettings(self)
        self.groups       = CaptionGroups(self)
        self.conditionals = CaptionConditionals(self)
        self.generate     = CaptionGenerate(self)

        from .caption_focus import CaptionFocus
        self.focus = CaptionFocus(container, self)

        self.addTab(self.settings, "Rules")
        self.addTab(self.groups, "Groups")
        self.addTab(self.conditionals, "Conditionals")
        self.addTab(self.focus, "Focus")
        #self.addTab(QtWidgets.QWidget(), "Folder Overrides") # Let variables from json override settings?
        self.addTab(self.generate, "Generate")
        self.addTab(CaptionList(self), "List")

        self._activeWidget = None
        self.currentChanged.connect(self.onTabChanged)
        self.onTabChanged(0)

    @Slot()
    def onTabChanged(self, index: int):
        if self._activeWidget:
            self._activeWidget.onTabDisabled()

        if widget := self.widget(index):
            self._activeWidget = widget
            widget.onTabEnabled()

    @Slot()
    def _invalidateRulesProcessor(self):
        self._cachedRulesProcessor = None

    def rulesProcessor(self) -> CaptionRulesProcessor:
        if not self._cachedRulesProcessor:
            self._cachedRulesProcessor = self.container.createRulesProcessor()
        return self._cachedRulesProcessor



class CaptionContainer(QtWidgets.QWidget):
    def __init__(self, tab):
        super().__init__()

        self.captionCache = CaptionCache(tab.filelist)
        self.captionSeparator = ', '

        self.ctx = CaptionContext(self, tab)
        self._menu = CaptionMenu(self, self.ctx)
        self._build(self.ctx)

        self.ctx.captionGenerated.connect(self._onCaptionGenerated)
        self.ctx.separatorChanged.connect(self._onSeparatorChanged)
        self.ctx.controlUpdated.connect(self._onControlUpdated)
        self.ctx.needsRulesApplied.connect(self.applyRulesIfAuto)

        self._menu.previewToggled.connect(self._onPreviewToggled)

        tab.filelist.addListener(self)
        self.onFileChanged( tab.filelist.getCurrentFile() )

        self._loadRules()
        QTimer.singleShot(1, self._forceUpdateGroupSelection) # Workaround for BUG

        if Config.captionShowPreview:
            QTimer.singleShot(1, lambda: self._onPreviewToggled(True))


    def _build(self, ctx):
        row = 0
        splitter = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(12)
        splitter.addWidget(ctx)
        splitter.setStretchFactor(row, 1)
        self._splitter = splitter

        row += 1
        self.txtRulesPreview = HoverTextEdit(self)
        self.txtRulesPreview.setReadOnly(True)
        qtlib.setMonospace(self.txtRulesPreview, 1.1)
        qtlib.setShowWhitespace(self.txtRulesPreview)
        qtlib.setTextEditHeight(self.txtRulesPreview, 2, "min")
        self.txtRulesPreview.hoverTextChanged.connect(lambda: self.ctx.controlUpdated.emit())
        self.txtRulesPreview.hide()
        splitter.addWidget(self.txtRulesPreview)
        splitter.setStretchFactor(row, 1)

        row += 1
        self.bubbles = CaptionBubbles(self.ctx, showWeights=False, showRemove=True, editable=False)
        self.bubbles.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        self.bubbles.setContentsMargins(4, 4, 4, 4)
        self.bubbles.setFocusProxy(self)
        self.bubbles.remove.connect(self.removeCaption)
        self.bubbles.orderChanged.connect(lambda: self.setCaption( self.captionSeparator.join(self.bubbles.getCaptions()) ))
        self.bubbles.dropped.connect(self.appendToCaption)
        self.bubbles.clicked.connect(self.selectCaption)
        splitter.addWidget(self.bubbles)
        splitter.setStretchFactor(row, 1)

        row += 1
        self.txtCaption = CaptionTextEdit()
        qtlib.setMonospace(self.txtCaption, 1.2)
        self.txtCaption.textChanged.connect(self._onCaptionEdited)
        self.txtCaption.moveSelectionPressed.connect(self.moveCaptionSelection)
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
        btnMenu.setMenu(self._menu)
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


    def _loadRules(self):
        try:
            loadMode = RulesLoadMode(Config.captionRulesLoadMode)
        except ValueError:
            print(f"WARNING: Invalid caption rules load mode: {Config.captionRulesLoadMode}")
            loadMode = RulesLoadMode.Empty

        match loadMode:
            case RulesLoadMode.Defaults:
                self.ctx.settings._loadDefaultPreset()
            case RulesLoadMode.Previous:
                # When the caption window is not open, this _loadRules method is called only upon opening it for the first time for an ImgTab.
                # Then, prevTab will be the current tab and CaptionContainer is None.
                # TODO: Add another way of referencing the previous tab without holding an actual reference that keeps the tab in memory?
                prevTab = self.ctx.tab.mainWindow.previousTab
                if not prevTab:
                    return

                prevCaptionWin: CaptionContainer | None = prevTab.getWindowContent("caption")
                if not prevCaptionWin:
                    self.ctx.settings._loadDefaultPreset()
                    return

                prevPreset = prevCaptionWin.ctx.settings.getPreset()
                self.ctx.settings.applyPreset(prevPreset)


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

        self.ctx.captionEdited.emit(text)

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
        Config.captionShowPreview = enabled
        if enabled:
            self._updatePreview(self.getCaption())

            splitterSizes = self._splitter.sizes()
            idx = self._splitter.indexOf(self.txtRulesPreview)
            splitterSizes[idx] = self.txtRulesPreview.minimumHeight()
            self._splitter.setSizes(splitterSizes)

    def _updatePreview(self, text: str):
        if not self.txtRulesPreview.isVisible():
            return

        textNew = self.ctx.rulesProcessor().process(text)
        self.txtRulesPreview.setPlainText(textNew)
        self._highlight(textNew, self.txtRulesPreview)


    def _highlight(self, text: str, txtWidget: QtWidgets.QPlainTextEdit):
        formats = self.ctx.groups.getCaptionCharFormats()
        wordFormatMap = self.ctx.groups.getCaptionCombineFormats()

        with QSignalBlocker(txtWidget):
            cursor = txtWidget.textCursor()
            cursor.setPosition(0)
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.End, QtGui.QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(QtGui.QTextCharFormat())

            start = 0
            sep = self.captionSeparator.strip()
            for caption in text.split(sep):
                captionStrip, padLeft, padRight = stripCountPadding(caption)
                start += padLeft

                if format := formats.get(captionStrip):
                    self._highlightPart(cursor, format, start, len(captionStrip))
                elif self.isHovered(captionStrip):
                    # Char format for colored captions is made in CaptionColorSet
                    format = QtGui.QTextCharFormat()
                    format.setFontUnderline(True)
                    self._highlightPart(cursor, format, start, len(captionStrip))

                # Try highlighting combined words
                else:
                    captionWords = captionStrip.split(" ")
                    lastWord = captionWords[-1]
                    pos = start

                    if (combineFormat := wordFormatMap.get(lastWord)) and (groupFormat := combineFormat.getGroupFormat(captionWords)):
                        for word in captionWords[:-1]:
                            if word in groupFormat.words:
                                self._highlightPart(cursor, groupFormat.format, pos, len(word))
                            pos += len(word) + 1

                        self._highlightPart(cursor, groupFormat.format, pos, len(lastWord))

                    # if (combineFormat := wordFormatMap.get(lastWord)):
                    #     wordSet, wordFormat = combineFormat.getFormat(captionWords)
                    #     if wordSet and wordFormat:
                    #         lastWordFormat = None
                    #         for word in captionWords[:-1]:
                    #             if word in wordSet:
                    #                 self._highlightPart(cursor, wordFormat, pos, len(word))
                    #                 lastWordFormat = wordFormat
                    #             pos += len(word) + 1

                    #         if lastWordFormat:
                    #             self._highlightPart(cursor, lastWordFormat, pos, len(lastWord))

                    # if (combineFormat := wordFormatMap.get(lastWord)) and combineFormat.hasSubset(captionWords):
                    #     lastWordFormat = None
                    #     for word in captionWords[:-1]:
                    #         if wordFormat := combineFormat.wordFormats.get(word):
                    #             self._highlightPart(cursor, wordFormat, pos, len(word))
                    #             lastWordFormat = wordFormat
                    #         pos += len(word) + 1

                    #     if lastWordFormat:
                    #         self._highlightPart(cursor, lastWordFormat, pos, len(lastWord))

                start += len(captionStrip) + padRight + len(sep)

    def _highlightPart(self, cursor: QtGui.QTextCursor, format: QtGui.QTextCharFormat, start: int, length: int):
        cursor.setPosition(start)
        cursor.setPosition(start+length, QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(format)


    def getSelectedCaption(self) -> str:
        text = self.txtCaption.toPlainText()
        cursorPos = self.txtCaption.textCursor().position()
        return self._getSelectedCaption(text, cursorPos)[0]

    def _getSelectedCaption(self, text: str, cursorPos: int) -> tuple[str, int]:
        sepStrip = self.captionSeparator.strip()
        accumulatedLength = 0
        for i, caption in enumerate(text.split(sepStrip)):
            accumulatedLength += len(caption) + len(sepStrip)
            if cursorPos < accumulatedLength:
                return caption.strip(), i

        return "", -1

    @Slot()
    def selectCaption(self, index: int):
        text = self.txtCaption.toPlainText()
        sepStrip, sepSpaceL, sepSpaceR = stripCountPadding(self.captionSeparator)

        accumulatedLength = 0
        splitCaptions = text.split(sepStrip)
        for i, caption in enumerate(splitCaptions):
            if i != index:
                accumulatedLength += len(caption) + len(sepStrip)
                continue

            capStrip, capSpaceL, capSpaceR = stripCountPadding(caption)
            offsetL = min(capSpaceL, sepSpaceR) if i > 0 else 0
            offsetR = min(capSpaceR, sepSpaceL) if i < len(splitCaptions)-1 else 0

            start = accumulatedLength + offsetL
            end   = accumulatedLength + len(caption) - offsetR

            cursor = self.txtCaption.textCursor()
            cursor.setPosition(start, QtGui.QTextCursor.MoveMode.MoveAnchor)
            cursor.setPosition(end, QtGui.QTextCursor.MoveMode.KeepAnchor)
            self.txtCaption.setTextCursor(cursor)

    @Slot()
    def moveCaptionSelection(self, offset: int, offsetLine: int):
        text = self.txtCaption.toPlainText()

        cursor = self.txtCaption.textCursor()
        if offsetLine != 0:
            moveLineDir = QtGui.QTextCursor.MoveOperation.Up if offsetLine < 0 else QtGui.QTextCursor.MoveOperation.Down
            cursor.movePosition(moveLineDir, QtGui.QTextCursor.MoveMode.MoveAnchor)

        index = self._getSelectedCaption(text, cursor.position())[1]
        index = max(0, index+offset)
        self.selectCaption(index)


    def getHoveredCaption(self) -> str:
        return self.txtRulesPreview.hoverText if self.txtRulesPreview.isVisible() else ""

    def isHovered(self, text: str) -> bool:
        return self.txtRulesPreview.isVisible() and self.txtRulesPreview.isHovered(text)


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
        self._updatePreview(text)

    def updateSelectionState(self, captionText: str, force=False):
        separator = self.captionSeparator.strip()
        captions = [ cap for c in captionText.split(separator) if (cap := c.strip()) ]
        captionSet = set(captions)

        self.ctx.conditionals.updateState(captions)
        self.ctx.groups.updateSelectedState(captionSet, force)
        self.ctx.focus.updateSelectionState(captionSet)

    @Slot()
    def _forceUpdateGroupSelection(self):
        # BUG: The stylesheet for GroupButtons is not correctly applied when opening a new tab,
        # possibly because they are not visible during tab creation?
        # Since GroupButtons only re-apply the stylesheet when the color changes for performance reasons, they are not enabled correctly.
        # As a workaround, force a color update after creating a new tab.
        text = self.txtCaption.toPlainText()
        self.updateSelectionState(text, force=True)


    @Slot()
    def appendToCaption(self, text: str):
        caption = self.txtCaption.toPlainText()
        if caption:
            caption += self.captionSeparator
        caption += text
        self.setCaption(caption)

        if self.isAutoApplyRules():
            self.applyRules()

    def toggleCaption(self, caption: str, removeWords: set[str]|None):
        caption = caption.strip()
        captions = []
        removed = False

        # lastWord = ""
        # if removeWords:
        #     print(f"removeWords: {removeWords}")
        #     lastWord = caption.rsplit(" ", 1)[-1]

        text = self.txtCaption.toPlainText()
        if text:
            for current in text.split(self.captionSeparator.strip()):
                current = current.strip()
                if caption == current:
                    removed = True
                # elif removeWords and current.endswith(lastWord):
                #     # All removeWords need to exist in 'current'
                #     # TODO: Still buggy! Removing from other groups when removeWords has one word.
                #     currentWords = [word for word in current.split(" ")]
                #     if not removeWords.issubset(currentWords):
                #         captions.append(current)
                #         continue

                #     current = " ".join(word for word in currentWords if word not in removeWords)
                #     if current != lastWord:
                #         captions.append(current)
                #     removed = True
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
        # FIXME: The preview is made after applying the rules to the text. This can change the sorting of combined tags.
        rulesProcessor = self.createRulesProcessor()
        text = self.txtCaption.toPlainText()
        textNew = rulesProcessor.process(text)

        # Only set when text has changed to prevent save button turning red
        if textNew != text:
            self.setCaption(textNew)

    def createRulesProcessor(self) -> CaptionRulesProcessor:
        removeDup = self.ctx.settings.isRemoveDuplicates
        sortCaptions = self.ctx.settings.isSortCaptions

        rulesProcessor = CaptionRulesProcessor()
        rulesProcessor.setup(self.ctx.settings.prefix, self.ctx.settings.suffix, self.captionSeparator, removeDup, sortCaptions)
        rulesProcessor.setSearchReplacePairs(self.ctx.settings.searchReplacePairs)
        rulesProcessor.setBannedCaptions(self.ctx.settings.bannedCaptions)
        rulesProcessor.setCaptionGroups( (group.captionsExpandWildcards, group.exclusivity, group.combineTags) for group in self.ctx.groups.groups )
        rulesProcessor.setConditionalRules(self.ctx.conditionals.getFilterRules())
        return rulesProcessor


    @Slot()
    def saveCaption(self):
        # Skip to next file when saving succeeds and skip-on-save is enabled. Don't loop.
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



class CaptionTextEdit(QtWidgets.QPlainTextEdit):
    moveSelectionPressed = Signal(int, int)

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

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            move = None
            match event.key():
                case Qt.Key.Key_Alt:    move = (0, 0)
                case Qt.Key.Key_Left:   move = (-1, 0)
                case Qt.Key.Key_Right:  move = (1, 0)
                case Qt.Key.Key_Up:     move = (0, -1)
                case Qt.Key.Key_Down:   move = (0, 1)

            if move is not None:
                event.accept()
                self.moveSelectionPressed.emit(move[0], move[1])
                return

        super().keyPressEvent(event)



class HoverTextEdit(QtWidgets.QPlainTextEdit):
    hoverTextChanged = Signal(str)

    def __init__(self, container: CaptionContainer):
        super().__init__()
        self.setMouseTracking(True)
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)

        self.container = container
        self.hoverText = ""
        self._hoverWords: set[str] = set()


    def isHovered(self, text: str) -> bool:
        return bool(text) and self._hoverWords.issuperset(text.split(" "))


    def setHoverText(self, text: str):
        if self.hoverText == text:
            return

        self._hoverWords.clear()
        if text:
            self._hoverWords.update(text.split(" "))

        self.hoverText = text
        self.hoverTextChanged.emit(text)


    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

        text = self.toPlainText()
        cursorPos = self.cursorForPosition(event.pos()).position()

        newHoverText = ""
        if 0 < cursorPos < len(text):
            newHoverText = self.container._getSelectedCaption(text, cursorPos)[0]
        self.setHoverText(newHoverText)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.setHoverText("")
