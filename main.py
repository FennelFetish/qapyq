import os
import sys
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, Slot, QPoint
from export import Export
from filelist import FileList
from imgview import ImgView
from config import Config
import qtlib
import aux_window

from typing import ForwardRef
ImgTab = ForwardRef('ImgTab')


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.galleryWindow = None
        self.batchWindow   = None
        self.captionWindow = None

        self.setWindowTitle("pyImgSet")
        self.setAttribute(Qt.WA_QuitOnClose)

        self.menu = MainMenu(self)
        self.toolbar = MainToolBar(self, self.menu)
        self.addToolBar(self.toolbar)

        self.buildTabs()
        self.addTab()

        self._fullscreenTab = None

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
        tab = ImgTab(self.tabWidget)
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
        for win in [self.galleryWindow, self.batchWindow, self.captionWindow]:
            if win:
                win.setTab(tab)

        self.toolbar.setTool(tab.toolName if tab else None)
        
    
    @Slot()
    def setTool(self, toolName: str):
        self.currentTab.setTool(toolName)
        self.toolbar.setTool(toolName)

    
    @Slot()
    def toggleFullscreen(self):
        if self._fullscreenTab:
            self._fullscreenTab.toggleFullscreen()
            self._fullscreenTab = None
        else:
            self._fullscreenTab = self.currentTab
            self._fullscreenTab.toggleFullscreen()

    
    @Slot()
    def toggleGallery(self):
        if self.galleryWindow is None:
            from gallery import Gallery
            self.galleryWindow = aux_window.AuxiliaryWindow(self, Gallery, "Gallery", "gallery")
            self.galleryWindow.closed.connect(self.onGalleryClosed)
            self.galleryWindow.show()

            self.galleryWindow.setTab(self.currentTab)
            self.toolbar.actToggleGallery.setChecked(True)
        else:
            self.galleryWindow.close()
    
    @Slot()
    def onGalleryClosed(self):
        self.toolbar.actToggleGallery.setChecked(False)
        self.galleryWindow.deleteLater()
        self.galleryWindow = None


    @Slot()
    def toggleBatchWindow(self):
        if self.batchWindow is None:
            from batch import BatchContainer
            self.batchWindow = aux_window.AuxiliaryWindow(self, BatchContainer, "Batch", "batch")
            self.batchWindow.closed.connect(self.onBatchWindowClosed)
            self.batchWindow.show()

            self.batchWindow.setTab(self.currentTab)
            self.toolbar.actToggleBatch.setChecked(True)
        else:
            self.batchWindow.close()
    
    @Slot()
    def onBatchWindowClosed(self):
        self.toolbar.actToggleBatch.setChecked(False)
        self.batchWindow.deleteLater()
        self.batchWindow = None

    
    @Slot()
    def toggleCaptionWindow(self):
        if self.captionWindow is None:
            from caption import CaptionContainer
            self.captionWindow = aux_window.AuxiliaryWindow(self, CaptionContainer, "Caption", "caption")
            self.captionWindow.closed.connect(self.onCaptionWindowClosed)
            self.captionWindow.show()

            self.captionWindow.setTab(self.currentTab)
            self.toolbar.actToggleCaption.setChecked(True)
        else:
            self.captionWindow.close()

    @Slot()
    def onCaptionWindowClosed(self):
        self.toolbar.actToggleCaption.setChecked(False)
        self.captionWindow.deleteLater()
        self.captionWindow = None


    def closeEvent(self, event):
        aux_window.saveWindowPos(self, "main")
        if self._fullscreenTab:
            self._fullscreenTab.close()
        
        openWindows = []
        for win in [self.galleryWindow, self.batchWindow, self.captionWindow]:
            if win:
                openWindows.append(win.configKey)
                win.close()
        Config.windowOpen = openWindows

        from infer.model_settings import ModelSettingsWindow
        ModelSettingsWindow.closeInstance()



class MainMenu(QtWidgets.QMenu):
    def __init__(self, mainWindow: MainWindow):
        super().__init__()

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
        ModelSettingsWindow.openInstance(self)



class MainToolBar(QtWidgets.QToolBar):
    def __init__(self, mainWindow, menu):
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

        self.actToggleGallery = self.addAction("Gallery")
        self.actToggleGallery.setCheckable(True)
        self.actToggleGallery.triggered.connect(mainWindow.toggleGallery)

        self.actToggleBatch = self.addAction("Batch")
        self.actToggleBatch.setCheckable(True)
        self.actToggleBatch.triggered.connect(mainWindow.toggleBatchWindow)

        self.actToggleCaption = self.addAction("Caption")
        self.actToggleCaption.setCheckable(True)
        self.actToggleCaption.triggered.connect(mainWindow.toggleCaptionWindow)

        self.addWidget(qtlib.SpacerWidget())

        actAddTab = self.addAction("Add Tab")
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

    @Slot()
    def showMenu(self):
        widget = self.widgetForAction(self.actMenu)
        pos = widget.mapToGlobal(QPoint(0, widget.height()))
        self.actMenu.menu().popup(pos)



