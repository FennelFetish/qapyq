import os
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, Signal, QRect
from lib.captionfile import FileTypeSelector
from lib.filelist import DataKeys
from lib import qtlib
from ui.tab import ImgTab
from .gallery_item import GalleryItem, GalleryGridItem, GalleryListItem, ImageIcon


class Header(QtWidgets.QFrame):
    def __init__(self, dir: str, row: int):
        super().__init__()
        self.dir = dir
        self.row = row
        self.numImages = 0

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)

        txtTitle = QtWidgets.QLineEdit(dir)
        txtTitle.setReadOnly(True)
        qtlib.setMonospace(txtTitle, 1.2, bold=True)
        layout.addWidget(txtTitle)

        self.lblImgCount = QtWidgets.QLabel()
        layout.addWidget(self.lblImgCount)

        self.setLayout(layout)
        self.setStyleSheet(f"color: #fff; background-color: #161616")

    def updateImageLabel(self):
        text = f"{self.numImages} Image"
        if self.numImages != 1:
            text += "s"
        self.lblImgCount.setText(text)



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

        self.thumbnailSize = 200
        self.columns = 4
        self.rows = 0

        self._selectedItem: GalleryItem | None = None
        self._selectedCompare: GalleryItem | None = None
        self._ignoreFileChange = False

        # TODO: This layout has a maximum height of 524287. Why??
        self._layout = QtWidgets.QGridLayout()
        self._layout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetNoConstraint)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(self.itemClass.getSpacing())
        self.setLayout(self._layout)


    def setViewMode(self, mode: str):
        newItemClass = GalleryListItem if mode=="list" else GalleryGridItem
        if newItemClass == self.itemClass:
            return
        self.itemClass = newItemClass

        for widget in self.freeLayout().values():
            widget.deleteLater()

        self._layout.setSpacing(newItemClass.getSpacing())
        self.columns = self.calcColumnCount()

        self.reloadImages()
        self.reloaded.emit()

    def setThumbnailSize(self, size: int):
        if size == self.thumbnailSize:
            return

        self.thumbnailSize = size
        self.adjustGrid()
        for item in self.fileItems.values():
            item.onThumbnailSizeUpdated()

    def reloadCaptions(self):
        # TODO: Thread. Invalidate all and only load visible.
        for item in self.fileItems.values():
            item.loadCaption()


    def freeLayout(self) -> dict:
        galleryItems = dict()
        for i in reversed(range(self._layout.count())):
            item = self._layout.takeAt(i)
            if widget := item.widget():
                if isinstance(widget, GalleryItem):
                    galleryItems[widget.file] = widget
                else:
                    widget.deleteLater()

        return galleryItems

    def reloadImages(self):
        self.fileItems = dict()
        self._selectedItem = None
        self._selectedCompare = None

        existingItems: dict = self.freeLayout()
        headers = list()
        rows = set()

        currentHeader: Header = None
        row, col = 0, 0
        for file in self.filelist.getFiles():
            dirname = os.path.dirname(file)
            if not currentHeader or currentHeader.dir != dirname:
                if col > 0:
                    row += 1
                    col = 0
                
                currentHeader = self.addHeader(dirname, row)
                headers.append(currentHeader)
                rows.add(row)
                row += 1

            if not (galleryItem := existingItems.pop(file, None)):
                galleryItem = self.itemClass(self, file)
            
            self.addImage(galleryItem, file, row, col)
            currentHeader.numImages += 1
            rows.add(row)

            col += 1
            if col >= self.columns:
                col = 0
                row += 1

        self.rows = len(rows)

        for widget in existingItems.values():
            widget.deleteLater()

        for header in headers:
            header.updateImageLabel()
        self.headersUpdated.emit(headers)
    
    def addImage(self, galleryItem: GalleryItem, file: str, row: int, col: int):
        galleryItem.row = row
        self.fileItems[file] = galleryItem

        self._layout.addWidget(galleryItem, row, col, Qt.AlignmentFlag.AlignTop)

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

    def addHeader(self, dir: str, row: int) -> Header:
        header = Header(dir, row)
        self._layout.addWidget(header, row, 0, 1, self.columns)
        return header


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
        colWidth = self.thumbnailSize if self.itemClass == GalleryGridItem else GalleryListItem.COLUMN_WIDTH
        spacing  = self._layout.spacing()
        w = self.parent().width() # Parent width seems more reliable after updates, and it has exactly the same value.
        cols = int(w // (colWidth + spacing))
        return max(cols, 1)

    def adjustGrid(self):
        cols = self.calcColumnCount()
        if cols == self.columns:
            return
        self.columns = cols

        items = []
        for i in reversed(range(self._layout.count())):
            items.append(self._layout.takeAt(i))

        headers = list()
        rows = set()

        row, col = 0, 0
        for widget in (item.widget() for item in reversed(items)):
            if isinstance(widget, GalleryItem):
                widget.row = row
                self._layout.addWidget(widget, row, col, Qt.AlignmentFlag.AlignTop)
                rows.add(row)
                col += 1
                if col >= cols:
                    row += 1
                    col = 0
            elif isinstance(widget, Header):
                if col > 0:
                    row += 1
                    col = 0
                widget.row = row
                headers.append(widget)
                self._layout.addWidget(widget, row, 0, 1, cols)
                rows.add(row)
                row += 1
        
        self.rows = len(rows)
        self._layout.update()
        self.headersUpdated.emit(headers)


    def getRowForY(self, y: int, compareBottom=False) -> int:
        rowY = QRect.bottom if compareBottom else QRect.top

        # Binary search
        lo = 0
        hi = max(self.rows-1, 0)

        while lo < hi:
            row = lo + ((hi-lo) // 2)
            rect = self._layout.cellRect(row, 0)
            if not rect.isValid():
                return -1
            
            if y > rowY(rect):
                lo = row+1 # Continue in upper half
            else:
                hi = row   # Continue in lower half

        #assert(lo == hi)
        return lo

    def getYforRow(self, row: int, skipDownwards=False):
        # Check for header above current row
        itemAbove = self._layout.itemAtPosition(row-1, 0)
        if itemAbove and isinstance(itemAbove.widget(), Header):
            row += 1 if skipDownwards else -1

        rect = self._layout.cellRect(row, 0)
        if not rect.isValid():
            return -1

        y = rect.top()
        for col in range(1, self.columns):
            if (rect := self._layout.cellRect(row, col)).isValid():
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
