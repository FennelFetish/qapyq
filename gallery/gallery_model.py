import os, math
from typing import NamedTuple
from typing_extensions import override
from bisect import bisect_right
from PySide6.QtCore import Qt, Signal, Slot, QAbstractTableModel, QModelIndex, QPersistentModelIndex, QTimer, QObject
from lib.filelist import FileList, DataKeys
from .gallery_caption import GalleryCaption
from .gallery_header import GalleryHeader

# Imported at the bottom
# from .thumbnail_cache import ThumbnailCache


# Virtualization/Lazy Loading
# For extremely large datasets, consider implementing data virtualization
# where only the visible rows (plus a buffer) are actually in the model,
# and the rest are loaded on demand as the user scrolls. This complex solution significantly improves performance.


class SelectionState:
    Unselected = 0
    Primary    = 1
    Secondary  = 2

class ItemType:
    Header = 0
    File   = 1


class HeaderItem:
    itemType = ItemType.Header
    __slots__ = ('path', 'numFiles', 'row', 'endRow')

    def __init__(self, path: str):
        self.path: str = path
        self.numFiles: int = 0
        self.row: int = 0
        self.endRow: int = 0

class FileItem:
    itemType = ItemType.File
    __slots__ = ('path', 'filename', 'pos')

    def __init__(self, file: str):
        self.path: str = file
        self.filename: str = os.path.basename(file)
        self.pos: GridPos = None


class GridPos(NamedTuple):
    row: int
    col: int



class ThumbnailUpdateQueue(QObject):
    ROLES = [Qt.ItemDataRole.SizeHintRole]

    def __init__(self, model: 'GalleryModel'):
        super().__init__(model)
        self.model = model
        self.reset()

        self.timer = QTimer(singleShot=True, interval=20)
        self.timer.timeout.connect(self._emitUpdates)

    def reset(self):
        self.startRow = 2**31
        self.endRow   = -1

    def add(self, row: int):
        if self.endRow < 0:
            self.timer.start()
        elif row < self.startRow - 5 or row > self.endRow + 5:
            self._emitUpdates()
            self.add(row)
            return

        self.startRow = min(self.startRow, row)
        self.endRow   = max(self.endRow,   row)

    @Slot()
    def _emitUpdates(self):
        startIndex = self.model.index(self.startRow, 0)
        endIndex   = self.model.index(self.endRow, self.model.numColumns-1)
        self.reset()

        self.model.dataChanged.emit(startIndex, endIndex, self.ROLES)



