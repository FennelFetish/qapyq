from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot
from .caption_control import CaptionControl
from .caption_bubbles import CaptionBubbles
import os
import qtlib
from .caption_filter import DuplicateCaptionFilter, BannedCaptionFilter, SortCaptionFilter, PrefixSuffixFilter, MutuallyExclusiveFilter


# Tags as QLineEdit with handle, width is adjusted on text change
# Drag&Drop reorder, visualize insertion position with |-element, freeze any other relayouting during drag&drop
# Multiple rows of QHBoxLayout? FlowLayout? https://doc.qt.io/qt-6/qtwidgets-layouts-flowlayout-example.html

# Nested text fields for expressions like: (blue (starry:0.8) sky:1.2)
# Colored fields: red=high weight, blue=low weight
# Navigate with arrow keys into adjacent tags (always navigate in text)
# One handle per segment (comma until comma)


# QTextDocument?        https://doc.qt.io/qt-6/qtextdocument.html
# QSyntaxHighlighter?   https://doc.qt.io/qt-6/qsyntaxhighlighter.html


# TODO: Show icon in gallery for changed but unsaved captions.

class CaptionContainer(QtWidgets.QWidget):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab

        self.captionControl = CaptionControl(self)
        self.captionControl.captionClicked.connect(self.appendToCaption)
        self.captionControl.separatorChanged.connect(self._onSeparatorChanged)
        self.captionControl.controlUpdated.connect(self.onControlUpdated)
        self.captionControl.needsRulesApplied.connect(self.applyRulesIfAuto)

        self.captionCache = CaptionCache(self)

        self.bubbles = CaptionBubbles(self.captionControl.getCaptionColors, showWeights=False, showRemove=True, editable=False)
        self.bubbles.setContentsMargins(0, 18, 0, 0)
        self.bubbles.remove.connect(self.removeCaption)
        self.bubbles.orderChanged.connect(lambda: self.setCaption( self.captionSeparator.join(self.bubbles.getCaptions()) ))
        self.bubbles.dropped.connect(self.appendToCaption)

        self.captionFile = None
        self.captionFileExt = ".txt"
        self.captionSeparator = ', '

        self.txtCaption = QtWidgets.QPlainTextEdit()
        self.txtCaption.textChanged.connect(self._onCaptionEdited)
        qtlib.setMonospace(self.txtCaption, 1.2)

        self.btnApplyRules = QtWidgets.QPushButton("Apply Rules")
        self.btnApplyRules.clicked.connect(self.applyRules)

        self.btnReset = QtWidgets.QPushButton("Reload")
        self.btnReset.clicked.connect(self.resetCaption)

        self.btnSave = QtWidgets.QPushButton("Save")
        self.btnSave.clicked.connect(self.saveCaption)

        layout = QtWidgets.QGridLayout()
        layout.addWidget(self.captionControl, 0, 0, 1, 3)
        layout.setRowStretch(0, 0)
        layout.addWidget(self.bubbles, 1, 0, 1, 3)
        layout.setRowStretch(1, 0)
        layout.addWidget(self.txtCaption, 2, 0, 1, 3)
        layout.setRowStretch(2, 1)
        layout.addWidget(self.btnApplyRules, 3, 0)
        layout.addWidget(self.btnReset, 3, 1)
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
        self.captionControl.setText(text)

        self.captionCache.put(text)
        self.captionCache.setState("fail")
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
        self.captionControl.setText(self.txtCaption.toPlainText())

    @Slot()
    def appendToCaption(self, text):
        caption = self.txtCaption.toPlainText()
        if caption:
            caption += self.captionSeparator
        caption += text
        self.setCaption(caption)

        if self.captionControl.isAutoApplyRules:
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
        if self.captionControl.isAutoApplyRules:
            self.applyRules()

    @Slot()
    def applyRules(self):
        text = self.txtCaption.toPlainText()
        splitSeparator = self.captionSeparator.strip()
        captions = [c.strip() for c in text.split(splitSeparator)]
        captionGroups = self.captionControl.getCaptionGroups()

        # Filter mutually exclusive captions before removing duplicates: This will keep the last inserted caption
        exclusiveCaptionGroups = [group.captions for group in captionGroups if group.mutuallyExclusive]
        exclusiveFilter = MutuallyExclusiveFilter(exclusiveCaptionGroups)
        captions = exclusiveFilter.filterCaptions(captions)

        if self.captionControl.isRemoveDuplicates:
            dupFilter = DuplicateCaptionFilter()
            captions = dupFilter.filterCaptions(captions)

        banFilter = BannedCaptionFilter(self.captionControl.bannedCaptions)
        captions = banFilter.filterCaptions(captions)

        allCaptionGroups = [group.captions for group in captionGroups]
        sortFilter = SortCaptionFilter(allCaptionGroups, self.captionControl.prefix, self.captionControl.suffix, self.captionSeparator)
        captions = sortFilter.filterCaptions(captions)

        presufFilter = PrefixSuffixFilter(self.captionControl.prefix, self.captionControl.suffix, self.captionSeparator)
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
        self.captionCache.setState("pass")
        self._setSaveButtonStyle(False)

    @Slot()
    def resetCaption(self):
        if os.path.exists(self.captionFile):
            with open(self.captionFile) as file:
                text = file.read()
                self.setCaption(text)
            self.captionCache.setState("white")
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
            self.captionCache.setState("fail")
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

        if self.captionControl.isAutoApplyRules:
            self.applyRules()
    
    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)



class CaptionCache:
    keyCaption = "caption"
    keyState   = "caption_state"

    def __init__(self, captionControl):
        self.captionControl = captionControl
        self.filelist = captionControl.tab.filelist
    
    def get(self):
        file = self.filelist.getCurrentFile()
        return self.filelist.getData(file, CaptionCache.keyCaption)

    def put(self, text):
        file = self.filelist.getCurrentFile()
        self.filelist.setData(file, CaptionCache.keyCaption, text)

    def remove(self):
        file = self.filelist.getCurrentFile()
        self.filelist.removeData(file, CaptionCache.keyCaption)
    
    def setState(self, state):
        file = self.filelist.getCurrentFile()
        if state:
            self.filelist.setData(file, CaptionCache.keyState, state)
        else:
            self.filelist.removeData(file, CaptionCache.keyState)
            