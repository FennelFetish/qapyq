import sys
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, Slot
from imgview import ImgView
from export import Export


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Compare")
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

    @Slot()
    def addTab(self):
        tab = ImgTab(self.tabWidget)
        index = self.tabWidget.addTab(tab, "Empty")
        self.tabWidget.setCurrentIndex(index)

        # For debugging
        tab.imgview.loadImage("/home/rem/Pictures/red-tree-with-eyes.jpeg")

    @Slot()
    def closeTab(self, index):
        self.tabWidget.removeTab(index)
        if self.tabWidget.count() == 0:
            self.addTab()
    
    @Slot()
    def setTool(self, toolName: str):
        tab = self.tabWidget.currentWidget()
        tab.setTool(toolName)



class ImgTab(QtWidgets.QMainWindow):
    def __init__(self, tabWidget):
        super().__init__()
        self.tabWidget = tabWidget

        self.imgview = ImgView(self)
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

    def setTabName(self, name):
        idx = self.tabWidget.indexOf(self)
        self.tabWidget.setTabText(idx, name)



if __name__ == "__main__":
    app = QtWidgets.QApplication([])

    win = MainWindow()
    win.resize(1500, 900)
    win.move(0, 0)
    win.show()

    sys.exit(app.exec())
