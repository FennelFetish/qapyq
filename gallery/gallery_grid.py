from __future__ import annotations
import os
from contextlib import contextmanager
from typing import NamedTuple
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, Signal, Slot, QRect, QPoint, QObject, QTimer, QEvent
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
    fileChanged     = Signal(object, int, bool)
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
        self._selectedFiles: set[str] = set()
        self._highlightedFiles: set[str] = set()

        self._loadTask: GalleryLoadTask | None = None

        # TODO: This layout has a maximum height of 524287. Why??
        self._layout = QtWidgets.QGridLayout()
        self._layout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetNoConstraint)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(self.itemClass.getSpacing())
        self.setLayout(self._layout)

        self.filelist.addListener(self)
        self.filelist.addSelectionListener(self)
        self.filelist.addDataListener(self)

        self._eventFilter = GalleryDragEventFilter()
        self.installEventFilter(self._eventFilter)

    def deleteLater(self):
        self.removeEventFilter(self._eventFilter)
        self.clearLayout()

        self._selectedItem = None
        self.fileItems = dict()
        super().deleteLater()


    @property
    def selectedItem(self) -> GalleryItem |  None:
        return self._selectedItem


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


    @contextmanager
    def noGridUpdate(self):
        try:
            self.setVisible(False)
            #self.setUpdatesEnabled(False)
            yield self
        finally:
            #self.setUpdatesEnabled(True)
            self.setVisible(True)


    def clearTask(self):
        if self._loadTask:
            self._loadTask.aborted = True
            self._loadTask = None

    def clearLayout(self):
        self.clearTask()
        for i in reversed(range(self._layout.count())):
            item = self._layout.takeAt(i)
            if widget := item.widget():
                widget.deleteLater()


    def reloadImages(self, clear=True):
        self._selectedItem = None
        self._highlightedFiles.clear()

        if clear:
            self.fileItems = dict()
            self.clearLayout()
            itemsKeep = set()
        else:
            self.clearTask()
            itemsKeep = self.fileItems.keys() & self.filelist.getFiles()

        self._loadGrid(itemsKeep)


    def _loadGrid(self, itemsKeep: set[str]):
        currentFile = self.filelist.getCurrentFile()
        files = self.filelist.getFiles()

        # Take all headers and remove unneded GalleryItems from layout and 'self.fileItems'
        headers: dict[str, GalleryHeader] = dict()
        for i in reversed(range(self._layout.count())):
            widget: GalleryHeader | GalleryItem = self._layout.takeAt(i).widget()
            if isinstance(widget, GalleryHeader):
                headers[widget.dir] = widget
            elif widget.file not in itemsKeep:
                self.fileItems.pop(widget.file)
                widget.deleteLater()

        headerInfo = dict[str, HeaderInfo]() # Sorted
        createTasks = list[CreateTask]()

        row = col = 0
        currentDir = ""
        currentHeader: HeaderInfo = None
        emptyLastRow = False

        # Assign each file and header to row and column in grid.
        # Reuse existing GalleryItems/GalleryHeaders and immediately move them to their new place.
        # Add a CreateTask for new files and headers.
        for file in files:
            dirname = os.path.dirname(file)
            if currentDir != dirname:
                currentDir = dirname

                currentHeader = HeaderInfo()
                headerInfo[dirname] = currentHeader

                if col > 0:
                    col = 0
                    row += 1

                # Add header
                if header := headers.pop(dirname, None):
                    currentHeader.header = header
                    header.row = row
                    self._layout.addWidget(header, row, 0, 1, self.columns)
                else:
                    createTasks.append(CreateTask(row, 0, True, dirname))

                row += 1

            # Add Image
            if item := self.fileItems.get(file):
                item.row = row
                self._layout.addWidget(item, row, col, Qt.AlignmentFlag.AlignTop)

                if file == currentFile:
                    self._selectedItem = item
                    item.selected = True
                elif item.selected:
                    item.selected = False
            else:
                createTasks.append(CreateTask(row, col, False, file))

            currentHeader.fileCount += 1
            emptyLastRow = False

            col += 1
            if col >= self.columns:
                col = 0
                row += 1
                emptyLastRow = True

        self.rows = row
        if not emptyLastRow:
            self.rows += 1

        # Delete remaining (unused) headers
        for header in headers.values():
            header.deleteLater()

        for info in headerInfo.values():
            info.updateHeader()

        self.headersUpdated.emit( HeaderInfo.getLoadedHeaders(headerInfo) )

        if createTasks:
            self._loadTask = GalleryLoadTask(self, headerInfo, createTasks)
            self._loadTask.loadBatch()


    def getLoadPercent(self) -> float:
        if self._loadTask and len(self.filelist.files) > 0:
            return len(self.fileItems) / len(self.filelist.files)
        return 1.0


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

        widgets = list[GalleryHeader | GalleryItem]()
        for i in reversed(range(self._layout.count())):
            widgets.append(self._layout.takeAt(i).widget())

        headers = list[GalleryHeader]()
        emptyLastRow = False

        row, col = 0, 0
        for widget in reversed(widgets):
            if isinstance(widget, GalleryHeader):
                if col > 0:
                    row += 1
                    col = 0

                widget.row = row
                headers.append(widget)
                self._layout.addWidget(widget, row, 0, 1, cols)
                row += 1

            else:
                widget.row = row
                self._layout.addWidget(widget, row, col, Qt.AlignmentFlag.AlignTop)
                emptyLastRow = False

                col += 1
                if col >= cols:
                    row += 1
                    col = 0
                    emptyLastRow = True

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

    def getItemAtPos(self, pos: QPoint) -> GalleryItem | None:
        row = self.getRowForY(pos.y(), True)
        for col in range(self.columns):
            item = self._layout.itemAtPosition(row, col)
            if item and item.geometry().contains(pos):
                widget = item.widget()
                return widget if isinstance(widget, GalleryItem) else None
        return None


    def onFileChanged(self, currentFile: str):
        item = self.fileItems[currentFile]

        if self._selectedItem:
            self._selectedItem.selected = False
        item.selected = True
        self._selectedItem = item

        item.takeFocus()
        self.fileChanged.emit(item, item.row, False)

    def onFileListChanged(self, currentFile: str):
        # When files are appended, the selection is kept.
        # When files are removed, update the selection.
        # The gallery should scroll to the selection instead of the top.
        if (selectedItem := self._selectedItem) and selectedItem.file != currentFile:
            selectedItem.selected = False
            if selectedItem := self.fileItems.get(currentFile):
                selectedItem.selected = True
                self._selectedItem = selectedItem

        self.reloadImages(clear=False)
        if selectedItem:
            self.fileChanged.emit(selectedItem, selectedItem.row, True)
        else:
            self.reloaded.emit()

    def onFileSelectionChanged(self, selectedFiles: set[str]):
        toggleFiles = self._selectedFiles.symmetric_difference(selectedFiles)
        for file in toggleFiles:
            self.fileItems[file].selectedSecondary ^= True
        self._selectedFiles = selectedFiles.copy()

        self.highlightFiles([])

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


    def highlightFiles(self, files: list[str]):
        toggleFiles = self._highlightedFiles.symmetric_difference(files)
        for file in toggleFiles:
            item = self.fileItems[file]
            item.highlight ^= True
            item.update()

        self._highlightedFiles.clear()
        self._highlightedFiles.update(files)



