from typing import Iterable
from typing_extensions import override
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, Slot, QPoint, QThreadPool
from config import Config
from ui import aux_window
from ui.tab import ImgTab
from lib import qtlib, filelist


def getAuxWindowClass(winName: str) -> type:
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

    raise ValueError(f"Unknown window name: '{winName}'")



class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, app: QtWidgets.QApplication):
        super().__init__()
        self.app = app
        self._quitConfirmed = False

        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose)
        self.setWindowIcon(QtGui.QPixmap(Config.windowIcon))
        self.updateTitle(None)

        self.auxWindows: dict[str, aux_window.AuxiliaryWindow] = dict()

        self.toolbar = MainToolBar(self)
        self.addToolBar(qtlib.toolbarAreaFromString(Config.toolbarPosition), self.toolbar)

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
        self.tabWidget.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.tabWidget.currentChanged.connect(self.onTabChanged)
        self.tabWidget.tabCloseRequested.connect(self.askCloseTab)
        #self.tabWidget.tabBarClicked.connect(self._showTabMenu)
        self.setCentralWidget(self.tabWidget)

    # @Slot(int)
    # def _showTabMenu(self, index: int):
    #     if index >= 0 and self.app.mouseButtons() == Qt.MouseButton.RightButton:
    #         menu = TabContextMenu(self, index)
    #         menu.exec(QtGui.QCursor.pos())

    def tabs(self) -> Iterable[ImgTab]:
        for i in range(self.tabWidget.count()):
            yield self.tabWidget.widget(i)

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

    def addTabWithPaths(self, paths: Iterable[str]):
        tabTitle = self.tabWidget.tabText(self.tabWidget.currentIndex())
        if tabTitle == ImgTab.EMPTY_TAB_TITLE:
            tab = self.currentTab
        else:
            tab = self.addTab()

        tab.filelist.loadAll(paths)

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

    @Slot(int)
    def onTabChanged(self, index: int):
        for i, tab in enumerate(self.tabs()):
            if i != index: # Don't deactivate fullscreen tab
                tab.active = False

        if tab := self.currentTab:
            tab.active = True

        for win in self.auxWindows.values():
            win.setTab(tab)

        self._previousTab = tab

        self.toolbar.setTool(tab.toolName if tab else None)
        self.updateTitle(self.tabWidget.tabText(index))


    def closeTab(self, index: int):
        tab: ImgTab = self.tabWidget.widget(index)
        tab.onTabClosed()

        self.tabWidget.removeTab(index)
        if self.tabWidget.count() == 0:
            self.addTab()
        tab.deleteLater()

    def askCloseCurrentTab(self, confirm=False):
        if self._fullscreenTab:
            self.toggleFullscreen()
        self.askCloseTab(self.tabWidget.currentIndex(), confirm)

    @Slot(int)
    def askCloseTab(self, index: int, confirm: bool = False):
        tab: ImgTab = self.tabWidget.widget(index)
        questions = tab.checkClose()
        if questions:
            text = "This tab has:\n"
            text += "\n".join(f"• {q}" for q in questions)
            text += "\n\nDo you really want to close this tab?"
        elif confirm:
            text = "Do you really want to close the current tab?"
        else:
            self.closeTab(index)
            return

        dialog = QtWidgets.QMessageBox(self)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Question)
        dialog.setWindowTitle("Confirm Close Tab")
        dialog.setText(text)
        dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)

        if dialog.exec() == QtWidgets.QMessageBox.StandardButton.Yes:
            self.closeTab(index)


    def setTool(self, toolName: str):
        if self._fullscreenTab:
            self._fullscreenTab.setTool(toolName)
        else:
            self.currentTab.setTool(toolName)
        self.toolbar.setTool(toolName)

    @Slot(str)
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


    def toggleAuxWindow(self, winName: str):
        if win := self.auxWindows.get(winName):
            win.close()
            return

        winClass = getAuxWindowClass(winName)
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

    @Slot(object)
    def onAuxWindowClosed(self, win: aux_window.AuxiliaryWindow) -> None:
        winName = win.configKey
        self.toolbar.setWindowToggleChecked(winName, False)
        win.deleteLater()
        self.auxWindows.pop(winName, None)


    def askQuit(self, confirm=False) -> bool:
        questions = list[str]()
        for tab in self.tabs():
            questions.extend(tab.checkClose())

        if questions:
            text = "Some tabs have:\n"
            text += "\n".join(f"• {q}" for q in questions)
            text += "\n\nDo you really want to quit the application?"
        elif confirm:
            text = "Do you really want to quit the application?"
        else:
            self._quitConfirmed = True
            return True

        dialog = QtWidgets.QMessageBox(self)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Confirm Quit")
        dialog.setText(text)
        dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)

        self._quitConfirmed = (dialog.exec() == QtWidgets.QMessageBox.StandardButton.Yes)
        return self._quitConfirmed

    @override
    def closeEvent(self, event: QtGui.QCloseEvent):
        if not (self._quitConfirmed or self.askQuit()):
            event.ignore()
            return

        for tab in self.tabs():
            tab.filelist.abortLoading()
            tab.active = False
            tab.imgview.image.deleteLater()  # Stop video thread

        QThreadPool.globalInstance().clear()

        from gallery.thumbnail_cache import ThumbnailCache
        ThumbnailCache().shutdown()

        aux_window.saveWindowPos(self, "main")
        Config.toolbarPosition = qtlib.toolbarAreaToString(self.toolBarArea(self.toolbar))

        if self._fullscreenTab:
            self._fullscreenTab.close()

        openWindows = []
        for win in list(self.auxWindows.values()):
            openWindows.append(win.configKey)
            win.close()
        Config.windowOpen = openWindows

        qtlib.SingletonWindow.closeAllWindows()



