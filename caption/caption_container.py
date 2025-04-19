from __future__ import annotations
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from lib import qtlib
from lib.filelist import FileList, DataKeys
from lib.captionfile import FileTypeSelector
from config import Config
from .caption_context import CaptionContext
from .caption_menu import CaptionMenu, RulesLoadMode
from .caption_bubbles import CaptionBubbles
from .caption_text import CaptionTextEdit
from .caption_highlight import HighlightState
from .caption_multi_edit import CaptionMultiEdit


class CaptionContainer(QtWidgets.QWidget):
    def __init__(self, tab):
        super().__init__()

        self.filelist: FileList = tab.filelist
        self.filelist.addListener(self)
        self.filelist.addSelectionListener(self)

        self.captionCache = CaptionCache(self.filelist)
        self.captionSeparator = ', '

        self.ctx = CaptionContext(self, tab)

        self.txtCaption = self.ctx.text
        self.txtCaption.textChanged.connect(self._onCaptionEdited)
        self.txtCaption.cursorPositionChanged.connect(self._updateTextCursorHighlight)
        self.txtCaption.focusChanged.connect(self._updateTextCursorHighlight)
        self._setEditedOnChange = True

        self.highlightState = HighlightState()
        self.txtCaption.captionReplaced.connect(self.highlightState.clearState)
        self.ctx.controlUpdated.connect(self.highlightState.clearState)

        self.multiEdit = CaptionMultiEdit(self.filelist)

        self._menu = CaptionMenu(self, self.ctx)
        self._build(self.ctx)

        self.ctx.separatorChanged.connect(self._onSeparatorChanged)
        self.ctx.controlUpdated.connect(self._onControlUpdated)
        self.ctx.needsRulesApplied.connect(self.applyRulesIfAuto)

        self._menu.previewToggled.connect(self._onPreviewToggled)

        self._loadRules()

        # Initialize to Multi-Edit mode if required
        if self.filelist.selectedFiles:
            self.onFileSelectionChanged(self.filelist.selectedFiles)

        # Initialize caption text and generate tab
        self.onFileChanged(self.filelist.getCurrentFile())

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
        self.bubbles.orderChanged.connect(self._onBubbleOrderChanged)
        self.bubbles.remove.connect(self.txtCaption.removeCaption)
        self.bubbles.dropped.connect(self.txtCaption.appendToCaption)
        self.bubbles.clicked.connect(self.txtCaption.selectCaption)
        self.bubbles.doubleClicked.connect(self._multiEditEnsureFullPresence)
        self.bubbles.hovered.connect(self._updateBubbleHighlight)
        splitter.addWidget(self.bubbles)
        splitter.setStretchFactor(row, 1)

        row += 1
        qtlib.setMonospace(self.txtCaption, 1.2)
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
        self.btnMultiEdit = RightClickToggleButton("")
        self.btnMultiEdit.setToolTip(
            "Shows number of selected images. Left-click to toggle between:\n"  \
            "- Multi-Edit mode with combined captions of all selected images.\n"  \
            "- Single-Edit mode with caption of the currently displayed image only.\n"  \
            "Right-click to clear image selection."
        )
        self.btnMultiEdit.setFixedWidth(30)
        self.btnMultiEdit.hide()
        self.btnMultiEdit.clicked.connect(self._multiEditToggle)
        self.btnMultiEdit.rightClicked.connect(lambda: self.filelist.clearSelection())
        layout.addWidget(self.btnMultiEdit, 0, col)

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


    def _setCaptionUnedited(self, text: str, edited=False):
        try:
            self._setEditedOnChange = edited
            self.txtCaption.setCaption(text) # Will callback self._onCaptionEdited()
        finally:
            self._setEditedOnChange = True

    @Slot()
    def _onCaptionEdited(self):
        text = self.txtCaption.getCaption()

        if self._setEditedOnChange:
            if self.multiEdit.active:
                self.multiEdit.onCaptionEdited(text)
            else:
                self.captionCache.put(text)
                self.captionCache.setState(DataKeys.IconStates.Changed)

            self.btnSave.setChanged(True)

        self.ctx.highlight.highlight(text, self.captionSeparator, self.txtCaption, self.highlightState)
        self.bubbles.setText(text)
        self.updateSelectionState(text)
        self._updatePreview(text)
        self._updateTextCursorHighlight()

        self.ctx.captionEdited.emit(text)

    @Slot()
    def _onBubbleOrderChanged(self):
        text = self.captionSeparator.join(self.bubbles.getCaptions())
        self.txtCaption.setCaption(text)

    @Slot()
    def _onControlUpdated(self):
        text = self.txtCaption.getCaption()
        self.ctx.highlight.highlight(text, self.captionSeparator, self.txtCaption, self.highlightState)
        self.bubbles.updateBubbles()
        self.updateSelectionState(text)
        self._updatePreview(text)

    def updateSelectionState(self, captionText: str, force=False):
        separator = self.captionSeparator.strip()
        captions = [ cap for c in captionText.split(separator) if (cap := c.strip()) ]

        self.ctx.conditionals.updateState(captions)
        self.ctx.groups.updateSelectedState(captions, force)
        self.ctx.focus.updateSelectionState(set(captions))

    @Slot()
    def _forceUpdateGroupSelection(self):
        # BUG: The stylesheet for GroupButtons is not correctly applied when opening a new tab,
        # possibly because they are not visible during tab creation?
        # Since GroupButtons only re-apply the stylesheet when the color changes for performance reasons, they are not enabled correctly.
        # As a workaround, force a color update after creating a new tab.
        text = self.txtCaption.getCaption()
        self.updateSelectionState(text, force=True)


    @Slot()
    def _onSeparatorChanged(self, separator: str):
        self.captionSeparator = separator
        self.bubbles.separator = separator

        if self.multiEdit.active:
            edited = self.multiEdit.isEdited
            loadFunc = self._multiEditLoadApplyRules if self.isAutoApplyRules() else self._loadCaption
            text = self.multiEdit.changeSeparator(separator, loadFunc)
            self._setCaptionUnedited(text, edited)
        else:
            self.multiEdit.separator = separator

        self._onControlUpdated()


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
            self._updatePreview(self.txtCaption.getCaption())

            splitterSizes = self._splitter.sizes()
            idx = self._splitter.indexOf(self.txtRulesPreview)
            splitterSizes[idx] = self.txtRulesPreview.minimumHeight()
            self._splitter.setSizes(splitterSizes)

    def _updatePreview(self, text: str):
        if not self.txtRulesPreview.isVisible():
            return

        textNew = self.ctx.rulesProcessor().process(text)
        self.txtRulesPreview.setPlainText(textNew)
        self.ctx.highlight.highlight(textNew, self.captionSeparator, self.txtRulesPreview)


    def getHoveredCaption(self) -> str:
        return self.txtRulesPreview.hoverText if self.txtRulesPreview.isVisible() else ""

    def isHovered(self, text: str) -> bool:
        return self.txtRulesPreview.isVisible() and self.txtRulesPreview.isHovered(text)


    def isAutoApplyRules(self) -> bool:
        return self.chkAutoApply.isChecked()

    def setAutoApplyRules(self, enabled: bool):
        self.chkAutoApply.setChecked(enabled)

    @Slot()
    def applyRulesIfAuto(self):
        if self.isAutoApplyRules():
            self.applyRules()

    @Slot()
    def applyRules(self):
        rulesProcessor = self.ctx.rulesProcessor()
        text = self.txtCaption.getCaption()

        if self.multiEdit.active:
            textNew = self.multiEdit.loadCaptions(self.filelist.selectedFiles, self._multiEditLoadApplyRules)
        else:
            textNew = rulesProcessor.process(text)

        # Only set when text has changed to prevent save button turning red
        if textNew != text:
            self.txtCaption.setCaption(textNew)


    @Slot()
    def saveCaption(self):
        # Skip to next file when saving succeeds and skip-on-save is enabled. Don't loop.
        if self.saveCaptionNoSkip() and self.chkSkipOnSave.isChecked() and not self.filelist.isLastFile():
            self.filelist.setNextFile()

    def saveCaptionNoSkip(self) -> bool:
        if self.multiEdit.active:
            if self.multiEdit.saveCaptions(self.destSelector):
                self.btnSave.setChanged(False)
                return True
            else:
                return False

        else:
            text = self.txtCaption.getCaption()
            currentFile = self.filelist.getCurrentFile()

            if self.destSelector.saveCaption(currentFile, text):
                self.captionCache.remove()
                self.captionCache.setState(DataKeys.IconStates.Saved)
                self.btnSave.setChanged(False)
                return True
            else:
                return False


    def loadCaption(self):
        # Use cached caption if it exists in dictionary
        cachedCaption = self.captionCache.get()
        if cachedCaption is not None:
            self.txtCaption.setCaption(cachedCaption)
            self.captionCache.setState(DataKeys.IconStates.Changed)
        else:
            self.resetCaption()

    def _loadCaption(self, file: str) -> str:
        captionText: str | None = self.filelist.getData(file, DataKeys.Caption)
        if captionText is not None:
            self.filelist.setData(file, DataKeys.CaptionState, DataKeys.IconStates.Changed)
            return captionText

        captionText = self.srcSelector.loadCaption(file)
        if captionText is not None:
            # NOTE: "Saved" icon state is lost when a caption is edited and then reloaded.
            iconState = self.filelist.getData(file, DataKeys.CaptionState)
            if (iconState is None) or (iconState == DataKeys.IconStates.Changed):
                iconState = DataKeys.IconStates.Exists

            self.filelist.setData(file, DataKeys.CaptionState, iconState)
            return captionText

        # Initialize missing caption with empty string
        self.filelist.removeData(file, DataKeys.CaptionState)
        return ""

    @Slot()
    def resetCaption(self):
        if self.multiEdit.active:
            for file in self.filelist.selectedFiles:
                self.filelist.removeData(file, DataKeys.Caption)
            text = self.multiEdit.loadCaptions(self.filelist.selectedFiles, self._loadCaption, cacheCurrent=False)

        else:
            self.captionCache.remove()
            text = self._loadCaption( self.filelist.getCurrentFile() )

        self._setCaptionUnedited(text)
        self.btnSave.setChanged(False)
        self.btnReset.setChanged(False)


    def onFileChanged(self, currentFile: str):
        if not self.multiEdit.active:
            self.loadCaption()
            self.applyRulesIfAuto()

        # The generate tab needs the caption text for variables, so initialize and update it here.
        self.ctx.generate.onFileChanged(currentFile)

    def onFileListChanged(self, currentFile: str):
        self.onFileChanged(currentFile)

    def onFileSelectionChanged(self, selectedFiles: set[str]):
        if selectedFiles:
            self.btnMultiEdit.setText(str(len(selectedFiles)))
            self.btnMultiEdit.setChecked(True)
            self.btnMultiEdit.show()

            edited = self.multiEdit.isEdited
            loadFunc = self._multiEditLoadApplyRules if self.isAutoApplyRules() else self._loadCaption
            text = self.multiEdit.loadCaptions(selectedFiles, loadFunc)
            self._setCaptionUnedited(text, edited)

        else:
            self.btnMultiEdit.hide()
            self.btnMultiEdit.setChecked(False)

            if self.multiEdit.active:
                self.multiEdit.clear()
                self.loadCaption()


    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.matches(QtGui.QKeySequence.StandardKey.Save):
            self.saveCaption()
            event.accept()
            return

        event.ignore()
        return super().keyPressEvent(event)


    @Slot()
    def _multiEditEnsureFullPresence(self, index: int):
        if not self.multiEdit.active:
            return

        self.multiEdit.ensureFullPresence(index)

        text = self.txtCaption.getCaption()
        self.ctx.highlight.highlight(text, self.captionSeparator, self.txtCaption, self.highlightState)
        self.bubbles.updateBubbles()
        self._updatePreview(text)
        self._multiEditHighlightImages(index)

        self.btnSave.setChanged(True)

    @Slot()
    def _multiEditToggle(self, state: bool):
        if state:
            if not self.multiEdit.active:
                self.onFileSelectionChanged(self.filelist.selectedFiles)
        elif self.multiEdit.active:
            self.multiEdit.clear()
            self.loadCaption()


    @Slot()
    def _multiEditHighlightImages(self, index: int):
        if not self.multiEdit.active:
            return

        from gallery.gallery import Gallery
        gallery: Gallery | None = self.ctx.tab.getWindowContent("gallery")
        if gallery:
            files = self.multiEdit.getTagFiles(index) # Empty list for index<0
            gallery.highlightFiles(files)

    @Slot()
    def _updateTextCursorHighlight(self):
        if not self.multiEdit.active:
            return

        index = -1
        if self.txtCaption.hasFocus():
            text = self.txtCaption.getCaption()
            cursorPos = self.txtCaption.textCursor().position()
            index = self.txtCaption.getCaptionAtCursor(text, self.captionSeparator, cursorPos)[1]

        self._multiEditHighlightImages(index)

    @Slot()
    def _updateBubbleHighlight(self, index: int):
        if index < 0:
            self._updateTextCursorHighlight()
        else:
            self._multiEditHighlightImages(index)


    # Defined here to avoid circular dependency.
    def _multiEditLoadApplyRules(self, file: str) -> str:
        caption = self._loadCaption(file)
        caption = self.ctx.rulesProcessor().process(caption)

        self.filelist.setData(file, DataKeys.Caption, caption)
        self.filelist.setData(file, DataKeys.CaptionState, DataKeys.IconStates.Changed)
        return caption



class CaptionCache:
    def __init__(self, filelist: FileList):
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
            newHoverText = CaptionTextEdit.getCaptionAtCursor(text, self.container.captionSeparator, cursorPos)[0]
        self.setHoverText(newHoverText)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.setHoverText("")



class RightClickToggleButton(qtlib.ToggleButton):
    rightClicked = Signal()

    def __init__(self, text: str):
        super().__init__(text)

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        if e.button() == Qt.MouseButton.RightButton and self.rect().contains(e.position().toPoint()):
            e.accept()
            self.rightClicked.emit()
            return

        super().mouseReleaseEvent(e)