class GalleryDragEventFilter(QObject):
    MIN_DIST2 = 40 ** 2

    def __init__(self):
        super().__init__()
        self._startPos: QPoint | None = None

    def eventFilter(self, watchedGallery: GalleryGrid, event: QEvent) -> bool:
        if event.type() != QEvent.Type.MouseMove:
            self._startPos = None
            return False

        mouseEvent: QtGui.QMouseEvent = event
        if mouseEvent.buttons() & Qt.MouseButton.LeftButton:
            pos = mouseEvent.position().toPoint()
            if self._checkDist(pos) and (item := watchedGallery.getItemAtPos(pos)):
                item.onDragOver(mouseEvent)
                self._startPos = pos # Optimization: Only call onDragOver at intervals
                return True

        return False

    def _checkDist(self, pos: QPoint) -> bool:
        if self._startPos:
            dx = pos.x() - self._startPos.x()
            dy = pos.y() - self._startPos.y()
            return (dx*dx + dy*dy) > self.MIN_DIST2

        self._startPos = pos
        return False



class HeaderInfo:
    def __init__(self):
        self.header: GalleryHeader | None = None
        self.fileCount: int = 0

    def updateHeader(self):
        if self.header:
            self.header.updateImageLabel(self.fileCount)

    @staticmethod
    def getLoadedHeaders(headerInfo: dict[str, HeaderInfo]) -> list[GalleryHeader]:
        return [info.header for info in headerInfo.values() if info.header]


