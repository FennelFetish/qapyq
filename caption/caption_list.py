from __future__ import annotations
import os
from enum import Enum
from typing import Generator
from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal, QTimer, QSignalBlocker
from lib.captionfile import CaptionFile, FileTypeSelector, Keys
from lib.filelist import DataKeys
from lib import colorlib, qtlib
from ui.autocomplete import AutoCompleteSource, getAutoCompleteSource
from .caption_tab import CaptionTab
from .caption_highlight import CaptionHighlight
from .caption_text import BorderlessNavigationTextEdit


# List all captions and tags from current json file for comparison.
# Only load and highlight captions when tab is active.

# TODO: Add button (below key?) for loading it into the main text field, and setting the source of FileTypeSelector.
# TODO: Update list when standard caption is saved. Only reload the saved value, keep rest.
#       --> No, instead, check file modification time and confirm overwrite.


class KeyType(Enum):
    Tags     = Keys.TAGS
    Caption  = Keys.CAPTIONS
    TextFile = "text"


TYPE_MAP = {
    FileTypeSelector.TYPE_TAGS:     KeyType.Tags,
    FileTypeSelector.TYPE_CAPTIONS: KeyType.Caption,
    FileTypeSelector.TYPE_TXT:      KeyType.TextFile
}

SEPARATORS = {
    KeyType.Tags:     ", ",
    KeyType.Caption:  ". ",
    KeyType.TextFile: ", "
}


DELAY_RESIZE  = 10
DELAY_RESIZE2 = 15
DELAY_SCROLL  = 20



