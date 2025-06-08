import logging
logging.basicConfig(level=logging.INFO)

import sys, os
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, Slot, QPoint, QThreadPool
from config import Config
from ui import aux_window
from ui.tab import ImgTab
import lib.qtlib as qtlib


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

        self._previousTab: ImgTab | None = None
        self._fullscreenTab: ImgTab | None = None
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
    def addTab(self) -> ImgTab:
        if self._fullscreenTab:
            self.toggleFullscreen()

        tab = ImgTab(self)
        tab.tabTitleChanged.connect(self.updateTitle)
        index = self.tabWidget.addTab(tab, ImgTab.EMPTY_TAB_TITLE)
        self.tabWidget.setCurrentIndex(index)
        tab.imgview.setFocus()
        return tab

    @property
    def currentTab(self) -> ImgTab:
        if self._fullscreenTab:
            return self._fullscreenTab
        return self.tabWidget.currentWidget()

    @property
    def previousTab(self) -> ImgTab | None:
        "The previous tab is updated when the tab is changed. This property is only available while initializing a new tab."
        return self._previousTab

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
        tab: ImgTab = self.tabWidget.widget(index)
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

        self._previousTab = tab

        self.toolbar.setTool(tab.toolName if tab else None)
        self.updateTitle(self.tabWidget.tabText(index))


    @Slot()
    def setTool(self, toolName: str):
        if self._fullscreenTab:
            self._fullscreenTab.setTool(toolName)
        else:
            self.currentTab.setTool(toolName)
        self.toolbar.setTool(toolName)

    @Slot()
    def updateTitle(self, filename: str | None):
        title = Config.windowTitle
        if filename and filename != ImgTab.EMPTY_TAB_TITLE:
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
            case "stats":
                from stats.stats_container import StatsContainer
                return StatsContainer
            case "batch":
                from batch.batch_container import BatchContainer
                return BatchContainer
            case "caption":
                from caption.caption_container import CaptionContainer
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

    def showAuxWindow(self, winName: str, tab: ImgTab | None = None):
        win = self.auxWindows.get(winName)
        if not win:
            self.toggleAuxWindow(winName)

        if tab:
            return tab.getWindowContent(winName)
        return self.currentTab.getWindowContent(winName)

    @Slot()
    def onAuxWindowClosed(self, win: aux_window.AuxiliaryWindow) -> None:
        winName = win.configKey
        self.toolbar.setWindowToggleChecked(winName, False)
        win.deleteLater()
        self.auxWindows.pop(winName, None)


    def closeEvent(self, event):
        QThreadPool.globalInstance().clear()

        from gallery.thumbnail_cache import ThumbnailCache
        ThumbnailCache.shutdown()

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

        actOpen = QtGui.QAction("&Open...", self)
        actOpen.setShortcutContext(Qt.ApplicationShortcut)
        actOpen.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_O))
        actOpen.triggered.connect(self.openFile)
        self.addAction(actOpen)

        actOpenDir = QtGui.QAction("&Open Folder...", self)
        actOpenDir.setShortcutContext(Qt.ApplicationShortcut)
        actOpenDir.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.SHIFT | Qt.Key_O))
        actOpenDir.triggered.connect(self.openDir)
        self.addAction(actOpenDir)

        self.addSeparator()

        actFullscreen = QtGui.QAction("Toggle &Fullscreen", self)
        actFullscreen.setShortcutContext(Qt.ApplicationShortcut)
        actFullscreen.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_F))
        actFullscreen.triggered.connect(mainWindow.toggleFullscreen)
        self.addAction(actFullscreen)

        actPrevImage = QtGui.QAction("Previous Image", self)
        actPrevImage.setShortcutContext(Qt.ApplicationShortcut)
        actPrevImage.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_PageUp))
        actPrevImage.triggered.connect(lambda: self.changeImage(False))
        self.addAction(actPrevImage)

        actNextImage = QtGui.QAction("Next Image", self)
        actNextImage.setShortcutContext(Qt.ApplicationShortcut)
        actNextImage.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_PageDown))
        actNextImage.triggered.connect(lambda: self.changeImage(True))
        self.addAction(actNextImage)

        self.addSeparator()

        actAddTab = QtGui.QAction("New &Tab", self)
        actAddTab.setShortcutContext(Qt.ApplicationShortcut)
        actAddTab.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_T))
        actAddTab.triggered.connect(mainWindow.addTab)
        self.addAction(actAddTab)

        actSwitchTab = QtGui.QAction("Switch Tab", self)
        actSwitchTab.setShortcutContext(Qt.ApplicationShortcut)
        actSwitchTab.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_Tab))
        actSwitchTab.triggered.connect(mainWindow.switchTab)
        self.addAction(actSwitchTab)

        actCloseTab = QtGui.QAction("Close Tab", self)
        actCloseTab.setShortcutContext(Qt.ApplicationShortcut)
        actCloseTab.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_W))
        actCloseTab.triggered.connect(self.closeTabWithConfirmation)
        self.addAction(actCloseTab)

        self.addSeparator()

        self.addMenu(self._buildToolsSubmenu(mainWindow))

        self.addSeparator()

        actModelConfig = QtGui.QAction("Model Settings...", self)
        actModelConfig.triggered.connect(self.showModelSettings)
        self.addAction(actModelConfig)

        actShowHostWin = QtGui.QAction("Hosts...", self)
        actShowHostWin.setShortcutContext(Qt.ApplicationShortcut)
        actShowHostWin.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_H))
        actShowHostWin.triggered.connect(self.showHostsWin)
        self.addAction(actShowHostWin)

        actClearVram = QtGui.QAction("Clear V&RAM", self)
        actClearVram.setShortcutContext(Qt.ApplicationShortcut)
        actClearVram.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_R))
        actClearVram.triggered.connect(self.clearVram)
        self.addAction(actClearVram)

        actKillInference = QtGui.QAction("Terminate Inference", self)
        actKillInference.triggered.connect(self.killInference)
        self.addAction(actKillInference)

        self.addSeparator()

        actQuit = QtGui.QAction("&Quit", self)
        actQuit.setShortcutContext(Qt.ApplicationShortcut)
        actQuit.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_Q))
        actQuit.triggered.connect(self.quitWithConfirmation)
        self.addAction(actQuit)

    def _buildToolsSubmenu(self, mainWindow: MainWindow) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu("Tools")

        for i, tool in enumerate(("view", "slideshow", "measure", "compare", "crop", "scale", "mask")):
            act = QtGui.QAction(tool.capitalize(), self)
            act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            act.setShortcut(QtGui.QKeySequence.fromString(f"Ctrl+{i+1}"))
            act.triggered.connect(lambda checked, tool=tool: mainWindow.setTool(tool))
            menu.addAction(act)

        return menu


    @Slot()
    def openFile(self):
        path, filter = QtWidgets.QFileDialog.getOpenFileName(self, "Open File")
        self.open(path)

    @Slot()
    def openDir(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Open Folder")
        self.open(path)

    def open(self, path: str | None):
        if not path:
            return

        tabWidget = self.mainWindow.tabWidget
        tabTitle = tabWidget.tabText(tabWidget.currentIndex())

        if tabTitle == ImgTab.EMPTY_TAB_TITLE:
            tab = self.mainWindow.currentTab
        else:
            tab = self.mainWindow.addTab()
        tab.filelist.load(path)


    @Slot()
    def clearVram(self):
        from infer.inference import Inference
        if names := Inference().quitProcesses():
            names = ", ".join(names)
            self.mainWindow.currentTab.statusBar().showMessage(f"Inference process ended ({names})", 4000)

    @Slot()
    def killInference(self):
        from infer.inference import Inference
        if names := Inference().killProcesses():
            names = ", ".join(names)
            self.mainWindow.currentTab.statusBar().showMessage(f"Inference process killed ({names})", 4000)

    @Slot()
    def showModelSettings(self):
        from infer.model_settings import ModelSettingsWindow
        ModelSettingsWindow.openInstance(self.mainWindow)

    @Slot()
    def showHostsWin(self):
        from host.host_window import HostWindow
        HostWindow.openInstance(self.mainWindow)

    def changeImage(self, forward: bool):
        tab = self.mainWindow.currentTab
        if forward:
            tab.filelist.setNextFile()
        else:
            tab.filelist.setPrevFile()


    @Slot()
    def closeTabWithConfirmation(self):
        dialog = QtWidgets.QMessageBox(self.mainWindow)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Question)
        dialog.setWindowTitle("Confirm Close Tab")
        dialog.setText(f"Do you really want to close the current tab?")
        dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)

        if dialog.exec() == QtWidgets.QMessageBox.StandardButton.Yes:
            self.mainWindow.closeCurrentTab()

    @Slot()
    def quitWithConfirmation(self):
        dialog = QtWidgets.QMessageBox(self.mainWindow)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Question)
        dialog.setWindowTitle("Confirm Quit")
        dialog.setText(f"Do you really want to quit the application?")
        dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)

        if dialog.exec() == QtWidgets.QMessageBox.StandardButton.Yes:
            self.mainWindow.close()



