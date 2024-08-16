from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot
from .caption_control import CaptionControl
from .caption_bubbles import CaptionBubbles
import os
import qtlib


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
        self.bubbles = CaptionBubbles()

        self.captionCache = {}
        self.captionControl = CaptionControl(self)
        self.captionControl.captionClicked.connect(self.appendToCaption)
        self.captionControl.separatorChanged.connect(self._onSeparatorChanged)

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

    def setCaption(self, text):
        self.txtCaption.setPlainText(text)

    def _onCaptionEdited(self):
        text = self.txtCaption.toPlainText()
        self.captionCache[self.captionFile] = text
        self.bubbles.setText(text)

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
    def appendToCaption(self, text):
        caption = self.txtCaption.toPlainText()
        if caption:
            caption += self.captionSeparator
        caption += text
        self.setCaption(caption)

    @Slot()
    def applyRules(self):
        pass

    @Slot()
    def saveCaption(self):
        if os.path.exists(self.captionFile):
            print("Overwriting caption file:", self.captionFile)
        else:
            print("Saving to caption file:", self.captionFile)
        
        text = self.txtCaption.toPlainText()
        with open(self.captionFile, 'w') as file:
            file.write(text)

        del self.captionCache[self.captionFile]

    @Slot()
    def resetCaption(self):
        if os.path.exists(self.captionFile):
            with open(self.captionFile) as file:
                text = file.read()
                self.captionCache[self.captionFile] = text
                self.setCaption(text)
        else:
            self.setCaption("")

    def loadCaption(self):
        # Use cached caption if it exists in dictionary. But if cached caption is empty, reload it from file.
        # (If another program changes the caption file, one can set the cached caption to empty string to reload the caption...)
        if self.captionFile in self.captionCache and self.captionCache[self.captionFile]:
            self.setCaption( self.captionCache[self.captionFile] )
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
    
    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)
