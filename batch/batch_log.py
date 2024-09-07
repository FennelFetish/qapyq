from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
from datetime import datetime
import os
import qtlib


class BatchLog(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.txtLog = QtWidgets.QPlainTextEdit()
        self.txtLog.setReadOnly(True)

        self.btnClear = QtWidgets.QPushButton("Clear")
        self.btnClear.clicked.connect(lambda: self.txtLog.setPlainText(""))

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.txtLog)
        layout.addWidget(self.btnClear)
        self.setLayout(layout)

    @Slot()
    def addLog(self, line):
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S  ")
        self.txtLog.appendPlainText(timestamp + line)
        print(line)
