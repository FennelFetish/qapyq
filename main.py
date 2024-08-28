import os
import sys
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, Slot

from caption import CaptionWindow
from export import Export
from filelist import FileList
from gallery import Gallery, GalleryWindow
from imgview import ImgView


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.galleryWindow = None
        self.captionWindow = None

        self.setWindowTitle("pyImgSet")
        self.setAttribute(Qt.WA_QuitOnClose)

        self.toolbar = MainToolBar(self)
        self.addToolBar(self.toolbar)

        self.buildTabs()
        #self.buildMenu()

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
        self.tabWidget.setElideMode(Qt.ElideMiddle)
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

    @Slot()
    def addTab(self):
        tab = ImgTab(self.tabWidget)
        index = self.tabWidget.addTab(tab, "Empty")
        self.tabWidget.setCurrentIndex(index)
        tab.imgview.setFocus()


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
        self.toolbar.actToggleGallery.setChecked(False)
        self.galleryWindow = None

    
    @Slot()
    def toggleCaptionWindow(self):
        if self.captionWindow is None:
            self.captionWindow = CaptionWindow()
            self.captionWindow.setDimensions(self.app, 0.5, 0.45, 0.5, 0.55)
            self.captionWindow.closed.connect(self.onCaptionWindowClosed)
            self.captionWindow.show()

            tab = self.tabWidget.currentWidget()
            self.captionWindow.setTab(tab)
        else:
            self.captionWindow.close()

    @Slot()
    def onCaptionWindowClosed(self):
        self.toolbar.actToggleCaption.setChecked(False)
        self.captionWindow = None


    def closeEvent(self, event):
        if self.galleryWindow:
            self.galleryWindow.close()
        if self.captionWindow:
            self.captionWindow.close()



class MainToolBar(QtWidgets.QToolBar):
    def __init__(self, mainWindow):
        super().__init__()
        self.mainWindow = mainWindow
        self.setFloatable(False)

        self.actViewTool = self.addAction("View")
        self.actViewTool.setCheckable(True)
        self.actViewTool.triggered.connect(lambda: mainWindow.setTool("view"))

        self.actCompareTool = self.addAction("Compare")
        self.actCompareTool.setCheckable(True)
        self.actCompareTool.triggered.connect(lambda: mainWindow.setTool("compare"))

        self.actCropTool = self.addAction("Crop")
        self.actCropTool.setCheckable(True)
        self.actCropTool.triggered.connect(lambda: mainWindow.setTool("crop"))

        self.setTool("view")
        self.addSeparator()

        self.actToggleGallery = self.addAction("Gallery")
        self.actToggleGallery.setCheckable(True)
        self.actToggleGallery.triggered.connect(mainWindow.toggleGallery)

        self.actToggleCaption = self.addAction("Captions")
        self.actToggleCaption.setCheckable(True)
        self.actToggleCaption.triggered.connect(mainWindow.toggleCaptionWindow)

        winColor = QtWidgets.QApplication.palette().color(QtGui.QPalette.ColorRole.Window)
        colorBg = winColor.lighter().name()
        colorBorder = winColor.darker().name()
        self.setStyleSheet("QToolBar::separator {background-color: " + colorBg + "; border: 1px dotted " + colorBorder + "; height: 1px; width: 1px;}")

    def setTool(self, toolName):
        self.actViewTool.setChecked(False)
        self.actCompareTool.setChecked(False)
        self.actCropTool.setChecked(False)

        if toolName == "view":
                self.actViewTool.setChecked(True)
        elif toolName == "compare":
                self.actCompareTool.setChecked(True)
        elif toolName == "crop":
                self.actCropTool.setChecked(True)


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
        elif toolName == "compare":
                from tools import CompareTool
                return CompareTool(self)
        elif toolName == "crop":
                from tools import CropTool
                return CropTool(self)
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




class TabStatusBar(QtWidgets.QStatusBar):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab

        self.setSizeGripEnabled(False)
        #self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self._lblMouseCoords = QtWidgets.QLabel()
        self._lblMouseCoords.setFixedWidth(100)
        self.addPermanentWidget(self._lblMouseCoords)

        self._lblImgSize = QtWidgets.QLabel()
        self._lblImgSize.setContentsMargins(0, 0, 12, 0)
        self.addPermanentWidget(self._lblImgSize)

        self.setContentsMargins(6, 0, 6, 0)
        self.updateStyleSheet()

    def setImageSize(self, width, height):
        self._lblImgSize.setText(f"W: {width}  H: {height}")

    def setMouseCoords(self, x, y):
        self._lblMouseCoords.setText(f"X: {x}  Y: {y}")

    def showMessage(self, text, timeout=0):
        self.updateStyleSheet()
        super().showMessage(text, timeout)

    def showColoredMessage(self, text, success=True, timeout=4000):
        if success:
            self.updateStyleSheet("#00ff00")
        else:
            self.updateStyleSheet("#ff0000")
        super().showMessage(text, timeout)

    def updateStyleSheet(self, color=None):
        colorStr = f"color: {color}" if color else ""
        self.setStyleSheet("QStatusBar{border-top: 1px outset black;" + colorStr + "}")

        


def main() -> int:
    app = QtWidgets.QApplication([])

    screenSize = app.primaryScreen().size()

    win = MainWindow(app)
    win.resize(screenSize.width()//2, screenSize.height())
    win.move(0, 0)
    win.show()

    if len(sys.argv) > 1:
        tab = win.tabWidget.currentWidget()
        tab.filelist.load(sys.argv[1])
    # else:
    #     tab = win.tabWidget.currentWidget()
    #     tab.filelist.load("/home/rem/Pictures/red-tree-with-eyes.jpeg")

    return app.exec()

if __name__ == "__main__":
    sys.exit( main() )
