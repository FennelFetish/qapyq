import os
from typing import NamedTuple, Iterable
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot
from ui.tab import ImgTab
from lib import colorlib, qtlib


class GalleryHeader(QtWidgets.QWidget):
    class StyleCache(NamedTuple):
        titleFont: QtGui.QFont
        palette: QtGui.QPalette

    STYLE: StyleCache | None = None
    ALL_FILES_DIR = "All Images"


    def __init__(self, parent: QtWidgets.QWidget, tab: ImgTab, path: str):
        super().__init__(parent)
        self.tab = tab
        self.path = path

        txtTitle = QtWidgets.QLineEdit(path)
        txtTitle.setReadOnly(True)
        txtTitle.setFrame(False)

        self.lblImgCount = MenuLabel(self)

        if GalleryHeader.STYLE is None:
            GalleryHeader.STYLE = self._initStyle(txtTitle)

        txtTitle.setFont(GalleryHeader.STYLE.titleFont)
        self.setPalette(GalleryHeader.STYLE.palette)
        self.setAutoFillBackground(True)

        layout = QtWidgets.QHBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(txtTitle, 1)
        layout.addWidget(self.lblImgCount, 0, Qt.AlignmentFlag.AlignBottom)
        self.setLayout(layout)


    def _initStyle(self, txtTitle: QtWidgets.QWidget) -> StyleCache:
        palette = self.palette()
        palette.setColor(palette.ColorRole.Text, colorlib.BUBBLE_TEXT)
        palette.setColor(palette.ColorRole.Window, colorlib.BUBBLE_BG)
        palette.setColor(palette.ColorRole.Base, colorlib.BUBBLE_BG)

        qtlib.setMonospace(txtTitle, 1.2, bold=True)
        return self.StyleCache(txtTitle.font(), palette)


    def updateImageLabel(self, numImages: int):
        text = f"{numImages} Image"
        if numImages != 1:
            text += "s"
        self.lblImgCount.setText(text)


    @property
    def folderFiles(self) -> Iterable[str]:
        if self.path == self.ALL_FILES_DIR:
            return (file for file in self.tab.filelist.getFiles())
        else:
            return (file for file in self.tab.filelist.getFiles() if os.path.dirname(file) == self.path)


    @Slot()
    def selectFiles(self):
        self.tab.filelist.setSelection(self.folderFiles, updateCurrent=True)

    @Slot()
    def openFilesInNewTab(self):
        newTab = self.tab.mainWindow.addTab()
        newTab.filelist.loadFilesFixed(self.folderFiles, self.tab.filelist)

    @Slot()
    def removeFiles(self):
        if self.path == self.ALL_FILES_DIR:
            self.tab.filelist.loadAll(())
        else:
            self.tab.filelist.filterFiles(lambda file: os.path.dirname(file) != self.path)



class MenuLabel(QtWidgets.QLabel):
    def __init__(self, header: GalleryHeader):
        super().__init__("☰")
        self.header = header

    def setText(self, text: str) -> None:
        text = f"{text}   ☰" if text else "☰"
        super().setText(text)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            event.accept()

            menu = self.buildMenu()
            menu.exec_(self.mapToGlobal(event.position()).toPoint())
            return

        super().mousePressEvent(event)

    def buildMenu(self) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu("Folder")

        actSelectFiles = menu.addAction("Select Files")
        actSelectFiles.triggered.connect(self.header.selectFiles)

        actOpenFiles = menu.addAction("Open Files in New Tab")
        actOpenFiles.triggered.connect(self.header.openFilesInNewTab)

        menu.addSeparator()

        actRemoveFiles = menu.addAction("Unload Files")
        actRemoveFiles.triggered.connect(self.header.removeFiles)

        return menu
