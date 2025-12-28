import os, enum, time
from typing import Iterable, Iterator, Any, Callable
from bisect import bisect_left, bisect_right
from PySide6.QtCore import Qt, Signal, Slot, QThreadPool, QRunnable, QObject, QMutex, QMutexLocker
from config import Config
from lib.imagerw import READ_EXTENSIONS


try:
    import natsort as ns

    __keygenPath = ns.natsort_keygen(alg=ns.ns.INT | ns.ns.PATH | ns.ns.GROUPLETTERS)
    __keygenFile = ns.natsort_keygen(alg=ns.ns.INT)

    def folderSortKey(path: str) -> tuple:
        return __keygenPath(path), path

    def fileSortKey(filename: str) -> tuple:
        filename, ext = os.path.splitext(filename)
        ext = ext.lstrip(".")

        # Also return the unmodified filename as fallback for consistent sorting on presumably rare occasions
        # when filenames have different case but are otherwise exactly the same (Linux: Image before image),
        # and filenames with 0-prefixed numbers (01 before 1).
        return __keygenFile(filename.casefold()), ext.casefold(), filename, ext


    # __sortNameTrans = str.maketrans("-_.,", "    ")

    # def fileSortKey(filename: str) -> tuple:
    #     filename, ext = os.path.splitext(filename)
    #     ext = ext.lstrip(".")

    #     # Treat some delimeter chars as space and split filename by words.
    #     split = filename.translate(__sortNameTrans).casefold().split(" ")

    #     nameParts = tuple(
    #         (part,) if part.isalpha() else __keygenFile(part)
    #         for part in filter(None, split)
    #     )

    #     # Also return the unmodified filename as fallback for consistent sorting on presumably rare occasions
    #     # when filenames have different case but are otherwise exactly the same (Linux: Image before image),
    #     # and filenames with 0-prefixed numbers (01 before 1).
    #     return nameParts, ext.casefold(), filename, ext


except ImportError:
    print()
    print("natsort not installed. Files and folders might appear in wrong order.")
    print("Run the setup script to install the missing natsort package.")
    print()

    def folderSortKey(path: str) -> tuple:
        return (path,)

    def fileSortKey(filename: str) -> tuple:
        filename, ext = os.path.splitext(filename)
        ext = ext.lstrip(".")
        return filename.casefold(), ext.casefold(), filename, ext


def sortKey(path: str) -> tuple:
    path, filename = os.path.split(path)
    return folderSortKey(path), fileSortKey(filename)


class CachedPathSort:
    def __init__(self):
        self._folderKeys = dict[str, tuple]()

    def __call__(self, path: str) -> tuple:
        path, filename = os.path.split(path)
        folderKey = self._folderKeys.get(path)
        if folderKey is None:
            self._folderKeys[path] = folderKey = folderSortKey(path)
        return folderKey, fileSortKey(filename)



class DataKeys:
    ImageSize               = "img_size"                # tuple[w, h]

    Caption                 = "caption"                 # str
    CaptionState            = "caption_state"           # IconStates
    CropState               = "crop_state"              # IconStates
    Thumbnail               = "thumbnail"               # QPixmap
    ThumbnailRequestTime    = "thumbnail_time"          # int (ns)

    MaskLayers              = "mask_layers"             # list[MaskItem]
    MaskIndex               = "mask_selected_index"     # int
    MaskState               = "mask_state"              # IconStates

    Embedding               = "embedding"               # numpy vector (1xN)


    class IconStates(enum.Enum):
        Exists  = "exists"
        Changed = "changed"
        Saved   = "saved"



def fileFilter(path: str) -> bool:
    name, ext = os.path.splitext(path)
    if name.endswith(Config.maskSuffix):
        return False
    return ext.lower() in READ_EXTENSIONS


def getCommonRoot(files: list[str]) -> str:
    try:
        commonRoot = os.path.commonpath(files).rstrip("/\\")
        if os.path.isfile(commonRoot):
            commonRoot = os.path.dirname(commonRoot)
        return commonRoot
    except ValueError:
        return ""

def removeCommonRoot(path: str, commonRoot: str, allowEmpty=False) -> str:
    if not (commonRoot and path.startswith(commonRoot)):
        return path

    if (path := path[len(commonRoot):]) or allowEmpty:
        return path.lstrip("/\\")
    return "."


