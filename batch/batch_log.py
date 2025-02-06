from datetime import datetime
import os
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal, Slot
from config import Config
from lib import qtlib


class BatchLog(QtWidgets.QWidget):
    log = Signal(str)

    def __init__(self):
        super().__init__()
        self._savePath = Config.pathExport

        self.txtLog = QtWidgets.QPlainTextEdit()
        qtlib.setMonospace(self.txtLog)
        self.txtLog.setReadOnly(True)

        self.btnClear = QtWidgets.QPushButton("Clear")
        self.btnClear.clicked.connect(lambda: self.txtLog.setPlainText(""))

        self.btnSave = QtWidgets.QPushButton("Save...")
        self.btnSave.clicked.connect(self.saveLog)

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setRowStretch(0, 1)
        layout.setRowStretch(1, 0)

        layout.addWidget(self.txtLog, 0, 0, 1, 2)
        layout.addWidget(self.btnClear, 1, 0)
        layout.addWidget(self.btnSave, 1, 1)
        self.setLayout(layout)

        self.log.connect(self.addLog, Qt.ConnectionType.BlockingQueuedConnection)


    def onFileChanged(self, currentFile):
        self._savePath = os.path.dirname(currentFile)


    @Slot()
    def addLog(self, line: str):
        logScrollBar = self.txtLog.verticalScrollBar()
        scrollDown = (logScrollBar.value() == logScrollBar.maximum())

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S  ")
        self.txtLog.appendPlainText(timestamp + line)
        if scrollDown:
            logScrollBar.setValue(logScrollBar.maximum())

        print(line)

    def emitLog(self, line: str):
        self.log.emit(line)


    @Slot()
    def saveLog(self):
        filter = "Log Files (*.log);;Text Files (*.txt)"

        filename = datetime.now().strftime("batch_%Y-%m-%d_%H%M%S.log")
        path = os.path.join(self._savePath, filename)

        path, filter = QtWidgets.QFileDialog.getSaveFileName(self, "Choose target file", path, filter)
        if path:
            path = os.path.abspath(path)
            with open(path, 'w') as file:
                file.writelines(self.txtLog.toPlainText())
