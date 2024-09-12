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

        if not aux_window.loadWindowPos(self, "main", False):
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


    @Slot()
    def closeTab(self, index):
        # TODO: Proper cleanup, something's hanging there
        tab = self.tabWidget.widget(index)
        tab.imgview.tool.onDisabled(tab.imgview)
        self.tabWidget.removeTab(index)
        if self.tabWidget.count() == 0:
            self.addTab()
        tab.deleteLater()

    @Slot()
    def onTabChanged(self, index):
        tab = self.tabWidget.currentWidget()
        if self.galleryWindow:
            self.galleryWindow.setTab(tab)
        if self.captionWindow:
            self.captionWindow.setTab(tab)

        self.toolbar.setTool(tab.toolName if tab else None)
        
    
    @Slot()
    def setTool(self, toolName: str):
        tab = self.tabWidget.currentWidget()
        tab.setTool(toolName)
        self.toolbar.setTool(toolName)

    
    @Slot()
    def toggleGallery(self):
        # TODO: Keep GalleryWindow instance? Toggle via show/hide?
        if self.galleryWindow is None:
            from gallery import GalleryWindow
            self.galleryWindow = GalleryWindow()
            self.galleryWindow.closed.connect(self.onGalleryClosed)
            self.galleryWindow.show()

            tab = self.tabWidget.currentWidget()
            self.galleryWindow.setTab(tab)
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
            from batch import BatchWindow
            self.batchWindow = BatchWindow()
            self.batchWindow.closed.connect(self.onBatchWindowClosed)
            self.batchWindow.show()

            tab = self.tabWidget.currentWidget()
            self.batchWindow.setTab(tab)
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
            from caption import CaptionWindow
            self.captionWindow = CaptionWindow()
            self.captionWindow.closed.connect(self.onCaptionWindowClosed)
            self.captionWindow.show()

            tab = self.tabWidget.currentWidget()
            self.captionWindow.setTab(tab)
        else:
            self.captionWindow.close()

    @Slot()
    def onCaptionWindowClosed(self):
        self.toolbar.actToggleCaption.setChecked(False)
        self.captionWindow.deleteLater()
        self.captionWindow = None


    def closeEvent(self, event):
        aux_window.saveWindowPos(self, "main")
        if self.galleryWindow:
            self.galleryWindow.close()
        if self.batchWindow:
            self.batchWindow.close()
        if self.captionWindow:
            self.captionWindow.close()



class MainMenu(QtWidgets.QMenu):
    def __init__(self, mainWindow):
        super().__init__()

        actModelConfig = QtGui.QAction("Model Settings", self)

        actQuit = QtGui.QAction("&Quit", self)
        actQuit.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_Q))
        actQuit.triggered.connect(mainWindow.close)

        #menuFile = self.addMenu("&File")
        self.addAction(actModelConfig)
        self.addSeparator()
        self.addAction(actQuit)



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

        self.actToggleCaption = self.addAction("Captions")
        self.actToggleCaption.setCheckable(True)
        self.actToggleCaption.triggered.connect(mainWindow.toggleCaptionWindow)

        self.addWidget(qtlib.SpacerWidget())

        actClearModels = self.addAction("Clear VRAM")
        actClearModels.triggered.connect(self.clearModels)

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

    @Slot()
    def clearModels(self):
        from infer import Inference
        Inference().quitProcess()



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
        self.tools = {}
        self._toolbar = None
        self.toolName = None
        self.setTool("view")

        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.imgview)
        widget.setLayout(layout)
        self.setCentralWidget(widget)


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
        if toolName == "view":
                from tools import ViewTool
                return ViewTool(self)
        elif toolName == "slideshow":
                from tools import SlideshowTool
                return SlideshowTool(self)
        elif toolName == "measure":
                from tools import MeasureTool
                return MeasureTool(self)
        elif toolName == "compare":
                from tools import CompareTool
                return CompareTool(self)
        elif toolName == "crop":
                from tools import CropTool
                return CropTool(self)
        elif toolName == "mask":
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


    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F:
            self.toggleFullscreen()



class TabStatusBar(qtlib.ColoredMessageStatusBar):
    def __init__(self, tab):
        super().__init__()
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



def main() -> int:
    app = QtWidgets.QApplication([])
    win = MainWindow(app)
    win.show()

    if len(sys.argv) > 1:
        tab = win.tabWidget.currentWidget()
        tab.filelist.load(sys.argv[1])
    # else:
    #     tab = win.tabWidget.currentWidget()
    #     tab.filelist.load("/home/rem/Pictures/red-tree-with-eyes.jpeg")

    return app.exec()

if __name__ == "__main__":
    Config.load()
    exitCode = main()
    Config.save()
    sys.exit(exitCode)
