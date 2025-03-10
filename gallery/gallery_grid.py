from __future__ import annotations
import os
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, Signal, Slot, QRect, QObject, QTimer
from lib.captionfile import FileTypeSelector
from lib.filelist import DataKeys
from ui.tab import ImgTab
from .gallery_header import GalleryHeader

# Imported at the bottom because of circular dependency
# from .gallery_item import GalleryItem, GalleryGridItem, GalleryListItem, ImageIcon


class GalleryGrid(QtWidgets.QWidget):
    VIEW_MODE_GRID = "grid"
    VIEW_MODE_LIST = "list"

    headersUpdated  = Signal(list)
    fileChanged     = Signal(object, int)
    reloaded        = Signal()
    thumbnailLoaded = Signal()
    loadingProgress = Signal()


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

        self._loadTask: GalleryLoadTask | None = None

        # TODO: This layout has a maximum height of 524287. Why??
        self._layout = QtWidgets.QGridLayout()
        self._layout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetNoConstraint)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(self.itemClass.getSpacing())
        self.setLayout(self._layout)


    def setViewMode(self, mode: str):
        newItemClass = GalleryListItem if mode==self.VIEW_MODE_LIST else GalleryGridItem
        if newItemClass == self.itemClass:
            return
        self.itemClass = newItemClass

        self.clearLayout()

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


    def clearLayout(self) -> None:
        for i in reversed(range(self._layout.count())):
            item = self._layout.takeAt(i)
            if item and (widget := item.widget()):
                widget.deleteLater()


    def reloadImages(self):
        self.fileItems = dict()
        self._selectedItem = None
        self._selectedCompare = None

        self.clearLayout()

        self._loadTask = GalleryLoadTask(self)
        self._loadTask.loadBatch()

    def getLoadPercent(self) -> float:
        if self._loadTask:
            return len(self.fileItems) / len(self.filelist.files)
        return 1.0


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
                with self.tab.takeFocus() as filelist:
                    filelist.setCurrentFile(item.file)
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
        if self._loadTask:
            self._loadTask.needsAdjust = True
            return

        cols = self.calcColumnCount()
        if cols == self.columns:
            return
        self.columns = cols

        items = []
        for i in reversed(range(self._layout.count())):
            items.append(self._layout.takeAt(i))

        headers = list()
        emptyLastRow = False

        row, col = 0, 0
        for widget in (item.widget() for item in reversed(items)):
            if isinstance(widget, GalleryItem):
                widget.row = row
                self._layout.addWidget(widget, row, col, Qt.AlignmentFlag.AlignTop)
                emptyLastRow = False

                col += 1
                if col >= cols:
                    row += 1
                    col = 0
                    emptyLastRow = True

            elif isinstance(widget, GalleryHeader):
                if col > 0:
                    row += 1
                    col = 0
                widget.row = row
                headers.append(widget)
                self._layout.addWidget(widget, row, 0, 1, cols)
                row += 1

        self.rows = row
        if not emptyLastRow:
            self.rows += 1

        self._layout.update()
        self.headersUpdated.emit(headers)


    def getRowForY(self, y: int, compareBottom=False) -> int:
        rowY = QRect.bottom if compareBottom else QRect.top

        # Binary search
        lo = 0
        hi = max(self.rows-1, 0)

        while lo < hi:
            row = (lo+hi) // 2
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
        if itemAbove and isinstance(itemAbove.widget(), GalleryHeader):
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



class GalleryLoadTask(QObject):
    INTERVAL_SHORT = 10
    INTERVAL_LONG  = 1500

    def __init__(self, galleryGrid: GalleryGrid):
        super().__init__()
        self.galleryGrid = galleryGrid
        self.layout      = galleryGrid._layout
        self.numColumns  = galleryGrid.columns
        self.itemClass   = galleryGrid.itemClass

        self.run = 0
        self.needsAdjust = False
        self.aborted = False

        self.files = galleryGrid.filelist.getFiles()
        self.index = 0
        self.batchSize = 50

        self.headers: list[GalleryHeader] = list()
        self.currentHeader: GalleryHeader = None
        self.row = 0
        self.col = 0
        self.emptyLastRow = False

        self.compareTool = galleryGrid.tab.getTool("compare")

        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.loadBatch)

        # Let first iteration adjust the layout and load the first thumbnails
        initialInterval = self.INTERVAL_LONG if len(self.files) > 1000 else self.INTERVAL_SHORT
        self.timer.setInterval(initialInterval)


    @Slot()
    def loadBatch(self) -> None:
        self.run += 1
        if self.aborted:
            return

        lastNumHeaders = len(self.headers)

        end = min(self.index + self.batchSize, len(self.files))
        for self.index in range(self.index, end):
            file = self.files[self.index]

            dirname = os.path.dirname(file)
            if not self.currentHeader or self.currentHeader.dir != dirname:
                if self.col > 0:
                    self.col = 0
                    self.row += 1

                self.currentHeader = self.addHeader(dirname, self.row)
                self.headers.append(self.currentHeader)
                self.row += 1

            self.addImage(file, self.row, self.col)
            self.currentHeader.numImages += 1
            self.emptyLastRow = False

            self.col += 1
            if self.col >= self.numColumns:
                self.col = 0
                self.row += 1
                self.emptyLastRow = True

        numRows = self.row
        if not self.emptyLastRow:
            numRows += 1
        self.galleryGrid.rows = numRows

        # Update headers and their image counter
        for header in self.headers[max(0, lastNumHeaders-1):]:
            header.updateImageLabel()

        if len(self.headers) != lastNumHeaders:
            self.galleryGrid.headersUpdated.emit(self.headers)
        else:
            self.galleryGrid.loadingProgress.emit()

        # Queue next batch
        self.index += 1
        if self.index < len(self.files):
            if self.run == 2:
                self.timer.setInterval(self.INTERVAL_SHORT)
            self.timer.start()
        else:
            self.finalize()


    def finalize(self):
        self.galleryGrid._loadTask = None

        if self.needsAdjust:
            self.galleryGrid.adjustGrid()


    def addImage(self, file: str, row: int, col: int):
        galleryItem = self.itemClass(self.galleryGrid, file)
        galleryItem.row = row
        self.galleryGrid.fileItems[file] = galleryItem

        self.layout.addWidget(galleryItem, row, col, Qt.AlignmentFlag.AlignTop)

        if self.galleryGrid.filelist.getCurrentFile() == file:
            self.galleryGrid._selectedItem = galleryItem
            galleryItem.selected = True
        else:
            galleryItem.selected = False

        if self.compareTool and self.compareTool.compareFile == file:
            self.galleryGrid._selectedCompare = galleryItem
            galleryItem.setCompare(True)
        else:
            galleryItem.setCompare(False)

    def addHeader(self, dir: str, row: int) -> GalleryHeader:
        header = GalleryHeader(self.galleryGrid.tab, dir, row)
        self.layout.addWidget(header, row, 0, 1, self.numColumns)
        return header



from .gallery_item import GalleryItem, GalleryGridItem, GalleryListItem, ImageIcon