class CreateTask(NamedTuple):
    row: int
    col: int
    isHeader: bool
    file: str  # Or directory path


class GalleryLoadTask(QObject):
    BATCH_SIZE_FIRST = 1000
    BATCH_SIZE       = 10000

    # Let first iteration adjust the layout and load the first thumbnails
    INTERVAL_FIRST   = 1000
    INTERVAL         = 10

    def __init__(self, galleryGrid: GalleryGrid, headers: dict[str, HeaderInfo], createItems: list[CreateTask]):
        super().__init__()
        self.galleryGrid = galleryGrid
        self.layout      = galleryGrid._layout
        self.numColumns  = galleryGrid.columns
        self.itemClass   = galleryGrid.itemClass

        self.headers = headers
        self.createItems = createItems

        self.needsAdjust = False
        self.aborted = False

        self.index = 0
        self.readyIndex = 0

        self.batchSize = self.BATCH_SIZE_FIRST
        self.interval = self.INTERVAL_FIRST

        self.timer = QTimer(singleShot=True, interval=self.interval)
        self.timer.timeout.connect(self.loadBatch)


    @Slot()
    def loadBatch(self):
        if self.aborted:
            return

        newHeaders = False

        with self.galleryGrid.noGridUpdate():
            end = min(self.index + self.batchSize, len(self.createItems))
            for self.index in range(self.index, end):
                row, col, isHeader, file = self.createItems[self.index]

                if isHeader:
                    self.addHeader(file, row)
                    newHeaders = True
                else:
                    self.addImage(file, row, col)

                if row >= self.galleryGrid.rows:
                    self.galleryGrid.rows = row + 1

        if newHeaders:
            self.galleryGrid.headersUpdated.emit( HeaderInfo.getLoadedHeaders(self.headers) )
        else:
            self.galleryGrid.loadingProgress.emit()

        # Queue next batch
        self.index += 1
        if self.index < len(self.createItems):
            readyIndex = self.index // 100
            readyIndex = max(readyIndex, self.readyIndex+(self.numColumns*5)+1)
            self.setReady(readyIndex)

            self.batchSize = self.BATCH_SIZE
            self.timer.setInterval(self.interval)
            self.timer.start()
            self.interval = self.INTERVAL
        else:
            self.setReady(self.index)
            self.finalize()


    def setReady(self, toIndex: int):
        toIndex = min(toIndex, len(self.createItems))
        for index in range(self.readyIndex, toIndex):
            _, _, isHeader, file = self.createItems[index]
            if not isHeader:
                item = self.galleryGrid.fileItems[file]
                item.ready = True

        self.readyIndex = toIndex


    def finalize(self):
        self.galleryGrid.clearTask()
        if self.needsAdjust:
            self.galleryGrid.adjustGrid()


    def addImage(self, file: str, row: int, col: int):
        galleryItem = self.itemClass(self.galleryGrid, file)
        galleryItem.row = row
        self.galleryGrid.fileItems[file] = galleryItem

        self.layout.addWidget(galleryItem, row, col, Qt.AlignmentFlag.AlignTop)

        filelist = self.galleryGrid.filelist
        if filelist.getCurrentFile() == file:
            self.galleryGrid._selectedItem = galleryItem
            galleryItem.selected = True

        if filelist.isSelected(file):
            galleryItem.selectedSecondary = True

    def addHeader(self, dir: str, row: int):
        header = GalleryHeader(self.galleryGrid.tab, dir, row)
        self.layout.addWidget(header, row, 0, 1, self.numColumns)

        headerInfo = self.headers[dir]
        headerInfo.header = header
        headerInfo.updateHeader()



from .gallery_item import GalleryItem, GalleryGridItem, GalleryListItem, ImageIcon
