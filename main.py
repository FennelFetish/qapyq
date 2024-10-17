import sys
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, Slot, QPoint
from config import Config
from ui import aux_window
from ui.tab import ImgTab
import lib.qtlib as qtlib


EMPTY_TAB_TITLE = "Empty"


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        
        self.setAttribute(Qt.WA_QuitOnClose)
        self.setWindowIcon(QtGui.QPixmap(Config.windowIcon))
        self.updateTitle(None)

        self.auxWindows: dict[str, aux_window.AuxiliaryWindow] = dict()
        self.menu = MainMenu(self)
        self.toolbar = MainToolBar(self, self.menu)
        self.addToolBar(self.toolbar)

        self._fullscreenTab = None
        self.buildTabs()
        self.addTab()

        if not aux_window.loadWindowPos(self, "main"):
            aux_window.setWindowDimensions(self, 0.5, 1, 0, 0)


    def buildTabs(self):
        self.tabWidget = QtWidgets.QTabWidget(self)
        self.tabWidget.setDocumentMode(True) # Removes border
        self.tabWidget.setTabBarAutoHide(True)
        self.tabWidget.setTabsClosable(True)
        self.tabWidget.setMovable(True)
        self.tabWidget.setElideMode(Qt.ElideMiddle)
        self.tabWidget.currentChanged.connect(self.onTabChanged)
        self.tabWidget.tabCloseRequested.connect(self.closeTab)
        self.setCentralWidget(self.tabWidget)

    @Slot()
    def addTab(self):
        if self._fullscreenTab:
            self.toggleFullscreen()

        tab = ImgTab(self.tabWidget)
        tab.tabTitleChanged.connect(self.updateTitle)
        index = self.tabWidget.addTab(tab, "Empty")
        self.tabWidget.setCurrentIndex(index)
        tab.imgview.setFocus()

    @property
    def currentTab(self) -> ImgTab:
        return self.tabWidget.currentWidget()

    @Slot()
    def switchTab(self):
        fullscreen = False
        if self._fullscreenTab:
            fullscreen = True
            self.toggleFullscreen()
        
        index = self.tabWidget.currentIndex()
        index = (index + 1) % self.tabWidget.count()
        self.tabWidget.setCurrentIndex(index)

        if fullscreen:
            self.toggleFullscreen()

    @Slot()
    def closeCurrentTab(self):
        if self._fullscreenTab:
            self.toggleFullscreen()
        self.closeTab( self.tabWidget.currentIndex() )

    @Slot()
    def closeTab(self, index):
        # TODO: Proper cleanup, something's hanging there
        tab = self.tabWidget.widget(index)
        tab.onTabClosed()
        
        self.tabWidget.removeTab(index)
        if self.tabWidget.count() == 0:
            self.addTab()
        tab.deleteLater()

    @Slot()
    def onTabChanged(self, index):
        tab = self.currentTab
        for win in self.auxWindows.values():
            win.setTab(tab)

        self.toolbar.setTool(tab.toolName if tab else None)
        self.updateTitle(self.tabWidget.tabText(index))
    
    
    @Slot()
    def setTool(self, toolName: str):
        self.currentTab.setTool(toolName)
        self.toolbar.setTool(toolName)

    @Slot()
    def updateTitle(self, filename: str | None):
        title = Config.windowTitle
        if filename and filename != EMPTY_TAB_TITLE:
            title = f"{filename} - {title}"
        self.setWindowTitle(title)

    
    @Slot()
    def toggleFullscreen(self):
        if self._fullscreenTab:
            self._fullscreenTab.toggleFullscreen()
            self._fullscreenTab = None
        else:
            self._fullscreenTab = self.currentTab
            self._fullscreenTab.toggleFullscreen()


    @staticmethod
    def getWindowClass(winName: str) -> type:
        match winName:
            case "gallery":
                from gallery import Gallery
                return Gallery
            case "batch":
                from batch import BatchContainer
                return BatchContainer
            case "caption":
                from caption import CaptionContainer
                return CaptionContainer
        return None

    def toggleAuxWindow(self, winName: str):
        if win := self.auxWindows.get(winName):
            win.close()
            return
        
        winClass = self.getWindowClass(winName)
        win = aux_window.AuxiliaryWindow(self, winClass, winName.capitalize(), winName)
        win.closed.connect(self.onAuxWindowClosed)
        win.show()
        win.setTab(self.currentTab)
        self.auxWindows[winName] = win
        
        self.toolbar.setWindowToggleChecked(winName, True)

    @Slot()
    def onAuxWindowClosed(self, win: aux_window.AuxiliaryWindow) -> None:
        winName = win.configKey
        self.toolbar.setWindowToggleChecked(winName, False)
        win.deleteLater()
        self.auxWindows.pop(winName, None)


    def closeEvent(self, event):
        aux_window.saveWindowPos(self, "main")
        if self._fullscreenTab:
            self._fullscreenTab.close()
        
        openWindows = []
        for win in list(self.auxWindows.values()):
            openWindows.append(win.configKey)
            win.close()
        Config.windowOpen = openWindows

        from infer.model_settings import ModelSettingsWindow
        ModelSettingsWindow.closeInstance()