class CaptionList(CaptionTab):
    def __init__(self, context):
        super().__init__(context)
        self._needsReload = True
        self._needsHighlight = False

        self._jsonModTime = -1.0
        self._txtModTime  = -1.0

        self._layoutEntries = QtWidgets.QVBoxLayout()
        self._layoutEntries.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layoutEntries.setSpacing(0)

        self._build()

        self.ctx.tab.filelist.addListener(self)
        self.ctx.controlUpdated.connect(self._updateHighlight)
        self.ctx.multiEditToggled.connect(lambda state: QTimer.singleShot(1, self._updateHighlight))

    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(4)
        layout.setVerticalSpacing(0)
        layout.setColumnStretch(2, 1)

        row = 0
        widget = QtWidgets.QWidget()
        widget.setLayout(self._layoutEntries)

        self._scrollArea = qtlib.RowScrollArea(widget)
        layout.addWidget(self._scrollArea, row, 0, 1, 6)

        row += 1
        self.addEntrySelector = FileTypeSelector()
        self.addEntrySelector.type = FileTypeSelector.TYPE_TAGS
        self.addEntrySelector.name = ""
        layout.addLayout(self.addEntrySelector, row, 0)

        self.btnAddEntry = QtWidgets.QPushButton("✚ Add Key")
        self.btnAddEntry.setMinimumWidth(100)
        self.btnAddEntry.clicked.connect(self._addNewEntry)
        layout.addWidget(self.btnAddEntry, row, 1)

        self.statusBar = qtlib.ColoredMessageStatusBar()
        self.statusBar.layout().setContentsMargins(50, 0, 20, 0)
        self.statusBar.setSizeGripEnabled(False)
        layout.addWidget(self.statusBar, row, 2)

        self.btnReloadAll = qtlib.SaveButton("Reload All")
        self.btnReloadAll.setMinimumWidth(120)
        self.btnReloadAll.clicked.connect(self.reloadCaptions)
        layout.addWidget(self.btnReloadAll, row, 3)

        self.btnSaveAll = qtlib.SaveButton("Save All")
        self.btnSaveAll.setMinimumWidth(120)
        self.btnSaveAll.clicked.connect(self.saveAll)
        layout.addWidget(self.btnSaveAll, row, 4)

        self.setLayout(layout)


    @override
    def onTabEnabled(self):
        if self._needsReload:
            self.reloadCaptions()
        elif self._needsHighlight:
            self._updateHighlight()

    @override
    def onTabDisabled(self):
        pass


    def onFileChanged(self, currentFile: str):
        if self.ctx.currentWidget() is self:
            self.reloadCaptions()
        else:
            self._needsReload = True

    def onFileListChanged(self, currentFile: str):
        self.onFileChanged(currentFile)


    @property
    def entries(self) -> Generator[CaptionEntry]:
        widget: CaptionEntry
        for i in range(self._layoutEntries.count()):
            item = self._layoutEntries.itemAt(i)
            if item and (widget := item.widget()):
                yield widget

    def _clearLayout(self):
        for i in reversed(range(self._layoutEntries.count())):
            item = self._layoutEntries.takeAt(i)
            if item and (widget := item.widget()):
                widget.deleteLater()


    @staticmethod
    def getFileModTime(currentFile: str) -> tuple[float, float]:
        pathNoExt = os.path.splitext(currentFile)[0]

        jsonPath  = pathNoExt + ".json"
        txtPath   = pathNoExt + ".txt"

        jsonModifiedTime = os.path.getmtime(jsonPath) if os.path.exists(jsonPath) else -1.0
        txtModifiedTime  = os.path.getmtime(txtPath)  if os.path.exists(txtPath)  else -1.0
        return jsonModifiedTime, txtModifiedTime


    @Slot()
    def reloadCaptions(self):
        scrollBar = self._scrollArea.verticalScrollBar()
        scrollPos = scrollBar.value()

        self._clearLayout()
        currentFile = self.ctx.tab.filelist.getCurrentFile()

        self._jsonModTime, self._txtModTime = self.getFileModTime(currentFile)

        captionFile = CaptionFile(currentFile)
        if captionFile.loadFromJson():
            sortedTags = sorted(((k, v) for k, v in captionFile.tags.items()), key=lambda item: item[0])
            for key, tags in sortedTags:
                self.addEntry(KeyType.Tags, key, tags)

            sortedCaptions = sorted(((k, v) for k, v in captionFile.captions.items()), key=lambda item: item[0])
            for key, cap in sortedCaptions:
                self.addEntry(KeyType.Caption, key, cap)

        if text := FileTypeSelector.loadCaptionTxt(currentFile):
            self.addEntry(KeyType.TextFile, "", text, deletable=False)

        self._needsReload = False
        self.btnSaveAll.setChanged(False)
        self._updateTabOrder()

        QTimer.singleShot(DELAY_SCROLL, lambda: scrollBar.setValue(scrollPos))

    def addEntry(self, keyType: KeyType, keyName: str, text: str, deletable=True):
        entry = CaptionEntry(self, keyType, keyName, deletable)
        self._layoutEntries.addWidget(entry)
        entry.text = text

        entry.deleteClicked.connect(self._removeEntry)

        entry.textField.textChanged.connect(self._onEdited)
        entry.textField.focusReceived.connect(self._scrollToTextField)
        entry.textField.save.connect(self.saveAll)

        # Initial loading needs another size update to work consistently
        QTimer.singleShot(DELAY_RESIZE2, entry.textField._resizeToContent)
        return entry


    def _updateTabOrder(self):
        entries = self.entries
        try:
            lastEntry = next(entries)
            for entry in entries:
                self.setTabOrder(lastEntry.textField, entry.textField)
                lastEntry = entry

            self.setTabOrder(lastEntry.textField, self.addEntrySelector.cboType)
        except StopIteration:
            pass

        self.setTabOrder(self.addEntrySelector.cboType, self.addEntrySelector.cboKey)
        self.setTabOrder(self.addEntrySelector.cboKey, self.btnAddEntry)
        self.setTabOrder(self.btnAddEntry, self.btnReloadAll)
        self.setTabOrder(self.btnReloadAll, self.btnSaveAll)

    @Slot()
    def _updateHighlight(self):
        if self.ctx.currentWidget() is not self:
            self._needsHighlight = True
            return

        self._needsHighlight = False
        for entry in self.entries:
            entry.textField.updateHighlight()


    @Slot()
    def _addNewEntry(self):
        keyName = self.addEntrySelector.name.strip()
        keyType = TYPE_MAP[self.addEntrySelector.type]
        jsonType = (keyType != KeyType.TextFile)

        if jsonType and not keyName:
            self.statusBar.showColoredMessage("Empty key", False)
            return

        if any(entry.keyType == keyType and entry.keyName == keyName for entry in self.entries):
            self.statusBar.showColoredMessage("Key already exists", False)
            return

        self.addEntrySelector.name = ""

        entry = self.addEntry(keyType, keyName, "", deletable=jsonType)
        entry.edited = True
        entry.textField.setFocus()
        self._updateTabOrder()
        self.btnSaveAll.setChanged(True)

        scrollBar = self._scrollArea.verticalScrollBar()
        QTimer.singleShot(DELAY_SCROLL, lambda: scrollBar.setValue(scrollBar.height() + 1000))

    @Slot()
    def _removeEntry(self, entry: CaptionEntry):
        self._layoutEntries.removeWidget(entry)
        entry.deleteLater()
        self.btnSaveAll.setChanged(True)

    @Slot()
    def _onEdited(self):
        self.btnSaveAll.setChanged(True)

    @Slot()
    def _scrollToTextField(self, textEdit: AutoSizeTextEdit):
        self._scrollArea.ensureWidgetVisible(textEdit.parentWidget())


    @Slot()
    def saveAll(self):
        currentFile = self.ctx.tab.filelist.getCurrentFile()
        if not currentFile:
            self.statusBar.showColoredMessage("Failed to save caption list: Path is empty", False)
            return

        jsonModTime, txtModTime = self.getFileModTime(currentFile)
        if self._jsonModTime != jsonModTime or self._txtModTime != txtModTime:
            if not self._askOverwrite():
                self.statusBar.showColoredMessage("Saving aborted", False)
                return

        captionFile = CaptionFile(currentFile)
        jsonExists = os.path.exists(captionFile.jsonPath)

        if jsonExists and not captionFile.loadFromJson():
            msg = f"Failed to save caption list: Could not load existing captions from '{captionFile.jsonPath}'"
            self.statusBar.showColoredMessage(msg, False, 0)
            print(msg)
            return

        saveStates = []

        tags: dict[str, str] = dict()
        captions: dict[str, str] = dict()
        for entry in self.entries:
            if not entry.text:
                continue

            entry.edited = False
            match entry.keyType:
                case KeyType.Tags:
                    tags[entry.keyName] = entry.text
                case KeyType.Caption:
                    captions[entry.keyName] = entry.text
                case KeyType.TextFile:
                    FileTypeSelector.saveCaptionTxt(currentFile, entry.text)
                    saveStates.append(f"TXT File")

        if jsonExists or tags or captions:
            captionFile.tags = tags
            captionFile.captions = captions
            captionFile.saveToJson()

            print(f"Saved caption to file: {captionFile.jsonPath}")
            saveStates.append(f"JSON File ({len(tags)} Tags, {len(captions)} Captions)")

        if not saveStates:
            self.statusBar.showColoredMessage("Nothing to write", True)
            return

        msg = "Saved captions to " + ", ".join(reversed(saveStates))
        self.statusBar.showColoredMessage(msg, True)
        print(msg)

        self._jsonModTime, self._txtModTime = self.getFileModTime(currentFile)
        self.btnSaveAll.setChanged(False)
        self.ctx.tab.filelist.setData(currentFile, DataKeys.CaptionState, DataKeys.IconStates.Saved)


    def _askOverwrite(self) -> bool:
        text = "The caption files were changed since the last reload.\n" \
               "Do you really want to overwrite the caption files?"

        dialog = QtWidgets.QMessageBox(self)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Confirm Overwrite")
        dialog.setText(text)
        dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)

        return dialog.exec() == QtWidgets.QMessageBox.StandardButton.Yes



