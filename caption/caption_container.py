import os
from PySide6 import QtWidgets
from PySide6.QtCore import Signal, Slot
import qtlib
from filelist import DataKeys
from .caption_bubbles import CaptionBubbles
from .caption_filter import BannedCaptionFilter, DuplicateCaptionFilter, MutuallyExclusiveFilter, PrefixSuffixFilter, SortCaptionFilter
from .caption_generate import CaptionGenerate
from .caption_groups import CaptionGroups
from .caption_settings import CaptionSettings


class CaptionContext(QtWidgets.QTabWidget):
    captionClicked      = Signal(str)
    separatorChanged    = Signal(str)
    controlUpdated      = Signal()
    needsRulesApplied   = Signal()
    captionGenerated    = Signal(str, str)


    def __init__(self, tab, getSelectedCaption):
        super().__init__()
        self.tab = tab
        self.getSelectedCaption = getSelectedCaption

        self.settings = CaptionSettings(self)
        self.groups   = CaptionGroups(self)
        self.generate = CaptionGenerate(self)

        self.addTab(self.settings, "Settings")
        self.addTab(self.groups, "Caption")
        #self.addTab(QtWidgets.QWidget(), "Variables (json)")
        #self.addTab(QtWidgets.QWidget(), "Folder Overrides") # Let variables from json override settings?
        self.addTab(self.generate, "Generate")



