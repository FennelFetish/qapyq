import os
from contextlib import contextmanager
from datetime import datetime
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal, Slot
from config import Config
from lib import qtlib


class BatchLogEntry(QtWidgets.QPlainTextEdit):
    log = Signal(str)
    release = Signal()

    def __init__(self, name: str):
        super().__init__()
        qtlib.setMonospace(self)
        self.setReadOnly(True)

        self.timestamp = datetime.now()
        self.name = name.lower()
        self.title = self.timestamp.strftime(f"{name} (%Y-%m-%d %H:%M:%S)")

        self.log.connect(self._addLog, Qt.ConnectionType.QueuedConnection)
        self.release.connect(self._onReleased, Qt.ConnectionType.QueuedConnection)

        self._indent = False
        self.done = False


    def __call__(self, line: str):
        if self._indent:
            line = "  " + line
        self.log.emit(line)

    @Slot()
    def _addLog(self, line: str):
        logScrollBar = self.verticalScrollBar()
        scrollDown = (logScrollBar.value() == logScrollBar.maximum())

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S  ")
        self.appendPlainText(timestamp + line)
        if scrollDown:
            logScrollBar.setValue(logScrollBar.maximum())

        print(line)

    @Slot()
    def _onReleased(self):
        self.done = True

    def saveLog(self, savePath: str):
        filter = "Log Files (*.log);;Text Files (*.txt)"

        filename = self.timestamp.strftime(f"batch_{self.name}_%Y-%m-%d_%H%M%S.log")
        path = os.path.join(savePath, filename)

        path, filter = QtWidgets.QFileDialog.getSaveFileName(self, "Choose target file", path, filter)
        if path:
            path = os.path.abspath(path)
            with open(path, 'w') as file:
                file.writelines(self.toPlainText())

    @contextmanager
    def indent(self):
        self._indent = True
        try:
            yield self
        finally:
            self._indent = False



class BatchLog(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self._savePath = Config.pathExport

        self.cboEntries = QtWidgets.QComboBox()
        self.cboEntries.currentIndexChanged.connect(self._onEntryChanged)

        self.btnSave = QtWidgets.QPushButton("Save Selected Log...")
        self.btnSave.setEnabled(False)
        self.btnSave.clicked.connect(self.saveCurrentEntry)

        self.btnClear = QtWidgets.QPushButton("Clear Finished")
        self.btnClear.setEnabled(False)
        self.btnClear.clicked.connect(self.clearEntries)

        self.stackLayout = QtWidgets.QStackedLayout()

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setRowStretch(0, 1)
        layout.setRowStretch(1, 0)

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnMinimumWidth(1, 180)
        layout.setColumnMinimumWidth(2, 180)

        layout.addWidget(self.cboEntries, 0, 0)
        layout.addWidget(self.btnSave, 0, 1)
        layout.addWidget(self.btnClear, 0, 2)
        layout.addLayout(self.stackLayout, 1, 0, 1, 3)
        self.setLayout(layout)


    def onFileChanged(self, currentFile):
        self._savePath = os.path.dirname(currentFile)


    @Slot()
    def _onEntryChanged(self, index: int):
        if entry := self.cboEntries.itemData(index):
            self.stackLayout.setCurrentWidget(entry)

    def addEntry(self, name: str) -> BatchLogEntry:
        self.btnSave.setEnabled(True)
        self.btnClear.setEnabled(True)

        entry = BatchLogEntry(name)
        self.stackLayout.addWidget(entry) # Add to stack first
        self.cboEntries.addItem(entry.title, entry)
        self.cboEntries.setCurrentIndex(self.cboEntries.count()-1)
        return entry

    @Slot()
    def clearEntries(self):
        for i in range(self.cboEntries.count()-1, -1, -1):
            entry: BatchLogEntry = self.cboEntries.itemData(i)
            if entry.done:
                self.cboEntries.removeItem(i)
                self.stackLayout.removeWidget(entry)
                entry.deleteLater()

        if self.cboEntries.count() == 0:
            self.btnSave.setEnabled(False)
            self.btnClear.setEnabled(False)

    @Slot()
    def saveCurrentEntry(self):
        entry: BatchLogEntry = self.cboEntries.currentData()
        if entry:
            entry.saveLog(self._savePath)


    def hasUnfinished(self):
        for i in range(self.cboEntries.count()):
            entry: BatchLogEntry = self.cboEntries.itemData(i)
            if not entry.done:
                return True
        return False