def indexCycle(start: int, length: int, direction: int = 1) -> Iterable[int]:
    if direction > 0:
        yield from range(start+1, length)
        yield from range(0, start)
    else:
        yield from range(start-1, -1, -1)
        yield from range(length-1, start, -1)



class FileSelection:
    def __init__(self):
        super().__init__()
        self.files: set[str] = set()
        self._sortedFiles: list[str] | None = None

    @property
    def sorted(self) -> list[str]:
        if self._sortedFiles is None:
            self._sortedFiles = sorted(self.files, key=CachedPathSort())
        return self._sortedFiles

    def add(self, element: str):
        self.files.add(element)
        if self._sortedFiles is not None:
            index = bisect_left(self._sortedFiles, sortKey(element), key=sortKey)
            self._sortedFiles.insert(index, element)

    def update(self, *s: Iterable[str]):
        self.files.update(*s)
        self._sortedFiles = None

    def difference_update(self, *s: Iterable[str]):
        self.files.difference_update(*s)
        if self._sortedFiles is not None:
            self._sortedFiles = [file for file in self._sortedFiles if file in self.files]

    def discard(self, element: str):
        try:
            self.remove(element)
        except (KeyError, ValueError):
            pass

    def remove(self, element: str):
        self.files.remove(element)
        if self._sortedFiles:
            self._sortedFiles.remove(element)

    def clear(self):
        self.files.clear()
        self._sortedFiles = None

    def __len__(self) -> int:
        return self.files.__len__()

    def __contains__(self, o: object) -> bool:
        return self.files.__contains__(o)

    def __iter__(self) -> Iterator[str]:
        return self.files.__iter__()



class FileOrder:
    def __init__(self, filelist: 'FileList', mapFilePos: list[int], mapPosFile: list[int], folders: bool):
        self.filelist = filelist
        self.folders = folders
        self.mapFilePos = mapFilePos
        self.mapPosFile = mapPosFile

    def __getitem__(self, index: int) -> int:
        return self.mapFilePos[index]

    def unmap(self, index: int) -> int:
        return self.mapPosFile[index]

    def unmapIter(self, indices: Iterable[int]) -> Iterable[int]:
        return (self.mapPosFile[i] for i in indices)

    def nextSelected(self, currentIndex: int, direction: int = 1) -> int:
        files = self.filelist.files
        selection = self.filelist.selection.files
        currentIndex = self.mapFilePos[currentIndex]

        for i in indexCycle(currentIndex, len(files), direction):
            index = self.mapPosFile[i]
            if files[index] in selection:
                return index
        return currentIndex

    def removeIndices(self, sortedIndices: list[int], prevMappedIndex: int) -> int:
        sortedMappedIndices = sorted(self.mapFilePos[i] for i in sortedIndices)

        for index in reversed(sortedIndices):
            del self.mapFilePos[index]

        for mappedIndex in reversed(sortedMappedIndices):
            del self.mapPosFile[mappedIndex]

        # Adjust indices which are larger than any deleted index by subtracting the count of deleted indices which are smaller.
        # If the deleted indices are [0, 5, 14] for example:
        #     Subtract 1 from all elements larger than 0
        #     Subtract 2 from all elements larger than 5
        #     Subtract 3 from all elements larger than 14
        # 14 is smaller than e.g. 25, there are 3 deleted indices below 25, therefore shift 25 by -3
        # Complexity: O(n * log(i))
        for i, ele in enumerate(self.mapFilePos):
            shift = bisect_right(sortedMappedIndices, ele)
            self.mapFilePos[i] = ele - shift

        for i, ele in enumerate(self.mapPosFile):
            shift = bisect_right(sortedIndices, ele)
            self.mapPosFile[i] = ele - shift

        prevMappedIndex -= bisect_right(sortedMappedIndices, prevMappedIndex)
        return prevMappedIndex