class MainToolBar(QtWidgets.QToolBar):
    def __init__(self, mainWindow: MainWindow, menu: MainMenu):
        super().__init__("Main Toolbar")
        self.mainWindow = mainWindow
        self.setFloatable(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)

        self.actMenu = self.addAction("☰")
        self.actMenu.setMenu(menu)
        self.actMenu.triggered.connect(self.showMenu)

        self.addSeparator()

        self.buildToolButtons(mainWindow)
        self.setTool("view")

        self.addSeparator()

        self.windowToggles: dict[str, QtGui.QAction] = dict()
        self.addWindowToggle("gallery", mainWindow)
        self.addWindowToggle("stats", mainWindow)
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
            "scale":    self.addAction("Scale"),
            "mask":     self.addAction("Mask")
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
    os.environ["QT_SCALE_FACTOR"] = str(Config.guiScale)

    app = QtWidgets.QApplication([])
    QtGui.QPixmapCache.setCacheLimit(24)

    if Config.qtStyle:
        app.setStyle(Config.qtStyle)

    threadCount = QThreadPool.globalInstance().maxThreadCount()
    threadCount = max(threadCount // 2, 4)
    QThreadPool.globalInstance().setMaxThreadCount(threadCount)
    del threadCount

    win = MainWindow(app)
    win.show()
    loadInitialImage(win)
    restoreWindows(win)
    return app.exec()

if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)

    if not Config.load():
        sys.exit(1)

    exitCode = main()
    Config.save()
    sys.exit(exitCode)
