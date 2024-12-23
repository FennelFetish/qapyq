import os
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, Signal, QRect
from lib.captionfile import FileTypeSelector
from lib.filelist import DataKeys
from lib import qtlib
from ui.tab import ImgTab
from .gallery_item import GalleryGridItem, GalleryItem, GalleryListItem, ImageIcon


class GalleryGrid(QtWidgets.QWidget):
    headersUpdated  = Signal(list)
    fileChanged     = Signal(object, int)
    reloaded        = Signal()
    thumbnailLoaded = Signal()

    def __init__(self, tab: ImgTab, captionSource: FileTypeSelector):
        super().__init__()
        self.tab = tab
        self.captionSrc = captionSource
        self.filelist = tab.filelist
        self.fileItems: dict[str, GalleryItem] = {}
        self.itemClass = GalleryGridItem

        self.icons = {
            ImageIcon.Caption: QtGui.QPixmap("./res/icon_caption.png"),
            ImageIcon.Crop: QtGui.QPixmap("./res/icon_crop.png"),
            ImageIcon.Mask: QtGui.QPixmap("./res/icon_mask.png")
        }

        colorWhite = QtGui.QColor(230, 230, 230)
        colorGreen = QtGui.QColor(50, 180, 60)
        colorRed   = QtGui.QColor(250, 70, 30)
        self.iconStates = {
            DataKeys.IconStates.Exists: (QtGui.QPen(colorWhite), QtGui.QBrush(colorWhite)),
            DataKeys.IconStates.Saved: (QtGui.QPen(colorGreen), QtGui.QBrush(colorGreen)),
            DataKeys.IconStates.Changed: (QtGui.QPen(colorRed), QtGui.QBrush(colorRed)),
        }

        self.columns = 4
        self.rows = 0

        self._selectedItem: GalleryItem | None = None
        self._selectedCompare: GalleryItem | None = None
        self._ignoreFileChange = False

        # TODO: This layout has a maximum height of 524287. Why??
        layout = QtWidgets.QGridLayout()
        layout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetNoConstraint)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.setLayout(layout)


    def setViewMode(self, mode: str):
        newItemClass = GalleryListItem if mode=="list" else GalleryGridItem
        if newItemClass == self.itemClass:
            return
        self.itemClass = newItemClass

        for widget in self.freeLayout().values():
            widget.deleteLater()

        self.layout().setSpacing(newItemClass.getSpacing())
        self.columns = self.calcColumnCount()

        self.reloadImages()
        self.reloaded.emit()

    def reloadCaptions(self):
        # TODO: Thread. Invalidate all and only load visible.
        for item in self.fileItems.values():
            item.loadCaption()


    def freeLayout(self) -> dict:
        galleryItems = dict()
        layout: QtWidgets.QGridLayout = self.layout()
        for i in reversed(range(layout.count())):
            item = layout.takeAt(i)
            if widget := item.widget():
                if isinstance(widget, self.itemClass):
                    galleryItems[widget.file] = widget
                else:
                    widget.deleteLater()
            else:
                item.spacerItem().deleteLater()

        return galleryItems

    def reloadImages(self):
        self.fileItems = dict()
        self._selectedItem = None
        self._selectedCompare = None

        existingItems: dict = self.freeLayout()
        headers = list()
        rows = set()

        currentDir = ""
        row, col = 0, 0
        for file in self.filelist.getFiles():
            if (dirname := os.path.dirname(file)) != currentDir:
                if col > 0:
                    row += 1
                    col = 0
                currentDir = dirname
                self.addHeader(dirname, row)
                headers.append((dirname, row))
                rows.add(row)
                row += 1

            if not (galleryItem := existingItems.pop(file, None)):
                galleryItem = self.itemClass(self, file)
            
            self.addImage(galleryItem, file, row, col)
            rows.add(row)
            col += 1
            if col >= self.columns:
                col = 0
                row += 1

        self.rows = len(rows)

        for widget in existingItems.values():
            widget.deleteLater()

        self.headersUpdated.emit(headers)
    
    def addImage(self, galleryItem: GalleryItem, file: str, row: int, col: int):
        galleryItem.row = row
        self.fileItems[file] = galleryItem

        self.layout().addWidget(galleryItem, row, col, Qt.AlignmentFlag.AlignTop)

        if self.filelist.getCurrentFile() == file:
            self._selectedItem = galleryItem
            galleryItem.selected = True
        else:
            galleryItem.selected = False

        if (compareTool := self.tab.getTool("compare")) and compareTool.compareFile == file:
            self._selectedCompare = galleryItem
            galleryItem.setCompare(True)
        else:
            galleryItem.setCompare(False)

    def addHeader(self, text: str, row: int):
        label = QtWidgets.QLabel(text)
        qtlib.setMonospace(label, 1.2, bold=True)
        label.setContentsMargins(4, 4, 4, 4)

        palette = QtWidgets.QApplication.palette()
        colorFg = palette.color(QtGui.QPalette.ColorRole.BrightText).name()
        label.setStyleSheet(f"color: {colorFg}; background-color: #161616")
        self.layout().addWidget(label, row, 0, 1, self.columns)


    def setSelectedItem(self, item: GalleryItem, updateFileList=False):
        if self._selectedItem:
            self._selectedItem.selected = False
        item.selected = True
        self._selectedItem = item

        item.takeFocus()
        self.fileChanged.emit(item, item.row)

        if updateFileList:
            try:
                self._ignoreFileChange = True
                self.filelist.setCurrentFile(item.file)
            finally:
                self._ignoreFileChange = False

    def setSelectedCompare(self, item: GalleryItem):
        if self._selectedCompare:
            self._selectedCompare.setCompare(False)
        item.setCompare(True)
        self._selectedCompare = item


    def calcColumnCount(self):
        colWidth = self.itemClass.getColumnWidth()
        spacing  = self.layout().spacing()
        cols = int(self.width() // (colWidth + spacing))
        return max(cols, 1)

    def adjustGrid(self):
        cols = self.calcColumnCount()
        if cols == self.columns:
            return
        self.columns = cols

        layout = self.layout()
        items = []
        for i in reversed(range(layout.count())):
            items.append(layout.takeAt(i))

        headers = list()
        rows = set()

        row, col = 0, 0
        for widget in (item.widget() for item in reversed(items)):
            if isinstance(widget, self.itemClass):
                widget.row = row
                layout.addWidget(widget, row, col, Qt.AlignmentFlag.AlignTop)
                rows.add(row)
                col += 1
                if col >= cols:
                    row += 1
                    col = 0
            else:
                if col > 0:
                    row += 1
                    col = 0
                layout.addWidget(widget, row, 0, 1, cols)
                headers.append((widget.text(), row))
                rows.add(row)
                row += 1
        
        self.rows = len(rows)

        layout.update()
        self.headersUpdated.emit(headers)


    def getRowForY(self, y: int, compareBottom=False) -> int:
        layout: QtWidgets.QGridLayout = self.layout()
        rowY = QRect.bottom if compareBottom else QRect.top

        # Binary search
        lo = 0
        hi = self.rows-1

        while lo < hi:
            row = lo + ((hi-lo) // 2)
            rect = layout.cellRect(row, 0)
            if not rect.isValid():
                return 0
            
            if y > rowY(rect):
                lo = row+1 # Continue in upper half
            else:
                hi = row   # Continue in lower half

        return lo

    def getYforRow(self, row: int, skipDownwards=False):
        layout: QtWidgets.QGridLayout = self.layout()
        rect = layout.cellRect(row, 0)
        if not rect.isValid():
            return -1

        # Check for header above current row
        rectAbove = layout.cellRect(row-1, 0)
        if rectAbove.height() < 100 and rectAbove.isValid():
            if skipDownwards:
                row += 1
                rect = layout.cellRect(row, 0)
            else:
                row -= 1
                rect = rectAbove
        
        y = rect.top()
        for col in range(1, self.columns):
            if (rect := layout.cellRect(row, col)).isValid():
                y = min(y, rect.top())
        return y


    def onFileChanged(self, currentFile: str):
        if not self._ignoreFileChange:
            widget = self.fileItems[currentFile]
            self.setSelectedItem(widget)
    
    def onFileListChanged(self, currentFile: str):
        # When files were appended, the selection is kept
        # and the gallery should scroll to the selection instead of the top
        if (selectedItem := self._selectedItem) and selectedItem.file != currentFile:
            selectedItem = None

        self.reloadImages()
        if selectedItem:
            self.fileChanged.emit(selectedItem, selectedItem.row)
        else:
            self.reloaded.emit()

    def onFileDataChanged(self, file: str, key: str):
        widget = self.fileItems.get(file)
        if not widget:
            return

        match key:
            case DataKeys.ImageSize:
                if imgSize := self.filelist.getData(file, key):
                    widget.setImageSize(imgSize[0], imgSize[1])

            case DataKeys.CaptionState | DataKeys.CropState | DataKeys.MaskState:
                iconState = self.filelist.getData(file, key)
                widget.setIcon(key, iconState)
