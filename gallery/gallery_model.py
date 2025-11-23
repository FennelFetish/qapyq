import os, math
from typing import NamedTuple
from typing_extensions import override
from PySide6.QtCore import Qt, Signal, Slot, QAbstractTableModel, QModelIndex, QPersistentModelIndex, QTimer, QObject
from lib.filelist import FileList, DataKeys

# Imported at the bottom
# from .thumbnail_cache import ThumbnailCache


# Virtualization/Lazy Loading
# For extremely large datasets, consider implementing data virtualization
# where only the visible rows (plus a buffer) are actually in the model,
# and the rest are loaded on demand as the user scrolls. This complex solution significantly improves performance.



class ImageIcon:
    Caption = "caption"
    Crop    = "crop"
    Mask    = "mask"

class SelectionState:
    Unselected = 0
    Primary    = 1
    Secondary  = 2

class ItemType:
    Header = 0
    File   = 1


class HeaderItem:
    __slots__ = ('path', 'files', 'row', 'endRow')

    itemType = ItemType.Header

    def __init__(self, path: str):
        self.path: str = path
        self.files: list[FileItem] = []
        self.row: int = 0
        self.endRow: int = 0

class FileItem:
    __slots__ = ('path', 'label', 'pos')

    itemType = ItemType.File

    def __init__(self, file: str):
        self.path: str = file
        self.label: str = os.path.basename(file)
        self.pos: GridPos = None


class GridPos(NamedTuple):
    row: int
    col: int



class ThumbnailUpdateQueue(QObject):
    ROLES = [Qt.ItemDataRole.SizeHintRole]

    def __init__(self, model: 'GalleryModel'):
        super().__init__()
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

        #self.layoutAboutToBeChanged.emit()
        self.model.dataChanged.emit(startIndex, endIndex, self.ROLES)
        #self.layoutChanged.emit()



class GalleryModel(QAbstractTableModel):
    ItemType = ItemType

    ROLE_TYPE       = Qt.ItemDataRole.UserRole.value
    ROLE_LABEL      = Qt.ItemDataRole.UserRole.value + 1
    ROLE_IMGSIZE    = Qt.ItemDataRole.UserRole.value + 2
    ROLE_IMGCOUNT   = Qt.ItemDataRole.UserRole.value + 3
    ROLE_ICONS      = Qt.ItemDataRole.UserRole.value + 4
    ROLE_SELECTION  = Qt.ItemDataRole.UserRole.value + 5

    headersUpdated  = Signal(list)
    highlighted     = Signal()


    def __init__(self, filelist: FileList):
        super().__init__()
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

        self._thumbnailUpdateQueue = ThumbnailUpdateQueue(self)


    def getFileItem(self, file: str) -> FileItem | None:
        return self.fileItems.get(file)


    def setNumColumns(self, numCols: int, forceSignal=False):
        if numCols != self.numColumns:
            self.numColumns = numCols
            self.rebuildModel()
        elif forceSignal:
            self.modelReset.emit()


    def rebuildModel(self):
        self.beginResetModel()

        self.posItems = {}
        self.numRows = 0

        for header in self.headerItems:
            header.row = self.numRows
            self.posItems[GridPos(header.row, 0)] = header

            self.numRows += 1 + math.ceil(len(header.files) / self.numColumns)
            header.endRow = self.numRows

            for i, fileItem in enumerate(header.files):
                fileGridPos = GridPos(
                    header.row + 1 + (i // self.numColumns),
                    i % self.numColumns
                )

                self.fileItems[fileItem.path].pos = fileGridPos
                self.posItems[fileGridPos] = fileItem

        self.endResetModel()
        self.headersUpdated.emit(self.headerItems)


    def reloadImages(self, headers=True):
        self.headerItems = []
        self.fileItems = {}

        self._selectedItem = None
        self._selectedFiles.clear()

        currentDir = ""
        currentHeader: HeaderItem = None

        for file in self.filelist.getOrderedFiles():
            dirname = os.path.dirname(file)
            if currentDir != dirname:
                currentDir = dirname

                currentHeader = HeaderItem(currentDir)
                self.headerItems.append(currentHeader)

            item = FileItem(file)
            self.fileItems[file] = item
            currentHeader.files.append(item)

        self.rebuildModel()


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
        self.onFileChanged(currentFile)


    def onFileSelectionChanged(self, selectedFiles: set[str]):
        toggleFiles = self._selectedFiles.symmetric_difference(selectedFiles)
        for file in toggleFiles:
            if item := self.fileItems.get(file):
                index = self.index(*item.pos)
                self.dataChanged.emit(index, index, [self.ROLE_SELECTION])

        self._selectedFiles = selectedFiles.copy()

        #self.highlightFiles([])


    def onFileDataChanged(self, file: str, key: str):
        item = self.fileItems.get(file)
        if not item:
            return

        match key:
            # case DataKeys.ImageSize:
            #     self.dataChanged.emit(index, index, [self.ROLE_IMGSIZE])

            case DataKeys.CaptionState | DataKeys.CropState | DataKeys.MaskState:
                # iconState = self.filelist.getData(file, key)
                # item.setIcon(key, iconState)
                index = self.index(*item.pos)
                self.dataChanged.emit(index, index, [self.ROLE_ICONS])

        # if (
        #     self.ctx.captionsEnabled
        #     and key == DataKeys.CaptionState
        #     and self.filelist.getData(file, key) == DataKeys.IconStates.Saved
        #     and (item := self.fileItems[file])
        # ):
        #     if isinstance(item, GalleryListItem):
        #         if not item.captionEdited:
        #             item.loadCaption(False)
        #     else:
        #         item.reloadCaption = True
        #         item.update()


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
                case self.ROLE_LABEL:
                    return item.label

                case self.ROLE_IMGSIZE:
                    return self.filelist.getData(item.path, DataKeys.ImageSize)

                case self.ROLE_ICONS:
                    return {
                        ImageIcon.Caption: self.filelist.getData(item.path, DataKeys.CaptionState),
                        ImageIcon.Crop:    self.filelist.getData(item.path, DataKeys.CropState),
                        ImageIcon.Mask:    self.filelist.getData(item.path, DataKeys.MaskState)
                    }

                case self.ROLE_SELECTION:
                    if item.path == self.filelist.currentFile:
                        return SelectionState.Primary
                    elif self.filelist.isSelected(item.path):
                        return SelectionState.Secondary
                    else:
                        return SelectionState.Unselected

                case Qt.ItemDataRole.DecorationRole:
                    thumbnail = self.filelist.getData(item.path, DataKeys.Thumbnail)
                    if thumbnail is None:
                        ThumbnailCache().updateThumbnail(self, item.path)
                    return thumbnail

        else:
            match role:
                case self.ROLE_IMGCOUNT:
                    return len(item.files)

        return None

    @override
    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        itemType = index.data(GalleryModel.ROLE_TYPE)
        if itemType == ItemType.File:
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemNeverHasChildren
        else:
            flags = Qt.ItemFlag.NoItemFlags

        # if itemType == GalleryModel.ItemType.Header:
        #     flags |= Qt.ItemFlag.ItemIsEditable

        return flags



from .thumbnail_cache import ThumbnailCache
