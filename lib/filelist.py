from typing import Iterable, Iterator, Any, Callable
import os, enum
from bisect import bisect_left
from config import Config
from lib.imagerw import READ_EXTENSIONS


def sortKey(path: str):
    path, filename = os.path.split(path)
    return path, filename.lower()

try:
    import natsort as ns
    sortKey = ns.natsort_keygen(key=sortKey, alg=ns.ns.INT | ns.ns.PATH | ns.ns.GROUPLETTERS)
except:
    print("natsort not installed. Numbered files might appear in wrong order.")
    print("Run the setup script to install the missing natsort package.")


class DataKeys:
    ImageSize       = "img_size"            # tuple[w, h]

    Caption         = "caption"             # str
    CaptionState    = "caption_state"       # IconStates
    CropState       = "crop_state"          # IconStates
    Thumbnail       = "thumbnail"           # QPixmap
    ThumbnailRequestTime = "thumbnail_time" # int (ns)

    MaskLayers      = "mask_layers"         # list[MaskItem]
    MaskIndex       = "mask_selected_index" # int
    MaskState       = "mask_state"          # IconStates

    class IconStates(enum.Enum):
        Exists  = "exists"
        Changed = "changed"
        Saved   = "saved"



def fileFilter(path) -> bool:
    name, ext = os.path.splitext(path)
    if name.endswith(Config.maskSuffix):
        return False
    return ext.lower() in READ_EXTENSIONS


def removeCommonRoot(path: str, commonRoot: str, allowEmpty=False) -> str:
    if not (commonRoot and path.startswith(commonRoot)):
        return path

    if (path := path[len(commonRoot):]) or allowEmpty:
        return path.lstrip("/\\")
    return "."



class FileSelection:
    def __init__(self):
        super().__init__()
        self.files: set[str] = set()
        self._sortedFiles: list[str] | None = None

    @property
    def sorted(self):
        if self._sortedFiles is None:
            self._sortedFiles = sorted(self.files, key=sortKey)
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



