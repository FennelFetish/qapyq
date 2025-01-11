import os
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Signal, Slot, QSignalBlocker
from lib import qtlib
from lib.filelist import DataKeys
from lib.captionfile import FileTypeSelector
from .caption_bubbles import CaptionBubbles
from .caption_filter import CaptionRulesProcessor
from .caption_generate import CaptionGenerate
from .caption_groups import CaptionGroups
from .caption_settings import CaptionSettings


class CaptionContext(QtWidgets.QTabWidget):
    captionClicked      = Signal(str)
    separatorChanged    = Signal(str)
    controlUpdated      = Signal()
    needsRulesApplied   = Signal()
    captionGenerated    = Signal(str, str)


    def __init__(self, tab, getSelectedCaption, isAutoApplyRules, setAutoApplyRules):
        super().__init__()
        self.tab = tab
        self.getSelectedCaption = getSelectedCaption
        self.isAutoApplyRules = isAutoApplyRules
        self.setAutoApplyRules = setAutoApplyRules

        self.settings = CaptionSettings(self)
        self.groups   = CaptionGroups(self)
        self.generate = CaptionGenerate(self)

        self.addTab(self.settings, "Rules")
        self.addTab(self.groups, "Groups")
        #self.addTab(QtWidgets.QWidget(), "Variables (json)")
        #self.addTab(QtWidgets.QWidget(), "Folder Overrides") # Let variables from json override settings?
        self.addTab(self.generate, "Generate")