class MainMenu(QtWidgets.QMenu):
    def __init__(self, mainWindow: MainWindow):
        super().__init__()
        self.mainWindow = mainWindow

        # https://doc.qt.io/qt-6/qt.html#Key-enum

        actFullscreen = QtGui.QAction("Toggle &Fullscreen", self)
        actFullscreen.setShortcutContext(Qt.ApplicationShortcut)
        actFullscreen.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_F))
        actFullscreen.triggered.connect(mainWindow.toggleFullscreen)

        # TODO: Don't focus MainWindow when using this shortcuts
        # actNextImage = QtGui.QAction("Next Image", self)
        # actNextImage.setShortcutContext(Qt.ApplicationShortcut)
        # actNextImage.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_PageUp))
        # actNextImage.triggered.connect(lambda: mainWindow.currentTab.filelist.setNextFile())

        # actPrevImage = QtGui.QAction("Previous Image", self)
        # actPrevImage.setShortcutContext(Qt.ApplicationShortcut)
        # actPrevImage.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_PageDown))
        # actPrevImage.triggered.connect(lambda: mainWindow.currentTab.filelist.setPrevFile())

        actAddTab = QtGui.QAction("New Tab", self)
        actAddTab.setShortcutContext(Qt.ApplicationShortcut)
        actAddTab.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_T))
        actAddTab.triggered.connect(mainWindow.addTab)

        actSwitchTab = QtGui.QAction("Switch Tab", self)
        actSwitchTab.setShortcutContext(Qt.ApplicationShortcut)
        actSwitchTab.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_Tab))
        actSwitchTab.triggered.connect(mainWindow.switchTab)

        actCloseTab = QtGui.QAction("Close Tab", self)
        actCloseTab.setShortcutContext(Qt.ApplicationShortcut)
        actCloseTab.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_W))
        actCloseTab.triggered.connect(mainWindow.closeCurrentTab)

        actClearVram = QtGui.QAction("Clear VRAM", self)
        actClearVram.triggered.connect(self.clearVram)

        actModelConfig = QtGui.QAction("Model Settings...", self)
        actModelConfig.triggered.connect(self.showModelSettings)
        
        actQuit = QtGui.QAction("&Quit", self)
        actQuit.setShortcutContext(Qt.ApplicationShortcut)
        actQuit.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_Q))
        actQuit.triggered.connect(mainWindow.close)

        self.addAction(actFullscreen)
        # self.addAction(actNextImage)
        # self.addAction(actPrevImage)
        self.addSeparator()
        self.addAction(actAddTab)
        self.addAction(actSwitchTab)
        self.addAction(actCloseTab)
        self.addSeparator()
        self.addAction(actModelConfig)
        self.addAction(actClearVram)
        self.addSeparator()
        self.addAction(actQuit)

    @Slot()
    def clearVram(self):
        from infer import Inference
        Inference().quitProcess()

    @Slot()
    def showModelSettings(self):
        from infer.model_settings import ModelSettingsWindow
        ModelSettingsWindow.openInstance(self.mainWindow)



