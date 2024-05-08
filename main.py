import sys
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, Slot
from imgview import ImgView
from export import Export
from gallery import Gallery, GalleryWindow
from filelist import FileList
import os


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.galleryWindow = None

        self.setWindowTitle("Image Compare")
        self.setAttribute(Qt.WA_QuitOnClose)
        self.buildTabs()
        self.buildMenu()
        self.buildToolbar()
        self.addTab()

        #self.setWindowState(Qt.WindowFullScreen)
        #self.setWindowState(Qt::WindowMaximized);
        #setWindowState(w.windowState() ^ Qt::WindowFullScreen);

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


    @Slot()
    def addTab(self):
        tab = ImgTab(self.tabWidget)
        index = self.tabWidget.addTab(tab, "Empty")
        
        # For debugging
        tab.imgview.loadImage("/home/rem/Pictures/red-tree-with-eyes.jpeg")

        self.tabWidget.setCurrentIndex(index)

    @Slot()
    def closeTab(self, index):
        self.tabWidget.removeTab(index)
        if self.tabWidget.count() == 0:
            self.addTab()

    @Slot()
    def onTabChanged(self, index):
        if self.galleryWindow:
            tab = self.tabWidget.currentWidget()
            self.galleryWindow.setTab(tab)
        
    
    @Slot()
    def setTool(self, toolName: str):
        tab = self.tabWidget.currentWidget()
        tab.setTool(toolName)

    
    def toggleGallery(self):
        # TODO: Keep GalleryWindow instance? Toggle via show/hide?
        if self.galleryWindow is None:
            screenSize = app.primaryScreen().size()
            wHalf = screenSize.width() // 2

            self.galleryWindow = GalleryWindow(self)
            self.galleryWindow.resize(wHalf, screenSize.height()//2)
            self.galleryWindow.move(wHalf, 0)
            self.galleryWindow.show()

            tab = self.tabWidget.currentWidget()
            self.galleryWindow.setTab(tab)
        else:
            self.galleryWindow.close()
    
    def onGalleryClosed(self):
        self.galleryWindow = None
    

    def closeEvent(self, event):
        if self.galleryWindow:
            self.galleryWindow.close()


class ImgTab(QtWidgets.QMainWindow):
    def __init__(self, tabWidget):
        super().__init__()
        self.tabWidget = tabWidget

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
        name = os.path.basename(currentFile)
        self.tabWidget.setTabText(idx, name)

    def onFileLoaded(self, currentFile):
        self.onFileChanged(currentFile)
    

    def setTool(self, toolName: str):
        if toolName not in self.tools:
            self.tools[toolName] = self.createTool(toolName)
        self.imgview.tool = self.tools[toolName]

        # Replace toolbar
        if self._toolbar is not None:
            self.removeToolBar(self._toolbar)
        self._toolbar = self.imgview.tool.getToolbar()
        if self._toolbar is not None:
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



if __name__ == "__main__":
    app = QtWidgets.QApplication([])

    screenSize = app.primaryScreen().size()

    win = MainWindow(app)
    win.resize(screenSize.width()//2, screenSize.height()//2)
    win.move(0, 0)
    win.show()

    sys.exit(app.exec())
