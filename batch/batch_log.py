from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
from datetime import datetime
import os
from config import Config


class BatchLog(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self._savePath = Config.pathExport

        self.txtLog = QtWidgets.QPlainTextEdit()
        self.txtLog.setReadOnly(True)

        self.btnClear = QtWidgets.QPushButton("Clear")
        self.btnClear.clicked.connect(lambda: self.txtLog.setPlainText(""))

        self.btnSave = QtWidgets.QPushButton("Save...")
        self.btnSave.clicked.connect(self.saveLog)

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setRowStretch(0, 1)
        layout.setRowStretch(1, 0)

        layout.addWidget(self.txtLog, 0, 0, 1, 2)
        layout.addWidget(self.btnClear, 1, 0)
        layout.addWidget(self.btnSave, 1, 1)
        self.setLayout(layout)


    def onFileChanged(self, currentFile):
        self._savePath = os.path.dirname(currentFile)


    @Slot()
    def addLog(self, line):
        logScrollBar = self.txtLog.verticalScrollBar()
        scrollDown = (logScrollBar.value() == logScrollBar.maximum())

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S  ")
        self.txtLog.appendPlainText(timestamp + line)
        if scrollDown:
            logScrollBar.setValue(logScrollBar.maximum())
        
        print(line)

    @Slot()
    def saveLog(self):
        filter = "Log Files (*.log);;Text Files (*.txt)"

        path, filter = QtWidgets.QFileDialog.getSaveFileName(self, "Choose target file", self._savePath, filter)
        if path:
            with open(path, 'w') as file:
                file.writelines(self.txtLog.toPlainText())
