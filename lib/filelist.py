from typing import Iterable, Any, Callable
import os, enum
from bisect import bisect_left
from PySide6.QtGui import QImageReader
from config import Config


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


# Only images with these extensions are loaded into the FileList:
VALID_EXTENSION = set([ f".{format.data().decode('utf-8').lower()}" for format in QImageReader.supportedImageFormats() ])

def fileFilter(path) -> bool:
    name, ext = os.path.splitext(path)
    if name.endswith(Config.maskSuffix):
        return False
    return ext.lower() in VALID_EXTENSION


class FileList:
    def __init__(self):
        self.files: list[str] = []
        self.fileData: dict[str, dict[str, Any]] = dict()
        self.currentFile = ""
        self.currentIndex = -1  # Index < 0 means: File set, but folder not yet scanned
        self.commonRoot = ""

        self.listeners = []
        self.dataListeners = []


    def loadAll(self, paths: Iterable[str]):
        self.files.clear()
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
        self.notifyListChanged()


    def loadFilesFixed(self, paths: Iterable[str], copyFromFileList=None, copyKeys: list[str]=[DataKeys.ImageSize, DataKeys.Thumbnail]):
        self.files.clear()
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
        self.notifyListChanged()


    def loadAppend(self, paths: Iterable[str]):
        for path in paths:
            if os.path.isdir(path):
                self._walkPath(path, True)
            elif fileFilter(path):
                self.files.append(os.path.abspath(path))

        self._postprocessList(removeDuplicates=True)
        self.notifyListChanged()

    def load(self, path: str):
        if os.path.isdir(path):
            self.loadFolder(path, True)
        else:
            self.loadFile(path)

    def loadFile(self, file: str):
        self.files = []
        self.fileData = dict()
        self.currentFile = os.path.abspath(file)
        self.currentIndex = -1
        self.commonRoot = ""
        self.notifyListChanged()

    def loadFolder(self, path: str, subfolders=False):
        self.files = []
        self.fileData = dict()
        self._walkPath(path, subfolders)
        self._postprocessList()
        self.currentFile = self.files[0] if len(self.files) > 0 else ""
        self.currentIndex = 0
        self.notifyListChanged()


    def filterFiles(self, predKeep: Callable[[str], bool]):
        currentFile = self.currentFile
        self.currentIndex = -1
        self.currentFile = ""

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
        self.notifyListChanged()


    def getNumFiles(self):
        self._lazyLoadFolder()
        return len(self.files)

    def getFiles(self):
        self._lazyLoadFolder()
        return self.files

    def isLastFile(self) -> bool:
        self._lazyLoadFolder()
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
        if self.files[index] == file:
            return index
        raise ValueError("File not in FileList")


    def setNextFile(self):
        self._lazyLoadFolder()
        if numFiles := len(self.files):
            self.currentIndex = (self.currentIndex+1) % numFiles
            self.currentFile = self.files[self.currentIndex]
            self.notifyFileChanged()

    def setPrevFile(self):
        self._lazyLoadFolder()
        if numFiles := len(self.files):
            self.currentIndex = (self.currentIndex-1) % numFiles
            self.currentFile = self.files[self.currentIndex]
            self.notifyFileChanged()


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
        if not (self.commonRoot and path.startswith(self.commonRoot)):
            return path

        if (path := path[len(self.commonRoot):]) or allowEmpty:
            return path.lstrip("/\\")
        return "."


    def addListener(self, listener):
        self.listeners.append(listener)

    def removeListener(self, listener):
        self.listeners.remove(listener)

    def notifyFileChanged(self):
        for l in self.listeners:
            l.onFileChanged(self.currentFile)

    def notifyListChanged(self):
        for l in self.listeners:
            l.onFileListChanged(self.currentFile)


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