class FileList:
    def __init__(self):
        self.files: list[str] = []
        self.selection: FileSelection = FileSelection()  # Min 2 selected files, always includes current file
        self.fileData: dict[str, dict[str, Any]] = dict()
        self.currentFile: str = ""
        self.currentIndex: int = -1  # Index < 0 means: File set, but folder not yet scanned
        self.commonRoot: str = ""

        self.listeners: list = []
        self.selectionListeners: list = []
        self.dataListeners: list = []


    @property
    def selectedFiles(self) -> set[str]:
        return self.selection.files


    def reset(self):
        self.files = list()
        self.selection = FileSelection()
        self.fileData = dict()
        self.currentFile = ""
        self.currentIndex = -1
        self.commonRoot = ""
        self.listeners.clear()
        self.selectionListeners.clear()
        self.dataListeners.clear()


    def load(self, path: str):
        self.loadAll((path,))

    def loadAll(self, paths: Iterable[str]):
        self.files.clear()
        self.selection.clear()
        self.fileData.clear()
        for path in paths:
            if os.path.isdir(path):
                self._walkPath(path, True)
            elif fileFilter(path):
                self.files.append(os.path.abspath(path))

        self._postprocessList()
        numFiles = len(self.files)
        self.currentFile = self.files[0] if numFiles > 0 else ""
        self.currentIndex = 0 if numFiles > 1 else -1
        self.notifySelectionChanged()
        self.notifyListChanged()


    def loadFilesFixed(self, paths: Iterable[str], copyFromFileList=None, copyKeys: list[str]=[DataKeys.ImageSize, DataKeys.Thumbnail]):
        self.files.clear()
        self.selection.clear()
        self.fileData.clear()

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


    def loadAppend(self, paths: Iterable[str]):
        if not self.files:
            self.loadAll(paths)
            return

        self._lazyLoadFolder()
        for path in paths:
            if os.path.isdir(path):
                self._walkPath(path, True)
            elif fileFilter(path):
                self.files.append(os.path.abspath(path))

        self._postprocessList(removeDuplicates=True)

        try:
            self.currentIndex = self.indexOf(self.currentFile)
        except ValueError:
            print(f"Warning: File {self.currentFile} not in FileList")
            self.currentIndex = -1

        self.notifySelectionChanged()
        self.notifyListChanged()


    def filterFiles(self, predKeep: Callable[[str], bool]):
        currentFile = self.currentFile
        self.currentIndex = -1
        self.currentFile = ""
        numSelected = len(self.selection)

        newFiles = []
        for file in self.files:
            # Keep file
            if predKeep(file):
                newFiles.append(file)
                if file == currentFile:
                    self.currentIndex = len(newFiles) - 1
                    self.currentFile  = file

            # Remove file
            else:
                self.fileData.pop(file, None)
                self.selection.discard(file)
                if file == currentFile:
                    self.currentIndex = len(newFiles) - 1

        if not self.currentFile:
            if self.currentIndex >= 0:
                self.currentFile = newFiles[self.currentIndex]
            elif newFiles:
                self.currentIndex = 0
                self.currentFile  = newFiles[0]

        self.files = newFiles
        self._updateCommonRoot()

        if len(self.selection) != numSelected:
            self._validateSelection()
            self.notifySelectionChanged()

        self.notifyListChanged()


    def getNumFiles(self):
        self._lazyLoadFolder()
        return len(self.files)

    def getFiles(self):
        self._lazyLoadFolder()
        return self.files

    def isLastFile(self) -> bool:
        self._lazyLoadFolder()
        if self.selection:
            return self.selection.sorted[-1] == self.currentFile
        return self.currentIndex == len(self.files) - 1  # True when no files loaded

    def getCurrentFile(self):
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
            self.currentIndex = (self.currentIndex + indexOffset) % numFiles
            self.currentFile = self.files[self.currentIndex]
            self.notifyFileChanged()

    def _changeSelectedFile(self, indexOffset: int):
        try:
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
        currentFolder = os.path.dirname(self.currentFile)
        currentIndex = max(self.currentIndex, 0)

        for i in range(currentIndex, len(self.files)):
            if self._switchFolderProcessFile(i, currentFolder):
                return

        for i in range(0, currentIndex):
            if self._switchFolderProcessFile(i, currentFolder):
                return

    def setPrevFolder(self):
        self._lazyLoadFolder()
        currentFolder = os.path.dirname(self.currentFile)

        for i in range(self.currentIndex-1, -1, -1):
            if self._switchFolderProcessFile(i, currentFolder):
                return

        for i in range(len(self.files)-1, self.currentIndex, -1):
            if self._switchFolderProcessFile(i, currentFolder):
                return

    def _switchFolderProcessFile(self, index: int, currentFolder: str) -> bool:
        folder = os.path.dirname(self.files[index])
        if folder != currentFolder:
            self.currentIndex = index
            self.currentFile = self.files[self.currentIndex]
            self.notifyFileChanged()
            return True
        return False


    def _lazyLoadFolder(self):
        if self.currentIndex < 0 and self.currentFile:
            path = os.path.dirname(self.currentFile)
            self._walkPath(path, False)
            self._postprocessList(removeDuplicates=True)

            try:
                self.currentIndex = self.indexOf(self.currentFile)
            except ValueError:
                print(f"Warning: File {self.currentFile} not in FileList")
                self.currentIndex = -1

    def _walkPath(self, path: str, subfolders=False):
        path = os.path.abspath(path)
        for (root, dirs, files) in os.walk(path, topdown=True, followlinks=True):
            if not subfolders:
                dirs.clear()
            root = os.path.normpath(root)
            self.files.extend(os.path.join(root, f) for f in files if fileFilter(f))


    def _postprocessList(self, removeDuplicates=False):
        if removeDuplicates:
            self.files = sorted(set(self.files), key=sortKey)
        else:
            self.files.sort(key=sortKey)

        self._updateCommonRoot()

    def _updateCommonRoot(self):
        try:
            self.commonRoot = os.path.commonpath(self.files).rstrip("/\\")
            if os.path.isfile(self.commonRoot):
                self.commonRoot = os.path.dirname(self.commonRoot)
        except ValueError:
            self.commonRoot = ""

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

    def isSelected(self, file: str):
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

    def _getFileRange(self, fileEnd: str) -> list[str] | None:
        'Returns files from `currentFile` to `fileEnd`, including both.'

        try:
            indexEnd = self.indexOf(fileEnd)
        except ValueError:
            print(f"Warning: File {fileEnd} not in FileList")
            return None

        indexStart = self.currentIndex
        if indexEnd == indexStart:
            return None
        if indexEnd < indexStart:
            indexStart, indexEnd = indexEnd, indexStart

        return self.files[indexStart:indexEnd+1]

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
