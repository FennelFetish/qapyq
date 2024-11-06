import os
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Signal, Slot, QSignalBlocker
from lib import qtlib
from lib.filelist import DataKeys
from lib.captionfile import CaptionFile
from .caption_bubbles import CaptionBubbles
from .caption_filter import CaptionRulesProcessor
from .caption_generate import CaptionGenerate
from .caption_groups import CaptionGroups
from .caption_settings import CaptionSettings, FileTypeSelector

# TODO: Ctrl+S saves current caption

class CaptionContext(QtWidgets.QTabWidget):
    captionClicked      = Signal(str)
    separatorChanged    = Signal(str)
    controlUpdated      = Signal()
    fileTypeUpdated     = Signal()
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
        self.addTab(self.groups, "Groups")
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
        self.ctx.controlUpdated.connect(self._onControlUpdated)
        self.ctx.fileTypeUpdated.connect(self._onFileTypeUpdated)
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

        self.btnReset = QtWidgets.QPushButton("Reload from .txt")
        self.btnReset.clicked.connect(self.resetCaption)
        layout.addWidget(self.btnReset, 3, 1)

        self.btnSave = QtWidgets.QPushButton("Save to .txt")
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
            cursor.movePosition(QtGui.QTextCursor.End, QtGui.QTextCursor.KeepAnchor)
            cursor.setCharFormat(QtGui.QTextCharFormat())

            start = 0
            sep = self.captionSeparator.strip()
            for caption in text.split(sep):
                if format := formats.get(caption.strip()):
                    cursor.setPosition(start)
                    cursor.setPosition(start+len(caption), QtGui.QTextCursor.KeepAnchor)
                    cursor.setCharFormat(format)
                start += len(caption) + len(sep)


    def getSelectedCaption(self):
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
        rulesProcessor = CaptionRulesProcessor()
        rulesProcessor.setup(self.ctx.settings.prefix, self.ctx.settings.suffix, self.captionSeparator, self.ctx.settings.isRemoveDuplicates)
        rulesProcessor.setBannedCaptions(self.ctx.settings.bannedCaptions)
        rulesProcessor.setCaptionGroups(
            (group.captions for group in self.ctx.groups.groups),
            (group.captions for group in self.ctx.groups.groups if group.mutuallyExclusive)
        )

        text = self.txtCaption.toPlainText()
        textNew = rulesProcessor.process(text)

        # Only set when text has changed to prevent save button turning red
        if textNew != text:
            self.setCaption(textNew)


    @Slot()
    def _onFileTypeUpdated(self):
        srcSelector = self.ctx.settings.srcSelector
        if srcSelector.type == FileTypeSelector.TYPE_TXT:
            self.btnReset.setText("Reload from .txt")
        else:
            self.btnReset.setText(f"Reload from .json   [{srcSelector.type}.{srcSelector.name}]")

        destSelector = self.ctx.settings.destSelector
        if destSelector.type == FileTypeSelector.TYPE_TXT:
            self.btnSave.setText("Save to .txt")
        else:
            self.btnSave.setText(f"Save to .json   [{destSelector.type}.{destSelector.name}]")


    @Slot()
    def saveCaption(self):
        text = self.txtCaption.toPlainText()

        destSelector = self.ctx.settings.destSelector
        success = False
        if destSelector.type == FileTypeSelector.TYPE_TXT:
            success = self.saveCaptionTxt(text)
        else:
            success = self.saveCaptionJson(text, destSelector.type, destSelector.name)

        if success:
            self.captionCache.remove()
            self.captionCache.setState(DataKeys.IconStates.Saved)
            self._setSaveButtonStyle(False)

    def saveCaptionTxt(self, text: str) -> bool:
        with open(self.captionFile, 'w') as file:
            file.write(text)
        print("Saved caption to file:", self.captionFile)
        return True

    def saveCaptionJson(self, text: str, type: str, name: str) -> bool:
        captionFile = CaptionFile(self.captionFile)
        
        if type == FileTypeSelector.TYPE_CAPTIONS:
            captionFile.addCaption(name, text)
        else:
            captionFile.addTags(name, text)
        
        if captionFile.updateToJson():
            print(f"Saved caption to file: {captionFile.jsonPath} [{type}.{name}]")
            return True
        else:
            print(f"Failed to save caption to file: {captionFile.jsonPath} [{type}.{name}]")
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
        srcSelector = self.ctx.settings.srcSelector
        if srcSelector.type == FileTypeSelector.TYPE_TXT:
            text = self.resetCaptionTxt()
        else:
            text = self.resetCaptionJson(srcSelector.type, srcSelector.name)

        if text:
            self.setCaption(text)
            self.captionCache.setState(DataKeys.IconStates.Exists)
        else:
            self.setCaption("")
            self.captionCache.setState(None)
        
        # When setting the text, _onCaptionEdited() will make a cache entry and turn the save button red. So we revert that here.
        self.captionCache.remove()
        self._setSaveButtonStyle(False)

    def resetCaptionTxt(self) -> str | None:
        if os.path.exists(self.captionFile):
            with open(self.captionFile, 'r') as file:
                return file.read()
        return None

    def resetCaptionJson(self, type: str, name: str):
        captionFile = CaptionFile(self.captionFile)
        if not captionFile.loadFromJson():
            return None

        if type == FileTypeSelector.TYPE_CAPTIONS:
            return captionFile.getCaption(name)
        else:
            return captionFile.getTags(name)
        

    @Slot()
    def _onSeparatorChanged(self, separator):
        self.captionSeparator = separator
        self.bubbles.separator = separator
        self._onControlUpdated()


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
    
    def setState(self, state: DataKeys.IconStates | None):
        file = self.filelist.getCurrentFile()
        if state:
            self.filelist.setData(file, DataKeys.CaptionState, state)
        else:
            self.filelist.removeData(file, DataKeys.CaptionState)
            