class CaptionContainer(QtWidgets.QWidget):
    def __init__(self, tab):
        super().__init__()
        self.captionCache = CaptionCache(tab.filelist)

        self.captionFile = None
        self.captionFileExt = ".txt"
        self.captionSeparator = ', '

        self.ctx = CaptionContext(tab, self.getSelectedCaption)
        self._build(self.ctx)

        self.ctx.captionClicked.connect(self.appendToCaption)
        self.ctx.captionGenerated.connect(self._onCaptionGenerated)
        self.ctx.separatorChanged.connect(self._onSeparatorChanged)
        self.ctx.controlUpdated.connect(self.onControlUpdated)
        self.ctx.needsRulesApplied.connect(self.applyRulesIfAuto)

        tab.filelist.addListener(self)
        self.onFileChanged( tab.filelist.getCurrentFile() )


    def _build(self, ctx):
        layout = QtWidgets.QGridLayout()
        layout.addWidget(ctx, 0, 0, 1, 3)
        layout.setRowStretch(0, 0)

        self.bubbles = CaptionBubbles(self.ctx.groups.getCaptionColors, showWeights=False, showRemove=True, editable=False)
        self.bubbles.setContentsMargins(0, 18, 0, 0)
        self.bubbles.remove.connect(self.removeCaption)
        self.bubbles.orderChanged.connect(lambda: self.setCaption( self.captionSeparator.join(self.bubbles.getCaptions()) ))
        self.bubbles.dropped.connect(self.appendToCaption)
        layout.addWidget(self.bubbles, 1, 0, 1, 3)
        layout.setRowStretch(1, 0)

        self.txtCaption = QtWidgets.QPlainTextEdit()
        self.txtCaption.textChanged.connect(self._onCaptionEdited)
        qtlib.setMonospace(self.txtCaption, 1.2)
        layout.addWidget(self.txtCaption, 2, 0, 1, 3)
        layout.setRowStretch(2, 1)

        self.btnApplyRules = QtWidgets.QPushButton("Apply Rules")
        self.btnApplyRules.clicked.connect(self.applyRules)
        layout.addWidget(self.btnApplyRules, 3, 0)

        self.btnReset = QtWidgets.QPushButton("Reload")
        self.btnReset.clicked.connect(self.resetCaption)
        layout.addWidget(self.btnReset, 3, 1)

        self.btnSave = QtWidgets.QPushButton("Save")
        self.btnSave.clicked.connect(self.saveCaption)
        layout.addWidget(self.btnSave, 3, 2)

        layout.setRowStretch(3, 0)
        self.setLayout(layout)

    
    def _setSaveButtonStyle(self, changed: bool):
        if changed:
            self.btnSave.setStyleSheet("border: 2px solid #bb3030; border-style: outset; border-radius: 4px; padding: 2px")
        else:
            self.btnSave.setStyleSheet("")

    def setCaption(self, text):
        self.txtCaption.setPlainText(text)

    def _onCaptionEdited(self):
        text = self.txtCaption.toPlainText()
        self.bubbles.setText(text)
        self.ctx.groups.updateSelectedState(text)

        self.captionCache.put(text)
        self.captionCache.setState(DataKeys.IconStates.Changed)
        self._setSaveButtonStyle(True)

    def getSelectedCaption(self):
        text = self.txtCaption.toPlainText()
        splitSeparator = self.captionSeparator.strip()
        lenSplitSeparator = len(splitSeparator)
        splitText = text.split(splitSeparator)
        cursorPos = self.txtCaption.textCursor().position()

        accumulatedLength = 0
        for part in splitText:
            accumulatedLength += len(part) + lenSplitSeparator
            if cursorPos < accumulatedLength:
                return part.strip()

        return ""


    @Slot()
    def onControlUpdated(self):
        self.bubbles.updateBubbles()
        self.ctx.groups.updateSelectedState(self.txtCaption.toPlainText())

    @Slot()
    def appendToCaption(self, text):
        caption = self.txtCaption.toPlainText()
        if caption:
            caption += self.captionSeparator
        caption += text
        self.setCaption(caption)

        if self.ctx.settings.isAutoApplyRules:
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
        if self.ctx.settings.isAutoApplyRules:
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
        if self.ctx.settings.isAutoApplyRules:
            self.applyRules()

    @Slot()
    def applyRules(self):
        text = self.txtCaption.toPlainText()
        splitSeparator = self.captionSeparator.strip()
        captions = [c.strip() for c in text.split(splitSeparator)]
        captionGroups = self.ctx.groups.getCaptionGroups()

        # Filter mutually exclusive captions before removing duplicates: This will keep the last inserted caption
        exclusiveCaptionGroups = [group.captions for group in captionGroups if group.mutuallyExclusive]
        exclusiveFilter = MutuallyExclusiveFilter(exclusiveCaptionGroups)
        captions = exclusiveFilter.filterCaptions(captions)

        if self.ctx.settings.isRemoveDuplicates:
            dupFilter = DuplicateCaptionFilter()
            captions = dupFilter.filterCaptions(captions)

        banFilter = BannedCaptionFilter(self.ctx.settings.bannedCaptions)
        captions = banFilter.filterCaptions(captions)

        allCaptionGroups = [group.captions for group in captionGroups]
        sortFilter = SortCaptionFilter(allCaptionGroups, self.ctx.settings.prefix, self.ctx.settings.suffix, self.captionSeparator)
        captions = sortFilter.filterCaptions(captions)

        presufFilter = PrefixSuffixFilter(self.ctx.settings.prefix, self.ctx.settings.suffix, self.captionSeparator)
        captions = presufFilter.filterCaptions(captions)

        # Only set when text has changed to prevent save button turning red
        textNew = self.captionSeparator.join(captions)
        if textNew != text:
            self.setCaption(textNew)

    @Slot()
    def saveCaption(self):
        if os.path.exists(self.captionFile):
            print("Overwriting caption file:", self.captionFile)
        else:
            print("Saving to caption file:", self.captionFile)
        
        text = self.txtCaption.toPlainText()
        with open(self.captionFile, 'w') as file:
            file.write(text)

        self.captionCache.remove()
        self.captionCache.setState(DataKeys.IconStates.Saved)
        self._setSaveButtonStyle(False)

    @Slot()
    def resetCaption(self):
        if os.path.exists(self.captionFile):
            with open(self.captionFile, 'r') as file:
                text = file.read()
            self.setCaption(text)
            self.captionCache.setState(DataKeys.IconStates.Exists)
        else:
            self.setCaption("")
            self.captionCache.setState(None)
        
        # When setting the text, _onCaptionEdited() will make a cache entry and turn the save button red. So we revert that here.
        self.captionCache.remove()
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
    def _onSeparatorChanged(self, separator):
        self.captionSeparator = separator
        self.bubbles.separator = separator
        self.bubbles.updateBubbles()

    def onFileChanged(self, currentFile):
        filename = os.path.normpath(currentFile)
        dirname, filename = os.path.split(filename)
        filename = os.path.basename(filename)
        filename = os.path.splitext(filename)[0]
        self.captionFile = os.path.join(dirname, filename + self.captionFileExt)
        self.loadCaption()

        if self.ctx.settings.isAutoApplyRules:
            self.applyRules()
    
    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)



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
    
    def setState(self, state: DataKeys.IconStates):
        file = self.filelist.getCurrentFile()
        if state:
            self.filelist.setData(file, DataKeys.CaptionState, state)
        else:
            self.filelist.removeData(file, DataKeys.CaptionState)
            