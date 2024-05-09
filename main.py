import sys
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, Slot
from imgview import ImgView
from export import Export
from gallery import Gallery, GalleryWindow
from caption import CaptionWindow
from filelist import FileList
import os


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.galleryWindow = None
        self.captionWindow = None

        self.setWindowTitle("Image Compare")
        self.setAttribute(Qt.WA_QuitOnClose)
        self.buildTabs()
        self.buildMenu()
        self.buildToolbar()
        self.addTab()

        #self.setWindowState(Qt.WindowFullScreen)
        #self.setWindowState(Qt::WindowMaximized);
        #self.setWindowState(self.windowState() ^ Qt.WindowFullScreen)

    def buildTabs(self):
        btnAddTab = QtWidgets.QPushButton("Add Tab")
        btnAddTab.clicked.connect(self.addTab)

        self.tabWidget = QtWidgets.QTabWidget(self)
        self.tabWidget.setDocumentMode(True) # Removes border
        self.tabWidget.setTabsClosable(True)
        self.tabWidget.setCornerWidget(btnAddTab)
        self.tabWidget.currentChanged.connect(self.onTabChanged)
        self.tabWidget.tabCloseRequested.connect(self.closeTab)
        self.setCentralWidget(self.tabWidget)

    def buildMenu(self):
        actQuit = QtGui.QAction("&Quit", self)
        actQuit.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_Q))
        actQuit.triggered.connect(self.close)

        menuFile = self.menuBar().addMenu("&File")
        menuFile.addAction(actQuit)

        menuEdit = self.menuBar().addMenu("&Edit")

    def buildToolbar(self):
        toolbar = self.addToolBar("Tools")

        actView = toolbar.addAction("View")
        actView.triggered.connect(lambda: self.setTool("view"))

        actCompare = toolbar.addAction("Compare")
        actCompare.triggered.connect(lambda: self.setTool("compare"))

        actCrop = toolbar.addAction("Crop")
        actCrop.triggered.connect(lambda: self.setTool("crop"))

        toolbar.addSeparator()

        actToggleGallery = toolbar.addAction("Gallery")
        actToggleGallery.triggered.connect(self.toggleGallery)

        actToggleCaption = toolbar.addAction("Captions")
        actToggleCaption.triggered.connect(self.toggleCaptionWindow)


    @Slot()
    def addTab(self):
        tab = ImgTab(self.tabWidget)
        index = self.tabWidget.addTab(tab, "Empty")
        self.tabWidget.setCurrentIndex(index)

        # For debugging
        #tab.filelist.load("/home/rem/Pictures/red-tree-with-eyes.jpeg")

    @Slot()
    def closeTab(self, index):
        self.tabWidget.removeTab(index)
        if self.tabWidget.count() == 0:
            self.addTab()

    @Slot()
    def onTabChanged(self, index):
        tab = self.tabWidget.currentWidget()
        if self.galleryWindow:
            self.galleryWindow.setTab(tab)
        if self.captionWindow:
            self.captionWindow.setTab(tab)
        
    
    @Slot()
    def setTool(self, toolName: str):
        tab = self.tabWidget.currentWidget()
        tab.setTool(toolName)

    
    @Slot()
    def toggleGallery(self):
        # TODO: Keep GalleryWindow instance? Toggle via show/hide?
        if self.galleryWindow is None:
            self.galleryWindow = GalleryWindow()
            self.galleryWindow.setDimensions(self.app, 0.5, 0.5, 0.5, 0)
            self.galleryWindow.closed.connect(self.onGalleryClosed)
            self.galleryWindow.show()

            tab = self.tabWidget.currentWidget()
            self.galleryWindow.setTab(tab)
        else:
            self.galleryWindow.close()
    
    @Slot()
    def onGalleryClosed(self):
        self.galleryWindow = None

    
    @Slot()
    def toggleCaptionWindow(self):
        if self.captionWindow is None:
            self.captionWindow = CaptionWindow()
            self.captionWindow.setDimensions(self.app, 0.5, 0.5, 0.5, 0.5)
            self.captionWindow.closed.connect(self.onCaptionWindowClosed)
            self.captionWindow.show()

            tab = self.tabWidget.currentWidget()
            self.captionWindow.setTab(tab)
        else:
            self.captionWindow.close()

    @Slot()
    def onCaptionWindowClosed(self):
        self.captionWindow = None


    def closeEvent(self, event):
        if self.galleryWindow:
            self.galleryWindow.close()
        if self.captionWindow:
            self.captionWindow.close()



class ImgTab(QtWidgets.QMainWindow):
    def __init__(self, tabWidget):
        super().__init__()
        self.tabWidget = tabWidget
        self._index = -1 # Store index when fullscreen

        self.filelist = FileList()
        self.filelist.addListener(self)

        self.imgview = ImgView(self.filelist)
        self.export = Export()
        self.tools = {}
        self._toolbar = None
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
                return ViewTool()
            case "compare":
                from tools import CompareTool
                return CompareTool()
            case "crop":
                from tools import CropTool
                return CropTool(self.export)
        return None


    def toggleFullscreen(self):
        winState = self.windowState()
        if winState & Qt.WindowFullScreen:
            # Disable fullscreen
            index = self.tabWidget.insertTab(self._index, self, "Fullscreen")
            self.tabWidget.setCurrentIndex(index)
            self.onFileChanged(self.filelist.getCurrentFile())
            self._index = -1
        else:
            # Enable fullscreen
            self._index = self.tabWidget.indexOf(self)
            self.tabWidget.removeTab(self._index)
            self.setParent(None)

        self.imgview.setFocus()
        self.setWindowState(winState ^ Qt.WindowFullScreen)
        self.setVisible(True)


    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F:
            self.toggleFullscreen()




if __name__ == "__main__":
    app = QtWidgets.QApplication([])

    screenSize = app.primaryScreen().size()

    win = MainWindow(app)
    win.resize(screenSize.width()//2, screenSize.height()//2)
    win.move(0, 0)
    win.show()

    sys.exit(app.exec())