class CaptionEntry(QtWidgets.QWidget):
    deleteClicked = Signal(object)

    def __init__(self, captionList: CaptionList, keyType: KeyType, keyName: str, deletable=True):
        super().__init__()
        self.captionList = captionList

        self.keyType: KeyType = keyType
        self.keyName: str = keyName

        self.edited = False

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnMinimumWidth(1, 220)
        layout.setColumnMinimumWidth(2, 12)
        layout.setColumnStretch(3, 1)

        if deletable:
            btnDelete = qtlib.BubbleRemoveButton()
            btnDelete.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btnDelete.clicked.connect(self._deleteClicked)
            layout.addWidget(btnDelete, 0, 0, Qt.AlignmentFlag.AlignTop)
        else:
            layout.setColumnMinimumWidth(0, 18)

        keyText = f"{keyType.value}.{keyName}" if keyName else keyType.value
        self.txtKey = QtWidgets.QLabel(keyText)
        self.txtKey.setTextFormat(Qt.TextFormat.PlainText)
        self.txtKey.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        qtlib.setMonospace(self.txtKey)
        self._setKeyColor(self.txtKey, keyType)
        layout.addWidget(self.txtKey, 0, 1, Qt.AlignmentFlag.AlignTop)

        separator = SEPARATORS[keyType]
        autoCompleteSources = [captionList.ctx.groupAutoCompleteSource, getAutoCompleteSource(AutoCompleteSource.Type.Csv)]
        self.txtCaption = AutoSizeTextEdit(captionList.ctx.highlight, separator, autoCompleteSources)
        qtlib.setMonospace(self.txtCaption)
        self.txtCaption.textChanged.connect(self._setEdited)
        layout.addWidget(self.txtCaption, 0, 3, Qt.AlignmentFlag.AlignTop)

        separatorLine = QtWidgets.QFrame()
        separatorLine.setFrameStyle(QtWidgets.QFrame.Shape.HLine | QtWidgets.QFrame.Shadow.Sunken)
        layout.addWidget(separatorLine, 1, 0, 1, 4)
        layout.setRowMinimumHeight(1, 12)

        self.setLayout(layout)

    @staticmethod
    def _setKeyColor(txtKey: QtWidgets.QLabel, keyType: KeyType):
        match keyType:
            case KeyType.Tags:     keyColor = "#70C0C0"
            case KeyType.Caption:  keyColor = "#C0C070"
            case KeyType.TextFile: keyColor = "#C070C0"

        keyColor = colorlib.getHighlightColor(keyColor)
        keyPalette = txtKey.palette()
        keyPalette.setColor(QtGui.QPalette.ColorRole.WindowText, keyColor)
        txtKey.setPalette(keyPalette)


    @Slot()
    def _setEdited(self):
        self.edited = True

    @Slot()
    def _deleteClicked(self):
        self.deleteClicked.emit(self)


    @property
    def textField(self) -> AutoSizeTextEdit:
        return self.txtCaption

    @property
    def key(self):
        return self.txtKey.text()

    @property
    def text(self):
        return self.txtCaption.toPlainText()

    @text.setter
    def text(self, text: str):
        with QSignalBlocker(self.txtCaption):
            self.txtCaption.setPlainText(text)
            self.txtCaption._onTextChanged()