class MainToolBar(QtWidgets.QToolBar):
    def __init__(self, mainWindow: MainWindow, menu: MainMenu):
        super().__init__("Main Toolbar")
        self.mainWindow = mainWindow
        self.setFloatable(False)
        self.setContextMenuPolicy(Qt.PreventContextMenu)

        self.actMenu = self.addAction("☰")
        self.actMenu.setMenu(menu)
        self.actMenu.triggered.connect(self.showMenu)

        self.addSeparator()

        self.buildToolButtons(mainWindow)
        self.setTool("view")

        self.addSeparator()

        self.windowToggles: dict[str, QtGui.QAction] = dict()
        self.addWindowToggle("gallery", mainWindow)
        self.addWindowToggle("batch", mainWindow)
        self.addWindowToggle("caption", mainWindow)

        self.addWidget(qtlib.SpacerWidget())

        actAddTab = self.addAction("New Tab")
        actAddTab.triggered.connect(mainWindow.addTab)

        winColor = QtWidgets.QApplication.palette().color(QtGui.QPalette.ColorRole.Window)
        colorBg = winColor.lighter().name()
        colorBorder = winColor.darker().name()
        self.setStyleSheet("QToolBar{border:0px;} ::separator{background-color: " + colorBg + "; border: 1px dotted " + colorBorder + "; height: 1px; width: 1px;}")

    def buildToolButtons(self, mainWindow):
        self._toolActions = {
            "view":     self.addAction("View"),
            "slideshow":self.addAction("Slideshow"),
            "measure":  self.addAction("Measure"),
            "compare":  self.addAction("Compare"),
            "crop":     self.addAction("Crop"),
            #"mask":     self.addAction("Mask")
        }

        for name, act in self._toolActions.items():
            act.setCheckable(True)
            act.triggered.connect(lambda act=act, name=name: mainWindow.setTool(name)) # Capture correct vars

    def setTool(self, toolName):
        for act in self._toolActions.values():
            act.setChecked(False)

        if toolName in self._toolActions:
            self._toolActions[toolName].setChecked(True)

    def addWindowToggle(self, winName: str, mainWindow: MainWindow) -> None:
        act = self.addAction(winName.capitalize())
        act.setCheckable(True)
        act.triggered.connect(lambda: mainWindow.toggleAuxWindow(winName))
        self.windowToggles[winName] = act

    def setWindowToggleChecked(self, winName, checked: bool) -> None:
        if act := self.windowToggles.get(winName):
            act.setChecked(checked)

    @Slot()
    def showMenu(self):
        widget = self.widgetForAction(self.actMenu)
        pos = widget.mapToGlobal(QPoint(0, widget.height()))
        self.actMenu.menu().popup(pos)



def loadInitialImage(win: MainWindow):
    loadPath = sys.argv[1] if len(sys.argv) > 1 else Config.pathDebugLoad
    if loadPath:
        tab: ImgTab = win.tabWidget.currentWidget()
        tab.filelist.load(loadPath)

def restoreWindows(win: MainWindow):
    for winName in Config.windowOpen:
        win.toggleAuxWindow(winName)

def main() -> int:
    app = QtWidgets.QApplication([])
    win = MainWindow(app)
    win.show()
    loadInitialImage(win)
    restoreWindows(win)
    return app.exec()

if __name__ == "__main__":
    Config.load()
    exitCode = main()
    Config.save()
    sys.exit(exitCode)
