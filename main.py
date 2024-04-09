from imgview import ImgView
import sys
from PySide6 import QtWidgets
from PySide6 import QtGui
from PySide6.QtCore import Slot, Qt


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Compare")
        self.buildTabs()
        self.buildMenu()
        self.buildToolbar()
        self.addTab()

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
        toolbar.addAction("View")
        toolbar.addAction("Compare")

    @Slot()
    def addTab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(ImgView())
        tab.setLayout(layout)
        index = self.tabWidget.addTab(tab, "Empty")
        self.tabWidget.setCurrentIndex(index)

    @Slot()
    def closeTab(self, index):
        self.tabWidget.removeTab(index)
        if self.tabWidget.count() == 0:
            self.addTab()



if __name__ == "__main__":
    app = QtWidgets.QApplication([])

    win = MainWindow()
    win.resize(800, 600)
    win.move(100, 500)
    win.show()

    sys.exit(app.exec())