class CaptionContainer(QtWidgets.QWidget):
    def __init__(self, tab):
        super().__init__()
        self.captionCache = CaptionCache(tab.filelist)

        self.captionSeparator = ', '

        self.ctx = CaptionContext(tab, self.getSelectedCaption, self.isAutoApplyRules, self.setAutoApplyRules)
        self._build(self.ctx)

        self.ctx.captionClicked.connect(self.appendToCaption)
        self.ctx.captionGenerated.connect(self._onCaptionGenerated)
        self.ctx.separatorChanged.connect(self._onSeparatorChanged)
        self.ctx.controlUpdated.connect(self._onControlUpdated)
        self.ctx.needsRulesApplied.connect(self.applyRulesIfAuto)

        tab.filelist.addListener(self)
        self.onFileChanged( tab.filelist.getCurrentFile() )

        self.ctx.settings._loadDefaultPreset()

    def _build(self, ctx):
        splitter = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(12)
        splitter.addWidget(ctx)
        splitter.setStretchFactor(0, 1)

        self.bubbles = CaptionBubbles(self.ctx.groups.getCaptionColors, showWeights=False, showRemove=True, editable=False)
        self.bubbles.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        self.bubbles.setContentsMargins(4, 4, 4, 4)
        self.bubbles.remove.connect(self.removeCaption)
        self.bubbles.orderChanged.connect(lambda: self.setCaption( self.captionSeparator.join(self.bubbles.getCaptions()) ))
        self.bubbles.dropped.connect(self.appendToCaption)
        splitter.addWidget(self.bubbles)
        splitter.setStretchFactor(1, 1)

        self.txtCaption = QtWidgets.QPlainTextEdit()
        self.txtCaption.textChanged.connect(self._onCaptionEdited)
        qtlib.setMonospace(self.txtCaption, 1.2)
        splitter.addWidget(self.txtCaption)
        splitter.setStretchFactor(2, 1)
        
        mainLayout = QtWidgets.QVBoxLayout()
        mainLayout.setContentsMargins(0, 0, 0, 0)
        mainLayout.addWidget(splitter)
        mainLayout.addWidget(self._buildBottomRow())
        self.setLayout(mainLayout)

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
        self.btnReset = QtWidgets.QPushButton("Reload From:")
        self.btnReset.setFixedWidth(100)
        self.btnReset.clicked.connect(self.resetCaption)
        layout.addWidget(self.btnReset, 0, col)
        layout.setColumnStretch(col, 0)

        col += 1
        self.srcSelector = FileTypeSelector()
        self.srcSelector.type = FileTypeSelector.TYPE_TAGS
        self.srcSelector.txtName.setFixedWidth(120)
        layout.addLayout(self.srcSelector, 0, col)
        layout.setColumnStretch(col, 0)

        col += 1
        layout.addWidget(qtlib.VerticalSeparator(), 0, col)
        layout.setColumnStretch(col, 0)

        col += 1
        self.btnSave = QtWidgets.QPushButton("Save To:")
        self.btnSave.setFixedWidth(100)
        self.btnSave.clicked.connect(self.saveCaption)
        layout.addWidget(self.btnSave, 0, col)
        layout.setColumnStretch(col, 0)

        self.btnSavePalette = self.btnSave.palette()
        self.btnSaveChangedPalette = self.btnSave.palette()
        self.btnSaveChangedPalette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor.fromString("#440A0A"))
        self.btnSaveChangedPalette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor.fromString("#FFEEEE"))

        col += 1
        self.destSelector = FileTypeSelector()
        self.destSelector.type = FileTypeSelector.TYPE_TAGS
        self.destSelector.txtName.setFixedWidth(120)
        layout.addLayout(self.destSelector, 0, col)
        layout.setColumnStretch(col, 0)

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

        return menu


    def _setSaveButtonStyle(self, changed: bool):
        self.btnSave.setPalette(self.btnSaveChangedPalette if changed else self.btnSavePalette)

    def setCaption(self, text):
        self.txtCaption.setPlainText(text)
        self.txtCaption.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def _onCaptionEdited(self):
        text = self.txtCaption.toPlainText()
        self._highlight(text)
        self.bubbles.setText(text)
        self.ctx.groups.updateSelectedState(text)

        self.captionCache.put(text)
        self.captionCache.setState(DataKeys.IconStates.Changed)
        self._setSaveButtonStyle(True)


    def _highlight(self, text: str):
        formats = self.ctx.groups.getCaptionCharFormats()
        with QSignalBlocker(self.txtCaption):
            cursor = self.txtCaption.textCursor()
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
        self._highlight(text)
        self.bubbles.updateBubbles()
        self.ctx.groups.updateSelectedState(text)
        

    @Slot()
    def appendToCaption(self, text):
        caption = self.txtCaption.toPlainText()
        if caption:
            caption += self.captionSeparator
        caption += text
        self.setCaption(caption)

        if self.isAutoApplyRules():
            self.applyRules()

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
    def removeCaption(self, index):
        text = self.txtCaption.toPlainText()
        splitSeparator = self.captionSeparator.strip()
        captions = [c.strip() for c in text.split(splitSeparator)]
        del captions[index]
        self.setCaption( self.captionSeparator.join(captions) )

    @Slot()
    def applyRulesIfAuto(self):
        if self.isAutoApplyRules():
            self.applyRules()

    @Slot()
    def applyRules(self):
        removeDup = self.ctx.settings.isRemoveDuplicates
        sortCaptions = self.ctx.settings.isSortCaptions

        rulesProcessor = CaptionRulesProcessor()
        rulesProcessor.setup(self.ctx.settings.prefix, self.ctx.settings.suffix, self.captionSeparator, removeDup, sortCaptions)
        rulesProcessor.setSearchReplacePairs(self.ctx.settings.searchReplacePairs)
        rulesProcessor.setBannedCaptions(self.ctx.settings.bannedCaptions)
        rulesProcessor.setCaptionGroups( group.captions for group in self.ctx.groups.groups )
        rulesProcessor.setMutuallyExclusiveCaptionGroups( group.captions for group in self.ctx.groups.groups if group.mutuallyExclusive )
        rulesProcessor.setCombinationCaptionGroups( group.captions for group in self.ctx.groups.groups if group.combineTags )

        text = self.txtCaption.toPlainText()
        textNew = rulesProcessor.process(text)

        # Only set when text has changed to prevent save button turning red
        if textNew != text:
            self.setCaption(textNew)


    @Slot()
    def saveCaption(self):
        text = self.txtCaption.toPlainText()
        currentFile = self.ctx.tab.filelist.getCurrentFile()

        if self.destSelector.saveCaption(currentFile, text):
            self.captionCache.remove()
            self.captionCache.setState(DataKeys.IconStates.Saved)
            self._setSaveButtonStyle(False)

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
        self._setSaveButtonStyle(False)


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