class FileList:
    def __init__(self):
        self.files: list[str] = []
        self.selection: FileSelection = FileSelection()  # Min 2 selected files, always includes current file
        self.fileData: dict[str, dict[str, Any]] = dict()
        self.order: FileOrder | None = None

        self.currentFile: str = ""
        self.currentIndex: int = -1  # Index < 0 means: File set, but folder not yet scanned
        self.commonRoot: str = ""

        self.listeners: list = []
        self.selectionListeners: list = []
        self.dataListeners: list = []

        self._loadReceiver: FileListLoadReceiver | None = None


    @property
    def selectedFiles(self) -> set[str]:
        return self.selection.files


    def reset(self, clearListeners=True):
        self.files = list()
        self.selection = FileSelection()
        self.fileData = dict()
        self.order = None

        self.currentFile = ""
        self.currentIndex = -1
        self.commonRoot = ""

        if clearListeners:
            self.listeners = []
            self.selectionListeners = []
            self.dataListeners = []

        self.abortLoading()

    def abortLoading(self):
        if self._loadReceiver:
            self._loadReceiver.abortTask()
            self._loadReceiver = None

    def isLoading(self) -> bool:
        return self._loadReceiver is not None


    def load(self, path: str):
        self.loadAll((path,))

    def loadAll(self, paths: Iterable[str]):
        notify = bool(self.files)
        self.reset(clearListeners=False)

        if notify:
            self.notifySelectionChanged()
            self.notifyListChanged()

        self._loadReceiver = FileListLoadReceiver(self)
        self._loadReceiver.startTask(list(paths))

    def loadAppend(self, paths: Iterable[str]):
        self.abortLoading()

        self.order = None
        self._lazyLoadFolder()

        self._loadReceiver = FileListLoadReceiver(self)
        self._loadReceiver.startTask(list(paths))


    def _applyLoadedFiles(self, files: list[str], commonRoot: str, finished: bool):
        self.files = files
        self.commonRoot = commonRoot
        self.order = None

        if len(files) > 0:
            if self.currentIndex < 0:
                self.currentFile = files[0]
                self.currentIndex = 0
            else:
                try:
                    self.currentIndex = self.indexOf(self.currentFile)
                except ValueError:
                    print(f"Warning: File {self.currentFile} not in FileList")
                    self.currentIndex = -1
        else:
            self.currentFile = ""
            self.currentIndex = -1

        if finished:
            self._loadReceiver.deleteLater()
            self._loadReceiver = None

            # Enable lazy loading if there's only one file
            if len(files) <= 1:
                self.currentIndex = -1

            self.notifySelectionChanged()

        # TODO: Different notification for append (don't scroll to selection in Gallery)
        self.notifyListChanged()


    def loadFilesFixed(self, paths: Iterable[str], copyFromFileList=None, copyKeys: list[str]=[DataKeys.ImageSize, DataKeys.Thumbnail]):
        self.reset(clearListeners=False)

        if copyFromFileList and copyKeys:
            def copyData(file: str):
                if data := {key: val for key in copyKeys if (val := copyFromFileList.getData(file, key))}:
                    self.fileData[file] = data
        else:
            def copyData(file: str):
                pass

        for path in paths:
            path = os.path.abspath(path)
            if os.path.isfile(path) and fileFilter(path):
                self.files.append(path)
                copyData(path)

        self._postprocessList()
        numFiles = len(self.files)
        self.currentFile = self.files[0] if numFiles > 0 else ""
        self.currentIndex = 0 if numFiles > 0 else -1 # No lazy-loading of folder when loading a single image!
        self.notifySelectionChanged()
        self.notifyListChanged()


    def filterFiles(self, predKeep: Callable[[str], bool]):
        self.abortLoading()

        currentFile = self.currentFile
        currentMappedIndex = self.order[self.currentIndex] if self.order and self.currentIndex >= 0 else -1

        self.currentIndex = -1
        self.currentFile = ""
        numSelected = len(self.selection)

        removedIndices = list[int]()
        prevMappedIndex = -1

        newFiles = list[str]()
        for i, file in enumerate(self.files):
            # Keep file
            if predKeep(file):
                newFiles.append(file)
                if file == currentFile:
                    self.currentIndex = len(newFiles) - 1
                    self.currentFile  = file

                    # When the file ist kept, there is no need for prevMappedIndex
                    currentMappedIndex = -1
                    prevMappedIndex = -1

                elif self.order:
                    mappedIndex = self.order[i]
                    if mappedIndex < currentMappedIndex and mappedIndex > prevMappedIndex:
                        prevMappedIndex = mappedIndex

            # Remove file
            else:
                self.fileData.pop(file, None)
                self.selection.discard(file)
                if file == currentFile:
                    self.currentIndex = len(newFiles) - 1

                if self.order:
                    removedIndices.append(i)

        if len(newFiles) < 2:
            self.order = None
        elif self.order:
            prevMappedIndex = self.order.removeIndices(removedIndices, prevMappedIndex)
            if not self.currentFile:
                self.currentIndex = self.order.unmap(max(prevMappedIndex, 0))

        if not self.currentFile:
            if self.currentIndex >= 0:
                self.currentFile = newFiles[self.currentIndex]
            elif newFiles:
                self.currentIndex = 0
                self.currentFile  = newFiles[0]

        self.files = newFiles
        self.commonRoot = getCommonRoot(self.files)

        if len(self.selection) != numSelected:
            self._validateSelection()
            self.notifySelectionChanged()

        self.notifyListChanged()


    def getNumFiles(self) -> int:
        self._lazyLoadFolder()
        return len(self.files)

    def getFiles(self) -> list[str]:
        self._lazyLoadFolder()
        return self.files

    def isLastFile(self) -> bool:
        self._lazyLoadFolder()
        if self.selection:
            return self.selection.sorted[-1] == self.currentFile

        currentIndex = self.order[self.currentIndex] if self.order else self.currentIndex
        return currentIndex == len(self.files) - 1  # True when no files loaded

    def getCurrentNr(self) -> int:
        if self.order and self.currentIndex >= 0:
            return self.order[self.currentIndex]
        return self.currentIndex

    def getCurrentFile(self) -> str:
        return self.currentFile

    def setCurrentFile(self, file: str):
        try:
            index = self.indexOf(file)
        except ValueError:
            print(f"Warning: File {file} not in FileList")
            index = -1

        self.currentFile = file
        self.currentIndex = index
        self.notifyFileChanged()

    def setCurrentIndex(self, index: int):
        if index < 0 or index >= len(self.files):
            print(f"Warning: Index {index} out of bounds of FileList")
            return

        self.currentFile = self.files[index]
        self.currentIndex = index
        self.notifyFileChanged()

    def indexOf(self, file: str) -> int:
        index = bisect_left(self.files, sortKey(file), key=sortKey)
        if index < len(self.files) and self.files[index] == file:
            return index
        raise ValueError("File not in FileList")


    def setNextFile(self):
        self._lazyLoadFolder()
        if self.selection:
            self._changeSelectedFile(1)
        else:
            self._changeFile(1)

    def setPrevFile(self):
        self._lazyLoadFolder()
        if self.selection:
            self._changeSelectedFile(-1)
        else:
            self._changeFile(-1)

    def _changeFile(self, indexOffset: int):
        if numFiles := len(self.files):
            if self.order:
                index = (self.order[self.currentIndex] + indexOffset) % numFiles
                self.currentIndex = self.order.unmap(index)
            else:
                self.currentIndex = (self.currentIndex + indexOffset) % numFiles

            self.currentFile = self.files[self.currentIndex]
            self.notifyFileChanged()

    def _changeSelectedFile(self, indexOffset: int):
        try:
            if self.order:
                self.currentIndex = self.order.nextSelected(self.currentIndex, indexOffset)
            else:
                sortedSelection = self.selection.sorted
                index = bisect_left(sortedSelection, sortKey(self.currentFile), key=sortKey)
                if index >= len(sortedSelection) or sortedSelection[index] != self.currentFile:
                    raise ValueError("Current file not in selected files")
                index = (index + indexOffset) % len(sortedSelection)
                self.currentIndex = self.indexOf(sortedSelection[index]) # raises when not found

            self.currentFile = self.files[self.currentIndex]
            self.notifyFileChanged()
        except ValueError as ex:
            print(f"Warning: {ex}")


    def setNextFolder(self):
        self._lazyLoadFolder()
        currentIndex = max(self.currentIndex, 0)

        if self.order:
            indices = self.order.unmapIter(indexCycle(self.order[currentIndex], len(self.files)))
        else:
            indices = indexCycle(currentIndex, len(self.files))
        self._switchFolder(indices)

    def setPrevFolder(self):
        self._lazyLoadFolder()
        if self.order:
            indices = self.order.unmapIter(indexCycle(self.order[self.currentIndex], len(self.files), -1))
        else:
            indices = indexCycle(self.currentIndex, len(self.files), -1)
        self._switchFolder(indices)

    def _switchFolder(self, indices: Iterable[int]):
        currentFolder = os.path.dirname(self.currentFile)
        for i in indices:
            folder = os.path.dirname(self.files[i])
            if folder != currentFolder:
                self.currentIndex = i
                self.currentFile = self.files[self.currentIndex]
                self.notifyFileChanged()
                return


    def _lazyLoadFolder(self):
        # Lazy loading of the folder needs to be synchronous and finish before further processing.
        if self.currentIndex < 0 and self.currentFile and self._loadReceiver is None:
            assert len(self.files) == 1

            path = os.path.abspath(os.path.dirname(self.currentFile))
            with os.scandir(path) as it:
                for entry in filter(os.DirEntry.is_file, it):
                    file = entry.path
                    if fileFilter(file) and file != self.currentFile:
                        self.files.append(file)

            self._postprocessList()

            try:
                self.currentIndex = self.indexOf(self.currentFile)
            except ValueError:
                print(f"Warning: File {self.currentFile} not in FileList")
                self.currentIndex = -1

            numAddedFiles = len(self.files) - 1
            if numAddedFiles > 0:
                filesStr = "file" if numAddedFiles == 1 else "files"
                print(f"Added {numAddedFiles} {filesStr} (lazy load)")


    def _postprocessList(self):
        self.files.sort(key=CachedPathSort())
        self.commonRoot = getCommonRoot(self.files)

    def removeCommonRoot(self, path: str, allowEmpty=False) -> str:
        return removeCommonRoot(path, self.commonRoot, allowEmpty)


    def addListener(self, listener):
        self.listeners.append(listener)

    def removeListener(self, listener):
        self.listeners.remove(listener)

    def notifyFileChanged(self):
        if not self._validateSelection():
            self.notifySelectionChanged()

        for l in self.listeners:
            l.onFileChanged(self.currentFile)

    def notifyListChanged(self):
        for l in self.listeners:
            l.onFileListChanged(self.currentFile)


    def _validateSelection(self) -> bool:
        if self.selection and (len(self.selection) < 2 or self.currentFile not in self.selection):
            self.selection.clear()
            return False
        return True

    def isSelected(self, file: str) -> bool:
        return file in self.selection

    def selectFile(self, file: str):
        numSelected = len(self.selection)
        if numSelected == 0:
            if file == self.currentFile:
                return
            self.selection.add(self.currentFile)

        self.selection.add(file)
        if len(self.selection) != numSelected:
            self.notifySelectionChanged()

    def setSelection(self, files: Iterable[str], updateCurrent=False, clearCurrentSelection=True):
        if clearCurrentSelection:
            self.selection.clear()

        self.selection.update(files)

        if updateCurrent:
            if self.selection and (self.currentFile not in self.selection):
                self.setCurrentFile(self.selection.sorted[0])
        else:
            self.selection.add(self.currentFile)

        if len(self.selection) < 2:
            self.selection.clear()
        self.notifySelectionChanged()

    def _getFileRange(self, fileEnd: str) -> Iterable[str] | None:
        'Returns files from `currentFile` to `fileEnd`, including both.'

        try:
            indexEnd = self.indexOf(fileEnd)
        except ValueError:
            print(f"Warning: File {fileEnd} not in FileList")
            return None

        indexStart = self.currentIndex
        if indexEnd == indexStart:
            return None

        if self.order:
            indexStart, indexEnd = sorted((self.order[indexStart], self.order[indexEnd]))
            return (self.files[i] for i in self.order.unmapIter(range(indexStart, indexEnd+1)))
        else:
            indexStart, indexEnd = sorted((indexStart, indexEnd))
            return (self.files[i] for i in range(indexStart, indexEnd+1))

    def selectFileRange(self, fileEnd: str):
        if rangeFiles := self._getFileRange(fileEnd):
            self.selection.update(rangeFiles)
            self.notifySelectionChanged()

    def unselectFileRange(self, fileEnd: str):
        if rangeFiles := self._getFileRange(fileEnd):
            self.selection.difference_update(rangeFiles)
            if self.selection:
                self.selection.add(self.currentFile)
            self.notifySelectionChanged()

    def unselectFile(self, file: str):
        if file == self.currentFile:
            print("Warning: Cannot remove current file from selection")
            return

        try:
            self.selection.remove(file)
            if len(self.selection) < 2:
                self.selection.clear()
            self.notifySelectionChanged()
        except KeyError:
            pass

    def clearSelection(self):
        if self.selection:
            self.selection.clear()
            self.notifySelectionChanged()


    def setOrder(self, mapFilePos: list[int], mapPosFile: list[int], folders: bool = True):
        self.order = FileOrder(self, mapFilePos, mapPosFile, folders)

    def getOrderedFiles(self) -> Iterable[str]:
        files = self.getFiles()
        return (files[i] for i in self.order.mapPosFile) if self.order else files

    def clearOrder(self):
        self.order = None

    def isOrderWithFolders(self) -> bool:
        return self.order.folders if self.order else True


    def addSelectionListener(self, listener):
        self.selectionListeners.append(listener)

    def removeSelectionListener(self, listener):
        self.selectionListeners.remove(listener)

    def notifySelectionChanged(self):
        selectedFiles = self.selectedFiles
        for l in self.selectionListeners:
            l.onFileSelectionChanged(selectedFiles)


    def setData(self, file: str, key: str, data: Any, notify=True) -> None:
        fileDict = self.fileData.get(file)
        if fileDict is None:
            fileDict = dict()
            self.fileData[file] = fileDict
        fileDict[key] = data

        if notify:
            self.notifyDataChanged(file, key)

    def getData(self, file: str, key: str) -> Any | None:
        fileDict = self.fileData.get(file)
        if fileDict is None:
            return None
        return fileDict.get(key)

    def getMultipleData(self, file: str, keys: Iterable[str]) -> dict:
        if fileDict := self.fileData.get(file):
            return {k: v for k in keys if (v := fileDict.get(k)) is not None}
        return {}

    def removeData(self, file: str, key: str, notify=True) -> None:
        fileDict = self.fileData.get(file)
        if fileDict is None:
            return

        try:
            del fileDict[key]
        except KeyError:
            return

        if notify:
            self.notifyDataChanged(file, key)


    def addDataListener(self, listener):
        self.dataListeners.append(listener)

    def removeDataListener(self, listener):
        self.dataListeners.remove(listener)

    def notifyDataChanged(self, file: str, key: str):
        for l in self.dataListeners:
            l.onFileDataChanged(file, key)



