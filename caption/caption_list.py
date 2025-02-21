from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from lib.captionfile import CaptionFile, FileTypeSelector
import lib.qtlib as qtlib


# List all captions and tags from current json file for comparison.
# Use tag highlighting for tags (or all?).
# Each row shows key and content.
# Each entry has a button (below key?) for loading it into the main text field, and setting the source of FileTypeSelector.
# Only load and highlight captions when tab is active.


class CaptionList(QtWidgets.QWidget):
    def __init__(self, context):
        super().__init__()

        from .caption_container import CaptionContext
        self.ctx: CaptionContext = context

        self._build()

        self.ctx.tab.filelist.addListener(self)
        self.reloadCaptions()

    def _build(self):
        self._layout = QtWidgets.QVBoxLayout()
        self._layout.setSpacing(0)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        widget = QtWidgets.QWidget()
        widget.setLayout(self._layout)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(qtlib.BaseColorScrollArea(widget))
        self.setLayout(layout)


    def reloadCaptions(self):
        self._clearLayout()
        currentFile = self.ctx.tab.filelist.getCurrentFile()

        captionFile = CaptionFile(currentFile)
        if captionFile.loadFromJson():
            sortedTags = sorted(((k, v) for k, v in captionFile.tags.items()), key=lambda item: item[0])
            for key, tags in sortedTags:
                entry = CaptionEntry(self, f"tags.{key}")
                entry.caption = tags
                self._layout.addWidget(entry)

            sortedCaptions = sorted(((k, v) for k, v in captionFile.captions.items()), key=lambda item: item[0])
            for key, cap in sortedCaptions:
                entry = CaptionEntry(self, f"captions.{key}")
                entry.caption = cap
                self._layout.addWidget(entry)

        if text := FileTypeSelector.loadCaptionTxt(currentFile):
            entry = CaptionEntry(self, "text")
            entry.caption = text
            self._layout.addWidget(entry)


    def _clearLayout(self):
        for i in reversed(range(self._layout.count())):
            item = self._layout.takeAt(i)
            if item and (widget := item.widget()):
                widget.deleteLater()


    def onFileChanged(self, currentFile):
        self.reloadCaptions()

    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)



class CaptionEntry(QtWidgets.QWidget):
    def __init__(self, captionList: CaptionList, key: str):
        super().__init__()
        self.captionList = captionList

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnMinimumWidth(0, 200)
        layout.setColumnStretch(1, 1)

        self.txtKey = QtWidgets.QLabel(key)
        self.txtKey.setTextFormat(Qt.TextFormat.PlainText)
        self.txtKey.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        qtlib.setMonospace(self.txtKey)
        layout.addWidget(self.txtKey, 0, 0, Qt.AlignmentFlag.AlignTop)

        self.txtCaption = QtWidgets.QLabel()
        self.txtCaption.setTextFormat(Qt.TextFormat.PlainText)
        self.txtCaption.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.txtCaption.setWordWrap(True)
        self.txtCaption.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Preferred)
        qtlib.setMonospace(self.txtCaption)
        layout.addWidget(self.txtCaption, 0, 1, Qt.AlignmentFlag.AlignTop)

        separatorLine = QtWidgets.QFrame()
        separatorLine.setFrameStyle(QtWidgets.QFrame.Shape.HLine | QtWidgets.QFrame.Shadow.Sunken)
        layout.addWidget(separatorLine, 1, 0, 1, 2)
        layout.setRowMinimumHeight(1, 12)

        self.setLayout(layout)

    @property
    def caption(self):
        return self.txtCaption.text()

    @caption.setter
    def caption(self, text: str):
        self.txtCaption.setText(text)
