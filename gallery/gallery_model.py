import os, math, time
from typing import NamedTuple
from typing_extensions import override
from collections import OrderedDict
from itertools import chain
from bisect import bisect_right
from PySide6.QtCore import Qt, Signal, Slot, QAbstractTableModel, QModelIndex, QPersistentModelIndex, QTimer, QObject, QSignalBlocker
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QPlainTextDocumentLayout
from lib import qtlib
from lib.filelist import FileList, DataKeys
from config import Config
from .gallery_caption import GalleryCaption
from .gallery_header import GalleryHeader

# Imported at the bottom
# from .thumbnail_cache import ThumbnailCache


class SelectionState:
    Unselected = 0
    Primary    = 1
    Secondary  = 2

class ItemType:
    Header = 0
    File   = 1


class HeaderItem:
    itemType = ItemType.Header
    __slots__ = ('path', 'numFiles', 'row')

    def __init__(self, path: str):
        self.path: str = path
        self.numFiles: int = 0
        self.row: int = 0

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

    CAPTION_CACHE_SIZE = 400
    CAPTION_CACHE_TTL  = 5 * 1_000_000_000  # 5 seconds

    # Thumbnail:    Qt.ItemDataRole.DecorationRole
    # Size Hint:    Qt.ItemDataRole.SizeHintRole

    ROLE_TYPE           = Qt.ItemDataRole.UserRole.value

    ROLE_FILENAME       = Qt.ItemDataRole.UserRole.value + 1
    ROLE_FILEPATH       = Qt.ItemDataRole.UserRole.value + 2
    ROLE_FOLDERPATH     = Qt.ItemDataRole.UserRole.value + 3

    ROLE_ICONS          = Qt.ItemDataRole.UserRole.value + 4
    ROLE_SELECTION      = Qt.ItemDataRole.UserRole.value + 5
    ROLE_HIGHLIGHT      = Qt.ItemDataRole.UserRole.value + 6

    ROLE_IMGSIZE        = Qt.ItemDataRole.UserRole.value + 7
    ROLE_IMGCOUNT       = Qt.ItemDataRole.UserRole.value + 8

    ROLE_CAPTION        = Qt.ItemDataRole.UserRole.value + 9
    ROLE_CAPTION_DOC    = Qt.ItemDataRole.UserRole.value + 10
    ROLE_DOC_EDITED     = Qt.ItemDataRole.UserRole.value + 11


    headersUpdated = Signal(list)


    def __init__(self, filelist: FileList, galleryCaption: GalleryCaption):
        super().__init__()
        self.filelist = filelist

        self.galleryCaption = galleryCaption
        galleryCaption.captionSrc.fileTypeUpdated.connect(self._onCaptionSourceChanged)

        self.numColumns = 1
        self.numRows = 0

        self.headersEnabled: bool | None = None
        self.headerItems: list[HeaderItem] = []
        self.fileItems: dict[str, FileItem] = {}
        self.posItems: dict[GridPos, FileItem | HeaderItem] = {}

        self._selectedItem: FileItem | None = None
        self._selectedFiles: set[str] = set()
        self._highlightedFiles: set[str] = set()

        # A small time-bounded cache to avoid I/O during relayouting. Includes the filtering/processing.
        self._captionCache: OrderedDict[str, tuple[str, int]] = OrderedDict()

        # In list view, captions are cached in documents that include the undo stack.
        self._docs: OrderedDict[str, QTextDocument] = OrderedDict()
        self._docsEdited: dict[str, QTextDocument] = {}
        self._docFont = qtlib.getMonospaceFont()

        self._thumbnailUpdateQueue = ThumbnailUpdateQueue(self)


    def getFileItem(self, file: str) -> FileItem | None:
        return self.fileItems.get(file)

    def getFileIndex(self, file: str) -> QModelIndex:
        if item := self.fileItems.get(file):
            return self.index(*item.pos)
        return QModelIndex()

    def headerIndexForRow(self, row: int):
        index = bisect_right(self.headerItems, row, key=lambda header: header.row)
        return max(index-1, 0)


    @Slot()
    def _onCaptionSourceChanged(self):
        self._captionCache = OrderedDict()

    def resetCaptions(self, clearDocs: bool = True, modelReset: bool = True):
        self._captionCache = OrderedDict()

        if clearDocs:
            for doc in chain(self._docs.values(), self._docsEdited.values()):
                doc.deleteLater()

            self._docs = OrderedDict()
            self._docsEdited = {}

        if modelReset:
            self.modelReset.emit()


    def setNumColumns(self, numCols: int, forceReset=False):
        if numCols != self.numColumns:
            self.numColumns = numCols
            self._buildGrid()
        elif forceReset:
            self.modelReset.emit()


    def reloadImages(self):
        self._selectedItem = None
        self._selectedFiles = set()
        self._highlightedFiles = set()

        self.fileItems = {file: FileItem(file) for file in self.filelist.getFiles()}
        if self.fileItems:
            self._selectedItem = self.fileItems[self.filelist.currentFile]
            self._selectedFiles.update(self.filelist.selectedFiles)

        # Clear list view documents, but keep edited documents for files which still exist in FileList
        docsEdited = {}
        for file, doc in self._docsEdited.items():
            if file in self.fileItems:
                docsEdited[file] = doc
            else:
                doc.deleteLater()
        self._docsEdited = docsEdited

        for doc in self._docs.values():
            doc.deleteLater()
        self._docs = OrderedDict()

        # Always reset headers when reloading
        self.headersEnabled = None
        self.updateGrid()

    @Slot(bool)
    def updateGrid(self, headers: bool = True):
        headers &= self.filelist.isOrderWithFolders()
        if headers == self.headersEnabled:
            self._buildGrid()
            return

        self.headersEnabled = headers
        self.headerItems = []

        if headers:
            currentDir = None
            currentHeader: HeaderItem = None

            for file in self.filelist.getFiles():
                dirname = os.path.dirname(file)
                if currentDir != dirname:
                    currentDir = dirname

                    currentHeader = HeaderItem(currentDir)
                    self.headerItems.append(currentHeader)

                currentHeader.numFiles += 1

        else:
            header = HeaderItem(GalleryHeader.ALL_FILES_DIR)
            header.numFiles = self.filelist.getNumFiles()
            self.headerItems.append(header)

        self._buildGrid()

    def _buildGrid(self):
        self.beginResetModel()

        self.posItems = {}
        self.numRows = 0

        fileIt = iter(self.filelist.getOrderedFiles())
        for header in self.headerItems:
            header.row = self.numRows
            self.posItems[GridPos(header.row, 0)] = header
            self.numRows += 1 + math.ceil(header.numFiles / self.numColumns)

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
        if key not in (DataKeys.CaptionState, DataKeys.CropState, DataKeys.MaskState):
            return

        roles = [self.ROLE_ICONS]

        # Reload caption when it was edited and saved in CaptionWindow
        if (self.galleryCaption.captionsEnabled
            and key == DataKeys.CaptionState
            and self.filelist.getData(file, key) == DataKeys.IconStates.Saved
        ):
            roles.append(self.ROLE_CAPTION)
            self._captionCache.pop(file, None)

            if doc := self._docs.get(file): # Only reload when document is unedited
                with QSignalBlocker(doc):
                    qtlib.setTextPreserveUndo(QTextCursor(doc), self._getCaption(file))

        if item := self.fileItems.get(file):
            index = self.index(*item.pos)
            self.dataChanged.emit(index, index, roles)


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


    def _getCaption(self, file: str) -> str:
        entry = self._captionCache.get(file)
        now = time.monotonic_ns()

        if entry is None:
            caption = self.galleryCaption.loadCaption(file)
            self._captionCache[file] = (caption, now)

            if len(self._captionCache) > self.CAPTION_CACHE_SIZE:
                self._captionCache.popitem(last=False)

        else:
            caption, insertTime = entry
            if insertTime < (now - self.CAPTION_CACHE_TTL):
                caption = self.galleryCaption.loadCaption(file)
                self._captionCache[file] = (caption, now)

            self._captionCache.move_to_end(file)

        return caption


    def _getDocument(self, file: str) -> QTextDocument:
        if doc := self._docsEdited.get(file):
            return doc

        if doc := self._docs.get(file):
            self._docs.move_to_end(file)
            return doc

        doc = QTextDocument(self)
        doc.setDocumentLayout(QPlainTextDocumentLayout(doc))
        doc.setDefaultFont(self._docFont)
        doc.setPlainText(self._getCaption(file))
        self._storeUnchangedDocument(file, doc)
        return doc

    def _storeUnchangedDocument(self, file: str, doc: QTextDocument):
        self._docs[file] = doc
        if len(self._docs) > Config.galleryCacheSize:
            self._docs.popitem(last=False)


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

        if role == self.ROLE_TYPE:
            return item.itemType

        if item.itemType == ItemType.File:
            match role:
                case self.ROLE_FILENAME:
                    return item.filename

                case self.ROLE_FILEPATH:
                    return item.path

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

                case self.ROLE_IMGSIZE:
                    return self.filelist.getData(item.path, DataKeys.ImageSize)

                case self.ROLE_CAPTION:
                    return self._getCaption(item.path)

                case self.ROLE_CAPTION_DOC:
                    return self._getDocument(item.path)

                case self.ROLE_DOC_EDITED:
                    return item.path in self._docsEdited

        else: # ItemType.Header
            match role:
                case self.ROLE_FOLDERPATH:
                    return item.path

                case self.ROLE_IMGCOUNT:
                    return item.numFiles

        return None


    @override
    def setData(self, index: QModelIndex | QPersistentModelIndex, value, role: int = Qt.ItemDataRole.DisplayRole) -> bool:
        item = self.posItems.get(GridPos(index.row(), index.column()))
        if item is None:
            return False

        if role == self.ROLE_DOC_EDITED:
            if value:
                if doc := self._docs.pop(item.path, None):
                    self._docsEdited[item.path] = doc
            else:
                if doc := self._docsEdited.pop(item.path, None):
                    self._storeUnchangedDocument(item.path, doc)

            # Don't notify with dataChanged
            return True

        return False


    @override
    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        itemType = index.data(GalleryModel.ROLE_TYPE)
        if itemType == ItemType.File:
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemNeverHasChildren
        return Qt.ItemFlag.NoItemFlags



from .thumbnail_cache import ThumbnailCache