class FileListLoadReceiver(QObject):
    apply = Signal(tuple, str, bool)  # wrapped files, common root, finished

    def __init__(self, filelist: FileList):
        super().__init__(parent=None)
        self.filelist = filelist
        self.apply.connect(self._onApply, Qt.ConnectionType.QueuedConnection)

        self.task: FileListLoadTask | None = None

    @Slot(list, str, bool)
    def _onApply(self, wrappedFiles: tuple[list[str]], commonRoot: str, finished: bool):
        if self.filelist is None:
            return

        self.filelist._applyLoadedFiles(wrappedFiles[0], commonRoot, finished)

        if finished:
            self.filelist = None
        elif self.task:
            # Only allow more notifications after the current one is completely processed
            # to prevent overwhelming the GUI thread.
            self.task.allowNextNotify()

    def startTask(self, paths: list[str]):
        self.task = FileListLoadTask(self, paths)
        QThreadPool.globalInstance().start(self.task)

    def abortTask(self):
        self.apply.disconnect()
        self.filelist = None

        if self.task:
            self.task.abort()


class Folder:
    __slots__ = ('path', 'sortKey', 'fileEntries', 'existingFiles', 'missingKeys')

    def __init__(self, path: str, missingKeys=False):
        self.path: str = path
        self.sortKey: Any = folderSortKey(path)
        self.fileEntries: list[tuple[str, Any]] = []
        self.existingFiles: set[str] = set()
        self.missingKeys: bool = missingKeys

    def key(self):
        return self.sortKey

    @property
    def files(self) -> Iterable[str]:
        return (entry[0] for entry in self.fileEntries)


