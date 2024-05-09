from PySide6 import QtWidgets
from PySide6.QtCore import Signal


class AuxiliaryWindow(QtWidgets.QMainWindow):
    closed = Signal()

    def __init__(self, title):
        super().__init__()
        self.setWindowTitle(title)
        self.tab = None

    
    def setupContent(self, tab) -> object:
        return None

    def teardownContent(self, content):
        pass
    

    def setTab(self, tab):
        if tab is self.tab:
            return
        self.tab = tab
        
        if content := self.takeCentralWidget():
            self.teardownContent(content)
        
        if tab:
            content = self.setupContent(tab)
            self.setCentralWidget(content)

    
    def closeEvent(self, event):
        if content := self.takeCentralWidget():
            self.teardownContent(content)

        self.tab = None
        super().closeEvent(event)
        self.closed.emit()


    def setDimensions(self, app, sizeX, sizeY, posX, posY):
        screenSize = app.primaryScreen().size()
        self.resize(screenSize.width() * sizeX, screenSize.height() * sizeY)
        self.move(screenSize.width() * posX, screenSize.height() * posY)