class MainMenu(QtWidgets.QMenu):
    def __init__(self, mainWindow: MainWindow):
        super().__init__()
        self.mainWindow = mainWindow

        # https://doc.qt.io/qt-6/qt.html#Key-enum

        actOpen = self._addShortcutAction("&Open...", Qt.CTRL | Qt.Key_O)
        actOpen.triggered.connect(self.openFile)

        actOpenDir = self._addShortcutAction("&Open Folder...", Qt.CTRL | Qt.SHIFT | Qt.Key_O)
        actOpenDir.triggered.connect(self.openDir)

        self.addSeparator()

        actFullscreen = self._addShortcutAction("Toggle &Fullscreen", Qt.CTRL | Qt.Key_F)
        actFullscreen.triggered.connect(mainWindow.toggleFullscreen)

        actPrevImage = self._addShortcutAction("Previous Image", Qt.CTRL | Qt.Key_PageUp)
        actPrevImage.triggered.connect(lambda: self.changeImage(False))

        actNextImage = self._addShortcutAction("Next Image", Qt.CTRL | Qt.Key_PageDown)
        actNextImage.triggered.connect(lambda: self.changeImage(True))

        self.addSeparator()

        actAddTab = self._addShortcutAction("New &Tab", Qt.CTRL | Qt.Key_T)
        actAddTab.triggered.connect(mainWindow.addTab)

        actSwitchTab = self._addShortcutAction("Switch Tab", Qt.CTRL | Qt.Key_Tab)
        actSwitchTab.triggered.connect(mainWindow.switchTab)

        actCloseTab = self._addShortcutAction("Close Tab", Qt.CTRL | Qt.Key_W)
        actCloseTab.triggered.connect(lambda: mainWindow.askCloseCurrentTab(True))

        self.addSeparator()

        self.addMenu(self._buildToolsSubmenu(mainWindow))
        self.addMenu(self._buildWindowsSubmenu(mainWindow))

        self.addSeparator()

        self._fileTypes = self._buildFileTypesSubmenu()
        self.addMenu(self._fileTypes)

        actPlaybackEnabled = self.addAction("Enable Video Playback")
        actPlaybackEnabled.setCheckable(True)
        actPlaybackEnabled.setChecked(Config.mediaPlaybackEnabled)
        actPlaybackEnabled.toggled.connect(self._onMediaPlaybackToggled)

        self.addSeparator()

        actModelConfig = self.addAction("Model Settings...")
        actModelConfig.triggered.connect(self.showModelSettings)

        actShowHostWin = self._addShortcutAction("&Hosts...", Qt.CTRL | Qt.Key_H)
        actShowHostWin.triggered.connect(self.showHostsWin)

        actClearVram = self._addShortcutAction("Clear V&RAM", Qt.CTRL | Qt.Key_R)
        actClearVram.triggered.connect(self.clearVram)

        actKillInference = self.addAction("Terminate Inference")
        actKillInference.triggered.connect(self.killInference)

        self.addSeparator()

        actQuit = self._addShortcutAction("&Quit", Qt.CTRL | Qt.Key_Q)
        actQuit.triggered.connect(self.quitWithConfirmation)


    def _addShortcutAction(self, title: str, keys) -> QtGui.QAction:
        action = self.addAction(title)
        action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        action.setShortcut(QtGui.QKeySequence(keys))
        return action


    def _buildToolsSubmenu(self, mainWindow: MainWindow) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu("Select Tools")

        for i, tool in enumerate(("view", "slideshow", "measure", "compare", "crop", "scale", "mask"), 1):
            act = menu.addAction(tool.capitalize())
            act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            act.setShortcut(QtGui.QKeySequence.fromString(f"Ctrl+{i}"))
            act.triggered.connect(lambda checked, tool=tool: mainWindow.setTool(tool))

        return menu

    def _buildWindowsSubmenu(self, mainWindow: MainWindow) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu("Toggle Windows")

        for i, win in enumerate(("gallery", "stats", "batch", "caption"), 1):
            act = menu.addAction(win.capitalize())
            act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            act.setShortcut(QtGui.QKeySequence.fromString(f"F{i}"))
            act.triggered.connect(lambda checked, win=win: mainWindow.toggleAuxWindow(win))

        return menu

    def _buildFileTypesSubmenu(self) -> qtlib.CheckboxMenu:
        menu = qtlib.CheckboxMenu("File Types")
        menu.addCheckbox("image", "Load Images", "image" not in Config.mediaExcludeTypes)
        menu.addCheckbox("video", "Load Videos", "video" not in Config.mediaExcludeTypes)
        menu.selectionChanged.connect(self._onMediaTypesUpdated)
        return menu


    @Slot(dict)
    def _onMediaTypesUpdated(self, checkStates: dict[str, bool]):
        excludeTypes = [key for key, state in checkStates.items() if not state]
        if len(excludeTypes) < len(checkStates):
            Config.mediaExcludeTypes = excludeTypes
            filelist.resetReadExtensions()
        else:
            reactivate = next(iter(Config.mediaExcludeTypes), "image")
            self._fileTypes.setChecked(reactivate, True)

    @Slot(bool)
    def _onMediaPlaybackToggled(self, checked: bool):
        Config.mediaPlaybackEnabled = checked

        if not checked and Config.mediaPlaybackStarted:
            dialog = QtWidgets.QMessageBox(self.mainWindow)
            dialog.setIcon(QtWidgets.QMessageBox.Icon.Information)
            dialog.setWindowTitle("Restart to apply settings")
            dialog.setText("To free VRAM for model loading, please restart the application.")
            dialog.setInformativeText("Video playback has already allocated resources in memory.")
            dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
            dialog.exec()


    @Slot()
    def openFile(self):
        path, filter = QtWidgets.QFileDialog.getOpenFileName(self.mainWindow, "Open File")
        if path:
            self.mainWindow.addTabWithPaths([path])

    @Slot()
    def openDir(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self.mainWindow, "Open Folder")
        if path:
            self.mainWindow.addTabWithPaths([path])


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
    def quitWithConfirmation(self):
        if self.mainWindow.askQuit(True):
            self.mainWindow.close()