class FileListLoadTask(QRunnable):
    NOTIFY_INTERVAL_FIRST =   300_000_000  # 300 ms
    NOTIFY_INTERVAL       = 2_000_000_000  # 2 seconds

    def __init__(self, receiver: FileListLoadReceiver, paths: list[str]):
        super().__init__()
        self.setAutoDelete(True)
        self.startTime = time.monotonic_ns()

        self.receiver = receiver
        self.paths = paths

        self.numInitialFiles = 0
        self.numAddedFiles = 0

        self.folders: dict[str, Folder] = {}
        self._initFolders(receiver.filelist.files)

        self._mutex = QMutex()
        self._aborted = False
        self._nextNotifyTime = time.monotonic_ns() + self.NOTIFY_INTERVAL_FIRST


    def allowNextNotify(self):
        now = time.monotonic_ns()
        with QMutexLocker(self._mutex):
            self._nextNotifyTime = now + self.NOTIFY_INTERVAL

    def abort(self):
        with QMutexLocker(self._mutex):
            self._aborted = True

    def isAborted(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._aborted


    def _initFolders(self, files: list[str]):
        currentDir = None
        currentFolder: Folder = None

        for file in files:
            dirname, basename = os.path.split(file)
            if dirname != currentDir:
                currentDir = dirname
                currentFolder = Folder(dirname, missingKeys=True)
                self.folders[dirname] = currentFolder

            currentFolder.fileEntries.append((file, basename))

        self.numInitialFiles = len(files)

    def _getFolder(self, path: str):
        if folder := self.folders.get(path):
            # When an existing folder is retrieved to add more files,
            # lazily create keys and populate set with existing files.
            if folder.missingKeys:
                folder.missingKeys = False
                folder.fileEntries = [(file, fileSortKey(basename)) for file, basename in folder.fileEntries]

            folder.existingFiles.update(folder.files)
        else:
            self.folders[path] = folder = Folder(path)
        return folder


    @Slot()
    def run(self):
        fileEntryKey = lambda entry: entry[1]

        try:
            for path in self.paths:
                path = os.path.abspath(path)

                # Walk folders
                if os.path.isdir(path):
                    for (root, dirs, files) in os.walk(path, topdown=True, followlinks=True):
                        if self.isAborted():
                            return

                        root = os.path.normpath(root)
                        folder = self._getFolder(root)
                        numFolderFiles = len(folder.fileEntries)

                        folder.fileEntries.extend(
                            (filePath, fileSortKey(f))
                            for f in files
                            if fileFilter(f) and (filePath := os.path.join(root, f)) not in folder.existingFiles
                        )

                        folder.fileEntries.sort(key=fileEntryKey)
                        self._notifyFilesAdded(len(folder.fileEntries) - numFolderFiles)

                # Single file paths
                elif fileFilter(path):
                    dirname, basename = os.path.split(path)
                    folder = self._getFolder(dirname)

                    if path not in folder.existingFiles:
                        key = fileSortKey(basename)
                        index = bisect_right(folder.fileEntries, key, key=fileEntryKey)
                        folder.fileEntries.insert(index, (path, key))
                        self._notifyFilesAdded(1)

        finally:
            if not self.isAborted():
                t = (time.monotonic_ns() - self.startTime) / 1_000_000
                msg = " ".join((
                    "Added" if self.numInitialFiles else "Loaded",
                    str(self.numAddedFiles),
                    "file" if self.numAddedFiles == 1 else "files",
                    f"in {t:.2f} ms"
                ))

                print(msg)
                self.apply(finished=True)


    def _notifyFilesAdded(self, numAddedFiles: int):
        self.numAddedFiles += numAddedFiles

        with QMutexLocker(self._mutex):
            if self._nextNotifyTime < 0 or time.monotonic_ns() < self._nextNotifyTime:
                return
            self._nextNotifyTime = -1

        self.apply()

    def apply(self, finished: bool = False):
        folders = sorted(self.folders.values(), key=Folder.key)

        files = list[str]()
        for folder in folders:
            files.extend(folder.files)

        commonRoot = getCommonRoot(files)
        self.receiver.apply.emit((files,), commonRoot, finished)  # Wrap list in tuple to prevent copy