class ImgTab(QtWidgets.QMainWindow):
    def __init__(self, tabWidget):
        super().__init__()
        self.tabWidget = tabWidget
        self._index = -1 # Store index when fullscreen
        self.setWindowTitle("PyImgSet Tab")

        self.setStatusBar(TabStatusBar(self))

        self.filelist = FileList()
        self.filelist.addListener(self)

        self.imgview = ImgView(self.filelist)
        self.export = Export()
        self._windowContent: dict[str, QtWidgets.QWidget] = dict()

        self.tools = dict()
        self._toolbar = None
        self.toolName = None
        self.setTool("view")

        self.setCentralWidget(self.imgview)


    def onFileChanged(self, currentFile):
        idx = self.tabWidget.indexOf(self)
        name = os.path.basename(currentFile) if currentFile else "Empty"
        self.tabWidget.setTabText(idx, name)

    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)


    def setTool(self, toolName: str):
        if toolName not in self.tools:
            self.tools[toolName] = self.createTool(toolName)
        self.imgview.tool = self.tools[toolName]
        self.toolName = toolName

        # Replace toolbar
        if self._toolbar:
            self.removeToolBar(self._toolbar)
        self._toolbar = self.imgview.tool.getToolbar()
        if self._toolbar:
            self.addToolBar(Qt.RightToolBarArea, self._toolbar)
            self._toolbar.show()

    def createTool(self, toolName: str):
        match toolName:
            case "view":
                from tools import ViewTool
                return ViewTool(self)
            case "slideshow":
                from tools import SlideshowTool
                return SlideshowTool(self)
            case "measure":
                from tools import MeasureTool
                return MeasureTool(self)
            case "compare":
                from tools import CompareTool
                return CompareTool(self)
            case "crop":
                from tools import CropTool
                return CropTool(self)
            case "mask":
                from tools import MaskTool
                return MaskTool(self)
        
        print("Invalid tool:", toolName)
        return None

    def getTool(self, toolName: str):
        if toolName in self.tools:
            return self.tools[toolName]
        else:
            return None

    def getCurrentTool(self):
        return self.imgview.tool


    def getWindowContent(self, windowName: str):
        return self._windowContent.get(windowName, None)

    def setWindowContent(self, windowName: str, content: QtWidgets.QWidget):
        if windowName in self._windowContent:
            self._windowContent[windowName].deleteLater()
        self._windowContent[windowName] = content


    def toggleFullscreen(self):
        winState = self.windowState()
        if winState & Qt.WindowFullScreen:
            # Disable fullscreen
            index = self.tabWidget.insertTab(self._index, self, "Fullscreen")
            self.tabWidget.setCurrentIndex(index)
            self.onFileChanged(self.filelist.getCurrentFile())
            self._index = -1
            self.imgview.tool.onFullscreen(False)
        else:
            # Enable fullscreen
            self._index = self.tabWidget.indexOf(self)
            self.tabWidget.removeTab(self._index)
            self.setParent(None)
            self.imgview.tool.onFullscreen(True)

        self.imgview.setFocus()
        self.setWindowState(winState ^ Qt.WindowFullScreen)
        self.setVisible(True)

    
    def onTabClosed(self):
        self.imgview.tool.onDisabled(self.imgview)

        for winContent in self._windowContent.values():
            winContent.deleteLater()



class TabStatusBar(qtlib.ColoredMessageStatusBar):
    def __init__(self, tab):
        super().__init__("border-top: 1px outset black")
        self.tab = tab
        self.setSizeGripEnabled(False)
        self.setContentsMargins(6, 0, 6, 0)

        self._lblMouseCoords = QtWidgets.QLabel()
        self._lblMouseCoords.setFixedWidth(100)
        self.addPermanentWidget(self._lblMouseCoords)

        self._lblImgSize = QtWidgets.QLabel()
        self.addPermanentWidget(self._lblImgSize)

    def setImageSize(self, width, height):
        self._lblImgSize.setText(f"W: {width}  H: {height}")

    def setMouseCoords(self, x, y):
        self._lblMouseCoords.setText(f"X: {x}  Y: {y}")



def loadInitialImage(win: MainWindow):
    loadPath = sys.argv[1] if len(sys.argv) > 1 else Config.pathDebugLoad
    if loadPath:
        tab: ImgTab = win.tabWidget.currentWidget()
        tab.filelist.load(loadPath)

def restoreWindows(win: MainWindow):
    if "gallery" in Config.windowOpen:
        win.toggleGallery()
    if "batch" in Config.windowOpen:
        win.toggleBatchWindow()
    if "caption" in Config.windowOpen:
        win.toggleCaptionWindow()

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
