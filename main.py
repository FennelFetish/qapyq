import sys
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, Slot
from imgview import ImgView
import tools


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
        index = self.tabWidget.addTab(ImgTab(), "Empty")
        self.tabWidget.setCurrentIndex(index)

    @Slot()
    def closeTab(self, index):
        self.tabWidget.removeTab(index)
        if self.tabWidget.count() == 0:
            self.addTab()
    
    @Slot()
    def setTool(self, toolName: str):
        tab = self.tabWidget.currentWidget()
        tab.setTool(toolName)



class ImgTab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.imgview = ImgView()
        self.tools = {}
        self.setTool("view")

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.imgview)
        self.setLayout(layout)
    
    def setTool(self, toolName: str):
        if toolName not in self.tools:
            self.tools[toolName] = self.createTool(toolName)
        self.imgview.tool = self.tools[toolName]

    def createTool(self, toolName: str):
        match toolName:
            case "view":    return tools.ViewTool()
            case "compare": return tools.CompareTool()
            case "crop":    return tools.CropTool()
        return None



if __name__ == "__main__":
    app = QtWidgets.QApplication([])

    win = MainWindow()
    win.resize(800, 600)
    win.move(100, 500)
    win.show()

    sys.exit(app.exec())