class MainToolBar(QtWidgets.QToolBar):
    def __init__(self, mainWindow: MainWindow):
        super().__init__("Main Toolbar")
        self.mainWindow = mainWindow
        self.setFloatable(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)

        self.menu = MainMenu(mainWindow)

        self.actMenu = self.addAction("☰")
        self.actMenu.setMenu(self.menu)
        self.actMenu.triggered.connect(self._showMenu)

        self.addSeparator()

        self._buildToolButtons(mainWindow)
        self.setTool("view")

        self.addSeparator()

        self.windowToggles: dict[str, QtGui.QAction] = dict()
        self._addWindowToggle("gallery", mainWindow, 1)
        self._addWindowToggle("stats", mainWindow, 2)
        self._addWindowToggle("batch", mainWindow, 3)
        self._addWindowToggle("caption", mainWindow, 4)

        self.addWidget(qtlib.SpacerWidget())

        actAddTab = self.addAction("New Tab")
        actAddTab.triggered.connect(mainWindow.addTab)

        winColor = QtWidgets.QApplication.palette().color(QtGui.QPalette.ColorRole.Window)
        colorBg = winColor.lighter().name()
        colorBorder = winColor.darker().name()
        self.setStyleSheet("QToolBar{border:0px;} ::separator{background-color: " + colorBg + "; border: 1px dotted " + colorBorder + "; height: 1px; width: 1px;}")


    def _buildToolButtons(self, mainWindow):
        self._toolActions = {
            "view":     self.addAction("View"),
            "slideshow":self.addAction("Slideshow"),
            "measure":  self.addAction("Measure"),
            "compare":  self.addAction("Compare"),
            "crop":     self.addAction("Crop"),
            "scale":    self.addAction("Scale"),
            "mask":     self.addAction("Mask")
        }

        for i, (name, act) in enumerate(self._toolActions.items(), 1):
            act.setToolTip(f"Select the {act.text()} Tool with <b>Ctrl+{i}</b>")
            act.setCheckable(True)
            act.triggered.connect(lambda act=act, name=name: mainWindow.setTool(name)) # Capture correct vars

    def setTool(self, toolName):
        for act in self._toolActions.values():
            act.setChecked(False)

        if toolName in self._toolActions:
            self._toolActions[toolName].setChecked(True)

    def _addWindowToggle(self, winName: str, mainWindow: MainWindow, shortcut: int) -> None:
        act = self.addAction(winName.capitalize())
        act.setToolTip(f"Toggle the {act.text()} Window with <b>F{shortcut}</b>")
        act.setCheckable(True)
        act.triggered.connect(lambda: mainWindow.toggleAuxWindow(winName))
        self.windowToggles[winName] = act

    def setWindowToggleChecked(self, winName, checked: bool) -> None:
        if act := self.windowToggles.get(winName):
            act.setChecked(checked)

    @Slot()
    def _showMenu(self):
        widget = self.widgetForAction(self.actMenu)
        pos = widget.mapToGlobal(QPoint(0, widget.height()))
        self.menu.popup(pos)



# class TabContextMenu(QtWidgets.QMenu):
#     def __init__(self, mainWindow: MainWindow, tabIndex: int):
#         super().__init__()
#         self.mainWindow = mainWindow
#         self.index = tabIndex

#         actMerge = self.addAction("Append Files to Left Tab")
#         actMerge.triggered.connect(self._mergeLeft)

#         if self.index <= 0:
#             actMerge.setEnabled(False)

#     @Slot()
#     def _mergeLeft(self):
#         if self.index <= 0:
#             return

#         tabWidget = self.mainWindow.tabWidget
#         clickedTab: ImgTab = tabWidget.widget(self.index)
#         leftTab: ImgTab    = tabWidget.widget(self.index - 1)

#         leftTab.filelist.mergeFiles(clickedTab.filelist)