class AutoSizeTextEdit(BorderlessNavigationTextEdit):
    focusReceived = Signal(object)
    save = Signal()

    def __init__(self, highlight: CaptionHighlight, separator: str, autoCompleteSources: list[AutoCompleteSource] = []):
        super().__init__(separator, autoCompleteSources)
        self.highlight = highlight

        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.textChanged.connect(self._onTextChanged)
        self.verticalScrollBar().valueChanged.connect(self._scrollTop)

    def updateHighlight(self):
        self.highlight.highlight(self.toPlainText(), self.separator, self)

    @Slot()
    def _onTextChanged(self):
        self.updateHighlight()
        QTimer.singleShot(DELAY_RESIZE, self._resizeToContent)

    @Slot()
    def _resizeToContent(self):
        with QSignalBlocker(self):
            doc = self.document()
            doc.setDocumentMargin(0)
            lines = doc.size().height() * 1.07
            qtlib.setTextEditHeight(self, lines)

            self.verticalScrollBar().setValue(0)

    @Slot()
    def _scrollTop(self):
        scrollBar = self.verticalScrollBar()
        if scrollBar.value() > 0:
            scrollBar.setValue(0)


    @override
    def wheelEvent(self, e: QtGui.QWheelEvent):
        e.ignore()

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if (event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
            and not (self.completer and self.completer.isActive())
        ):
            event.ignore()
            return

        super().keyPressEvent(event)

    @override
    def focusInEvent(self, e: QtGui.QFocusEvent):
        super().focusInEvent(e)

        # Don't move cursor when autocomplete popup was closed
        if e.reason() != Qt.FocusReason.PopupFocusReason:
            self.moveCursor(QtGui.QTextCursor.MoveOperation.End)

        self.setActivePalette(True)
        self.focusReceived.emit(self)

    @override
    def focusOutEvent(self, e: QtGui.QFocusEvent):
        super().focusOutEvent(e)
        self.moveCursor(QtGui.QTextCursor.MoveOperation.End) # Clear selection
        self.setActivePalette(False)
