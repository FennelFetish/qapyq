import os
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal
from config import Config
from lib.filelist import FileList
from lib.qtlib import ColoredMessageStatusBar
from .imgview import ImgView


class ImgTab(QtWidgets.QMainWindow):
    EMPTY_TAB_TITLE = "Empty"

    tabTitleChanged = Signal(str)

    def __init__(self, tabWidget: QtWidgets.QTabWidget):
        super().__init__()
        self.tabWidget = tabWidget
        self._index = -1 # Store index when fullscreen
        self.setWindowTitle(f"{Config.windowTitle} Fullscreen Tab")

        self.setStatusBar(TabStatusBar(self))

        self.filelist = FileList()
        self.filelist.addListener(self)

        self.imgview = ImgView(self.filelist)
        self._windowContent: dict[str, QtWidgets.QWidget] = dict()

        self.tools = dict()
        self._toolbar = None
        self.toolName = None
        self.setTool("view")

        self.setCentralWidget(self.imgview)


    def onFileChanged(self, currentFile):
        idx = self.tabWidget.indexOf(self)
        name = os.path.basename(currentFile) if currentFile else self.EMPTY_TAB_TITLE
        self.tabWidget.setTabText(idx, name)
        self.tabTitleChanged.emit(name)

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
                from tools.view import ViewTool
                return ViewTool(self)
            case "slideshow":
                from tools.slideshow import SlideshowTool
                return SlideshowTool(self)
            case "measure":
                from tools.measure import MeasureTool
                return MeasureTool(self)
            case "compare":
                from tools.compare import CompareTool
                return CompareTool(self)
            case "crop":
                from tools.crop import CropTool
                return CropTool(self)
            case "scale":
                from tools.scale import ScaleTool
                return ScaleTool(self)
            case "mask":
                from tools.mask import MaskTool
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



class TabStatusBar(ColoredMessageStatusBar):
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
