from PySide6 import QtWidgets
from PySide6.QtCore import Signal
from config import Config


class AuxiliaryWindow(QtWidgets.QMainWindow):
    closed = Signal()

    def __init__(self, title, configKey):
        super().__init__()
        self.setWindowTitle(title)
        self.tab = None
        self._configKey = configKey
        loadWindowPos(self, configKey)

    
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
            content.deleteLater()
        
        if tab:
            content = self.setupContent(tab)
            self.setCentralWidget(content)

    
    def closeEvent(self, event):
        saveWindowPos(self, self._configKey)

        if content := self.takeCentralWidget():
            self.teardownContent(content)
            content.deleteLater()

        self.tab = None
        super().closeEvent(event)
        self.closed.emit()



def saveWindowPos(win, configKey):
    size, pos = win.size(), win.pos()
    Config.windowStates[configKey] = (size.width(), size.height(), pos.x(), pos.y())

def loadWindowPos(win, configKey, defaultOnFail=True):
    if configKey in Config.windowStates:
        w, h, x, y = Config.windowStates.get(configKey)
        win.resize(int(w), int(h))
        win.move(int(x), int(y))
        return True

    if defaultOnFail:
        setWindowDimensions(win, 0.5, 1.0, 0.5, 0.0)
    return False


def setWindowDimensions(win, sizeX, sizeY, posX, posY):
    app = QtWidgets.QApplication.instance()
    screenSize = app.primaryScreen().size()
    win.resize(screenSize.width() * sizeX, screenSize.height() * sizeY)
    win.move(screenSize.width() * posX, screenSize.height() * posY)
