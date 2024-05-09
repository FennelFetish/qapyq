from PySide6 import QtWidgets, QtGui


class Caption(QtWidgets.QWidget):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab


    def onFileChanged(self, currentFile):
        pass
    
    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)