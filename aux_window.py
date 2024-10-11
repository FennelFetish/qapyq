from PySide6 import QtWidgets
from PySide6.QtCore import Signal
from main import WINDOW_TITLE
from config import Config


class AuxiliaryWindow(QtWidgets.QMainWindow):
    closed = Signal()

    def __init__(self, parent, contentClass, title, configKey):
        super().__init__(parent)
        self.setWindowTitle(f"{title} - {WINDOW_TITLE}")
        self.contentClass = contentClass
        self.configKey = configKey
        self.tab = None
        
        if not loadWindowPos(self, configKey):
            setWindowDimensions(self, 0.5, 1.0, 0.5, 0.0)

    
    def setupContent(self, tab) -> object:
        return self.contentClass(tab)
    
    def removeContent(self):
        # Prevent deletion of content
        content = self.takeCentralWidget()
        if content:
            content.hide()
        
        if statusBar := self.statusBar():
            statusBar.setParent(None)
            self.setStatusBar(None)
            statusBar.hide()


    def setTab(self, tab):
        if tab is self.tab:
            return
        self.tab = tab

        self.removeContent()
        
        if tab:
            content = tab.getWindowContent(self.configKey)
            if not content:
                content = self.setupContent(tab)
                tab.setWindowContent(self.configKey, content)
            
            content.show()
            self.setCentralWidget(content)

            if hasattr(content, "statusBar"):
                content.statusBar.show()
                self.setStatusBar(content.statusBar)


    def closeEvent(self, event):
        saveWindowPos(self, self.configKey)
        self.removeContent()
        self.tab = None
        
        super().closeEvent(event)
        self.closed.emit()



def saveWindowPos(win, configKey):
    size, pos = win.size(), win.pos()
    Config.windowStates[configKey] = (size.width(), size.height(), pos.x(), pos.y())

def loadWindowPos(win, configKey):
    if configKey not in Config.windowStates:
        return False

    w, h, x, y = Config.windowStates.get(configKey)
    win.resize(int(w), int(h))
    win.move(int(x), int(y))
    return True


def setWindowDimensions(win, sizeX, sizeY, posX, posY):
    app = QtWidgets.QApplication.instance()
    screenSize = app.primaryScreen().size()
    win.resize(screenSize.width() * sizeX, screenSize.height() * sizeY)
    win.move(screenSize.width() * posX, screenSize.height() * posY)
