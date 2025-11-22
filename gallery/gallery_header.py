import os
from typing import NamedTuple
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot
from ui.tab import ImgTab
from lib import colorlib, qtlib


class GalleryHeader(QtWidgets.QFrame):
    class StyleCache(NamedTuple):
        titleFont: QtGui.QFont
        stylesheet: str

    STYLE: StyleCache | None = None


    def __init__(self, parent: QtWidgets.QWidget, tab: ImgTab, dir: str):
        super().__init__(parent)
        self.tab = tab
        self.dir = dir

        txtTitle = QtWidgets.QLineEdit(dir)
        txtTitle.setReadOnly(True)

        self.lblImgCount = MenuLabel(self)

        if GalleryHeader.STYLE is None:
            qtlib.setMonospace(txtTitle, 1.2, bold=True)
            stylesheet = f"color: {colorlib.BUBBLE_TEXT}; background-color: {colorlib.BUBBLE_BG}; border: 0px"
            GalleryHeader.STYLE = self.StyleCache(txtTitle.font(), stylesheet)
        else:
            txtTitle.setFont(GalleryHeader.STYLE.titleFont)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(txtTitle)
        layout.addWidget(self.lblImgCount)
        self.setLayout(layout)

        self.setStyleSheet(GalleryHeader.STYLE.stylesheet)

    def updateImageLabel(self, numImages: int):
        text = f"{numImages} Image"
        if numImages != 1:
            text += "s"
        self.lblImgCount.setText(text)


    @property
    def folderFiles(self):
        return (file for file in self.tab.filelist.getFiles() if os.path.dirname(file) == self.dir)


    @Slot()
    def selectFiles(self):
        self.tab.filelist.setSelection(self.folderFiles, updateCurrent=True)

    @Slot()
    def openFilesInNewTab(self):
        newTab = self.tab.mainWindow.addTab()
        newTab.filelist.loadFilesFixed(self.folderFiles, self.tab.filelist)

    @Slot()
    def removeFiles(self):
        self.tab.filelist.filterFiles(lambda file: os.path.dirname(file) != self.dir)



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
