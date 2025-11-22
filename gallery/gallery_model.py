import os, math
from typing import NamedTuple
from typing_extensions import override
from PySide6.QtCore import Qt, Signal, Slot, QAbstractTableModel, QModelIndex, QPersistentModelIndex, QTimer
from lib.filelist import FileList, DataKeys

# Imported at the bottom
# from .thumbnail_cache import ThumbnailCache


# Virtualization/Lazy Loading
# For extremely large datasets, consider implementing data virtualization
# where only the visible rows (plus a buffer) are actually in the model,
# and the rest are loaded on demand as the user scrolls. This complex solution significantly improves performance.


class HeaderItem:
    def __init__(self, path: str):
        self.path: str = path
        self.files: list[FileItem] = []
        self.row: int = 0
        self.endRow: int = 0


class FileItem:
    def __init__(self, file: str):
        self.file: str = file
        self.filename: str = os.path.basename(file)
        self.pos: GridPos = None


class GridPos(NamedTuple):
    row: int
    col: int



class GalleryModel(QAbstractTableModel):
    class ItemType:
        Header = 0
        File   = 1

    ROLE_TYPE     = Qt.ItemDataRole.UserRole.value
    ROLE_IMGSIZE  = Qt.ItemDataRole.UserRole.value + 1
    ROLE_IMGCOUNT = Qt.ItemDataRole.UserRole.value + 2

    #THUMBNAIL_UPDATE_ROLES = [Qt.ItemDataRole.DecorationRole]#, ROLE_IMGSIZE]
    THUMBNAIL_UPDATE_ROLES = [Qt.ItemDataRole.SizeHintRole]

    headersUpdated  = Signal(list)
    reloaded        = Signal()
    fileChanged     = Signal(object, int, bool)
    highlighted     = Signal()


    def __init__(self, filelist: FileList):
        super().__init__()
        self.filelist = filelist
        filelist.addListener(self)

        from .gallery_view import GalleryView
        self.view: GalleryView = None

        self.numColumns = 1
        self.numRows = 0

        self.headerItems: list[HeaderItem] = []
        self.fileItems: dict[str, FileItem] = {}
        self.posItems: dict[GridPos, FileItem | HeaderItem] = {}

        self._thumbnailUpdateTimer = QTimer(singleShot=True, interval=16)
        self._thumbnailUpdateTimer.timeout.connect(self._notifyThumbnailUpdate)
        self._updateRowStart = 2**31
        self._updateRowEnd   = -1


    def getFileItem(self, file: str) -> FileItem | None:
        return self.fileItems.get(file)


    def setNumColumns(self, numCols: int):
        self.beginResetModel()

        self.posItems = {}

        self.numColumns = numCols
        self.numRows = 0

        for header in self.headerItems:
            header.row = self.numRows
            self.posItems[GridPos(header.row, 0)] = header

            self.numRows += 1 + math.ceil(len(header.files) / numCols)
            header.endRow = self.numRows

            for i, fileItem in enumerate(header.files):
                fileGridPos = GridPos(
                    header.row + 1 + (i // numCols),
                    i % numCols
                )

                self.fileItems[fileItem.file].pos = fileGridPos
                self.posItems[fileGridPos] = fileItem

        self.endResetModel()
        self.headersUpdated.emit(self.headerItems)


    def reloadImages(self, folders: bool = True):
        self.headerItems = []

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

        self.setNumColumns(self.numColumns)
        self.reloaded.emit()


    def onFileChanged(self, currentFile: str):
        pass

    def onFileListChanged(self, currentFile: str):
        self.reloadImages()


    @Slot(str)
    def onThumbnailLoaded(self, file: str):
        if self._updateRowEnd < 0:
            self._thumbnailUpdateTimer.start()

        row = self.fileItems[file].pos.row
        self._updateRowStart = min(self._updateRowStart, row)
        self._updateRowEnd   = max(self._updateRowEnd, row)




    @Slot()
    def _notifyThumbnailUpdate(self):
        rows = self._updateRowEnd - self._updateRowStart + 1
        print(f"Update rows: {rows}")

        startIndex = self.index(self._updateRowStart, 0)
        endIndex   = self.index(self._updateRowEnd, self.numColumns-1)
        self._updateRowStart = 2**31
        self._updateRowEnd   = -1

        #self.layoutAboutToBeChanged.emit()
        self.dataChanged.emit(startIndex, endIndex, self.THUMBNAIL_UPDATE_ROLES)
        #self.layoutChanged.emit()


        # self.view.setVisible(False)
        # self.layoutAboutToBeChanged.emit()
        # self.layoutChanged.emit()
        # self.view.setVisible(True)

        #self.view.viewport().repaint()
        #self.view.viewport().update() # <<<<<<


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

        if isinstance(item, FileItem):
            match role:
                case self.ROLE_TYPE:
                    return self.ItemType.File
                case self.ROLE_IMGSIZE:
                    return self.filelist.getData(item.file, DataKeys.ImageSize)
                case Qt.ItemDataRole.DisplayRole:
                    return item.filename
                case Qt.ItemDataRole.DecorationRole:
                    thumbnail = self.filelist.getData(item.file, DataKeys.Thumbnail)
                    if thumbnail is None:
                        ThumbnailCache().updateThumbnail(self, item.file)
                    return thumbnail

        else:
            match role:
                case self.ROLE_TYPE:
                    return self.ItemType.Header
                case self.ROLE_IMGCOUNT:
                    return len(item.files)
                case Qt.ItemDataRole.DisplayRole:
                    return item.path

        return None

    @override
    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        flags = super().flags(index) | Qt.ItemFlag.ItemNeverHasChildren

        itemType = index.data(GalleryModel.ROLE_TYPE)
        if itemType != self.ItemType.File:
            flags &= ~Qt.ItemFlag.ItemIsSelectable

        if itemType == GalleryModel.ItemType.Header:
            flags |= Qt.ItemFlag.ItemIsEditable

        return flags



from .thumbnail_cache import ThumbnailCache
