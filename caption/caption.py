from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot
from .caption_bubbles import CaptionBubbles
import os


# Tags as QLineEdit with handle, width is adjusted on text change
# Drag&Drop reorder, visualize insertion position with |-element, freeze any other relayouting during drag&drop
# Multiple rows of QHBoxLayout? FlowLayout? https://doc.qt.io/qt-6/qtwidgets-layouts-flowlayout-example.html

# Nested text fields for expressions like: (blue (starry:0.8) sky:1.2)
# Colored fields: red=high weight, blue=low weight
# Navigate with arrow keys into adjacent tags (always navigate in text)
# One handle per segment (comma until comma)


# QTextDocument?        https://doc.qt.io/qt-6/qtextdocument.html
# QSyntaxHighlighter?   https://doc.qt.io/qt-6/qsyntaxhighlighter.html


class CaptionContainer(QtWidgets.QWidget):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.captionCache = {}
        self.bubbles = CaptionBubbles()
        
        self.captionFile = None
        self.captionFileExt = ".txt"

        self.txtCaption = QtWidgets.QTextEdit()
        self.txtCaption.textChanged.connect(self.onCaptionChanged)
        font = self.txtCaption.currentFont()
        font.setStyleHint(QtGui.QFont.Monospace)
        font.setFamily("monospace")
        fontSize = font.pointSizeF() * 1.5
        font.setPointSizeF(fontSize)
        self.txtCaption.setCurrentFont(font)

        self.btnSave = QtWidgets.QPushButton("Save")
        self.btnSave.clicked.connect(self.saveCaption)

        self.btnReset = QtWidgets.QPushButton("Reload")
        self.btnReset.clicked.connect(self.resetCaption)

        layout = QtWidgets.QGridLayout()
        layout.addWidget(self.bubbles, 0, 0, 1, 2)
        layout.addWidget(self.txtCaption, 1, 0, 1, 2)
        layout.addWidget(self.btnReset, 2, 0)
        layout.addWidget(self.btnSave, 2, 1)
        self.setLayout(layout)

    def updateCaption(self, text):
        self.txtCaption.setPlainText(text)
        self.bubbles.setText(text)

    def onCaptionChanged(self):
        text = self.txtCaption.toPlainText()
        self.captionCache[self.captionFile] = text

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
                self.updateCaption(text)
        else:
            self.updateCaption("")

    def loadCaption(self):
        # Use cached caption if it exists in dictionary. But if cached caption is empty, reload it from file.
        # (If another program changes the caption file, one can set the cached caption to empty string to reload the caption...)
        if self.captionFile in self.captionCache and self.captionCache[self.captionFile]:
            self.updateCaption( self.captionCache[self.captionFile] )
        else:
            self.resetCaption()


    def onFileChanged(self, currentFile):
        filename = os.path.normpath(currentFile)
        dirname, filename = os.path.split(filename)
        filename = os.path.basename(filename)
        filename = os.path.splitext(filename)[0]
        self.captionFile = os.path.join(dirname, filename + self.captionFileExt)
        self.loadCaption()
    
    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)


