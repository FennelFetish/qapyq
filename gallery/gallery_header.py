import os
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot
from ui.tab import ImgTab
from lib import colorlib, qtlib


class GalleryHeader(QtWidgets.QFrame):
    TITLE_INTERACTION = Qt.TextInteractionFlag.TextBrowserInteraction
    TITLE_SIZE_POLICY = (QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
    TITLE_FONT = None
    STYLESHEET = None

    def __init__(self, tab: ImgTab, dir: str, row: int):
        super().__init__()
        self.tab = tab
        self.dir = dir
        self.row = row

        lblTitle = QtWidgets.QLabel(dir, textInteractionFlags=self.TITLE_INTERACTION)
        lblTitle.setSizePolicy(*self.TITLE_SIZE_POLICY)

        self.lblImgCount = MenuLabel(self)

        if GalleryHeader.STYLESHEET is None:
            GalleryHeader.STYLESHEET = f"color: {colorlib.BUBBLE_TEXT}; background-color: {colorlib.BUBBLE_BG}; border: 0px"

            qtlib.setMonospace(lblTitle, 1.2, bold=True)
            GalleryHeader.TITLE_FONT = lblTitle.font()
        else:
            lblTitle.setFont(GalleryHeader.TITLE_FONT)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(lblTitle)
        layout.addWidget(self.lblImgCount)
        self.setLayout(layout)

        self.setStyleSheet(GalleryHeader.STYLESHEET)

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