class GalleryModel(QAbstractTableModel):
    ItemType = ItemType

    # File path:    Qt.ItemDataRole.DisplayRole
    # Thumbnail:    Qt.ItemDataRole.DecorationRole

    ROLE_TYPE           = Qt.ItemDataRole.UserRole.value
    ROLE_ICONS          = Qt.ItemDataRole.UserRole.value + 1
    ROLE_SELECTION      = Qt.ItemDataRole.UserRole.value + 2
    ROLE_HIGHLIGHT      = Qt.ItemDataRole.UserRole.value + 3
    ROLE_FILENAME       = Qt.ItemDataRole.UserRole.value + 4
    ROLE_CAPTION        = Qt.ItemDataRole.UserRole.value + 5
    ROLE_CAPTION_EDIT   = Qt.ItemDataRole.UserRole.value + 6
    ROLE_IMGSIZE        = Qt.ItemDataRole.UserRole.value + 7
    ROLE_IMGCOUNT       = Qt.ItemDataRole.UserRole.value + 8

    headersUpdated  = Signal(list)


    def __init__(self, filelist: FileList, galleryCaption: GalleryCaption):
        super().__init__()
        self.galleryCaption = galleryCaption

        self.filelist = filelist
        filelist.addListener(self)
        filelist.addDataListener(self)
        filelist.addSelectionListener(self)

        self.numColumns = 1
        self.numRows = 0

        self.headerItems: list[HeaderItem] = []
        self.fileItems: dict[str, FileItem] = {}
        self.posItems: dict[GridPos, FileItem | HeaderItem] = {}

        self._selectedItem: FileItem | None = None
        self._selectedFiles: set[str] = set()
        self._highlightedFiles: set[str] = set()

        self._editedCaptions: dict[str, str] = {}

        self._thumbnailUpdateQueue = ThumbnailUpdateQueue(self)


    def getFileItem(self, file: str) -> FileItem | None:
        return self.fileItems.get(file)

    def headerIndexForRow(self, row: int):
        index = bisect_right(self.headerItems, row, key=lambda header: header.row)
        return max(index-1, 0)

    def resetCaptions(self):
        self._editedCaptions = {}
        self.modelReset.emit()


    def setNumColumns(self, numCols: int, forceReset=False):
        if numCols != self.numColumns:
            self.numColumns = numCols
            self.buildGrid()
        elif forceReset:
            self.modelReset.emit()


    def buildGrid(self):
        self.beginResetModel()

        self.posItems = {}
        self.numRows = 0

        fileIt = iter(self.filelist.getOrderedFiles())
        for header in self.headerItems:
            header.row = self.numRows
            self.posItems[GridPos(header.row, 0)] = header

            self.numRows += 1 + math.ceil(header.numFiles / self.numColumns)
            header.endRow = self.numRows

            for i in range(header.numFiles):
                file = next(fileIt)
                fileItem = self.fileItems[file]

                fileGridPos = GridPos(
                    header.row + 1 + (i // self.numColumns),
                    i % self.numColumns
                )

                fileItem.pos = fileGridPos
                self.posItems[fileGridPos] = fileItem

        self.endResetModel()
        self.headersUpdated.emit(self.headerItems)

        assert not self.headerItems or next(fileIt, None) is None


    @Slot(bool)
    def reloadImages(self, headers: bool = True):
        headers &= self.filelist.isOrderWithFolders()

        self.headerItems = []
        self.fileItems = {}

        self._selectedItem = None
        self._selectedFiles = set()
        self._highlightedFiles = set()

        # TODO: Only clear files which are missing from FileList
        self._editedCaptions = {}

        currentDir = None
        currentHeader: HeaderItem = None

        if not headers:
            currentHeader = HeaderItem(GalleryHeader.ALL_FILES_DIR)
            self.headerItems.append(currentHeader)

        for file in self.filelist.getOrderedFiles():
            if headers:
                dirname = os.path.dirname(file)
                if currentDir != dirname:
                    currentDir = dirname

                    currentHeader = HeaderItem(currentDir)
                    self.headerItems.append(currentHeader)

            self.fileItems[file] = FileItem(file)
            currentHeader.numFiles += 1

        if self.fileItems:
            self._selectedItem = self.fileItems[self.filelist.currentFile]
            self._selectedFiles.update(self.filelist.selectedFiles)

        self.buildGrid()


    @Slot(str)
    def onThumbnailLoaded(self, file: str):
        row = self.fileItems[file].pos.row
        self._thumbnailUpdateQueue.add(row)


    def onFileChanged(self, currentFile: str):
        if self._selectedItem:
            index = self.index(*self._selectedItem.pos)
            self.dataChanged.emit(index, index, [self.ROLE_SELECTION])

        self._selectedItem = self.fileItems.get(currentFile)
        if self._selectedItem:
            index = self.index(*self._selectedItem.pos)
            self.dataChanged.emit(index, index, [self.ROLE_SELECTION])

    def onFileListChanged(self, currentFile: str):
        self.reloadImages()


    def onFileSelectionChanged(self, selectedFiles: set[str]):
        toggleFiles = self._selectedFiles.symmetric_difference(selectedFiles)
        for file in toggleFiles:
            if item := self.fileItems.get(file):
                index = self.index(*item.pos)
                self.dataChanged.emit(index, index, [self.ROLE_SELECTION])

        self._selectedFiles = selectedFiles.copy()
        self.highlightFiles([])


    def onFileDataChanged(self, file: str, key: str):
        item = self.fileItems.get(file)
        if not item:
            return

        match key:
            # case DataKeys.ImageSize:
            #     self.dataChanged.emit(index, index, [self.ROLE_IMGSIZE])

            case DataKeys.CaptionState | DataKeys.CropState | DataKeys.MaskState:
                index = self.index(*item.pos)
                self.dataChanged.emit(index, index, [self.ROLE_ICONS])

        if (
            self.galleryCaption.captionsEnabled
            and key == DataKeys.CaptionState
            and self.filelist.getData(file, key) == DataKeys.IconStates.Saved
            and (item := self.fileItems[file])
        ):
            index = self.index(*item.pos)
            self.dataChanged.emit(index, index, [self.ROLE_CAPTION])

            # if isinstance(item, GalleryListItem):
            #     if not item.captionEdited:
            #         item.loadCaption(False)
            # else:
            #     item.reloadCaption = True
            #     item.update()


    def highlightFiles(self, files: list[str]):
        toggleFiles = self._highlightedFiles.symmetric_difference(files)

        self._highlightedFiles = set(files)

        for file in toggleFiles:
            if item := self.fileItems.get(file):
                index = self.index(*item.pos)
                self.dataChanged.emit(index, index, [self.ROLE_HIGHLIGHT])

    @property
    def numHighlighted(self) -> int:
        return len(self._highlightedFiles)


    # === QAbstractTableModel Interface ===

    @override
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()):
        if parent.isValid():
            return 0
        return self.numRows

    @override
    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()):
        return self.numColumns

    @override
    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        item = self.posItems.get(GridPos(index.row(), index.column()))
        if item is None:
            return None

        match role:
            case self.ROLE_TYPE:
                return item.itemType
            case Qt.ItemDataRole.DisplayRole:
                return item.path

        if item.itemType == ItemType.File:
            match role:
                case Qt.ItemDataRole.DecorationRole:
                    thumbnail = self.filelist.getData(item.path, DataKeys.Thumbnail)
                    if thumbnail is None:
                        ThumbnailCache().updateThumbnail(self, item.path)
                    return thumbnail

                case self.ROLE_ICONS:
                    return self.filelist.getMultipleData(item.path, (DataKeys.CaptionState, DataKeys.CropState, DataKeys.MaskState))

                case self.ROLE_SELECTION:
                    if item.path == self.filelist.currentFile:
                        return SelectionState.Primary
                    elif self.filelist.isSelected(item.path):
                        return SelectionState.Secondary
                    else:
                        return SelectionState.Unselected

                case self.ROLE_HIGHLIGHT:
                    return item.path in self._highlightedFiles

                case self.ROLE_FILENAME:
                    return item.filename

                case self.ROLE_CAPTION:
                    return self.galleryCaption.loadCaption(item.path)

                case self.ROLE_CAPTION_EDIT:
                    return self._editedCaptions.get(item.path)

                case self.ROLE_IMGSIZE:
                    return self.filelist.getData(item.path, DataKeys.ImageSize)

        else: # ItemType.Header
            match role:
                case self.ROLE_IMGCOUNT:
                    return item.numFiles

        return None


    def setData(self, index: QModelIndex | QPersistentModelIndex, value, role: int = Qt.ItemDataRole.DisplayRole) -> bool:
        item = self.posItems.get(GridPos(index.row(), index.column()))
        if item is None:
            return False

        if role == self.ROLE_CAPTION_EDIT:
            if isinstance(value, str):
                # Don't notify dataChanged
                self._editedCaptions[item.path] = value
                return True

            elif value is None:
                self._editedCaptions.pop(item.path, None)
                self.dataChanged.emit(index, index, [self.ROLE_CAPTION_EDIT])
                return True

        return False


    @override
    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        itemType = index.data(GalleryModel.ROLE_TYPE)
        if itemType == ItemType.File:
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemNeverHasChildren
        return Qt.ItemFlag.NoItemFlags



from .thumbnail_cache import ThumbnailCache
