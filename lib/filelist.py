import os, enum
from PySide6.QtGui import QImageReader
from config import Config


try:
    import natsort as ns
    sortKey = ns.natsort_keygen(alg=ns.INT | ns.PATH | ns.IGNORECASE)
except:
    print("natsort not installed. Numbered files might appear in wrong order.")
    print("Run the setup script to install the missing natsort package.")
    def sortKey(path: str):
        return os.path.split(path)


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



VALID_EXTENSION = set([ f".{format.data().decode('utf-8').lower()}" for format in QImageReader.supportedImageFormats() ])

def fileFilter(path) -> bool:
    name, ext = os.path.splitext(path)
    if name.endswith(Config.maskSuffix):
        return False
    return ext.lower() in VALID_EXTENSION


class FileList:
    def __init__(self):
        self.files: list[str] = []
        self.fileData = dict()
        self.currentFile = ""
        self.currentIndex = -1  # Index < 0 means: File set, but folder not yet scanned

        self.listeners = []
        self.dataListeners = []


    def loadAll(self, paths):
        self.files.clear()
        self.fileData.clear()
        for path in paths:
            if os.path.isdir(path):
                self._walkPath(path, True)
            elif fileFilter(path):
                self.files.append(path)

        self._sortFiles()
        numFiles = len(self.files)
        self.currentFile = self.files[0] if numFiles > 0 else ""
        self.currentIndex = 0 if numFiles > 1 else -1
        self.notifyListChanged()

    def loadAppend(self, paths):
        for path in paths:
            if os.path.isdir(path):
                self._walkPath(path, True)
            elif fileFilter(path):
                self.files.append(path)

        self._removeDuplicates()
        self._sortFiles()
        self.notifyListChanged()

    def load(self, path):
        if os.path.isdir(path):
            self.loadFolder(path, True)
        else:
            self.loadFile(path)

    def loadFile(self, file):
        self.files = []
        self.fileData = dict()
        self.currentFile = file
        self.currentIndex = -1
        self.notifyListChanged()

    def loadFolder(self, path, subfolders=False):
        self.files = []
        self.fileData = dict()
        self._walkPath(path, subfolders)
        self._sortFiles()
        self.currentFile = self.files[0] if len(self.files) > 0 else ""
        self.currentIndex = 0
        self.notifyListChanged()


    def getNumFiles(self):
        return len(self.files)

    def getFiles(self):
        self._lazyLoadFolder()
        return self.files

    def getCurrentFile(self):
        return self.currentFile

    def setCurrentFile(self, file):
        try:
            index = self.files.index(file)
        except ValueError:
            print(f"Warning: File {file} not in FileList")
            index = -1

        self.currentFile = file
        self.currentIndex = index
        self.notifyFileChanged()

    def setCurrentIndex(self, index):
        if index < 0 or index >= len(self.files):
            print(f"Warning: Index {index} out of bounds of FileList")
            return
        
        self.currentFile = self.files[index]
        self.currentIndex = index
        self.notifyFileChanged()

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

    def _switchFolderProcessFile(self, index, currentFolder) -> bool:
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
            self._removeDuplicates()
            self._sortFiles()

            try:
                self.currentIndex = self.files.index(self.currentFile)
            except ValueError:
                print(f"Warning: File {self.currentFile} not in FileList")
                self.currentIndex = -1

    def _walkPath(self, path, subfolders=False):
        for (root, dirs, files) in os.walk(path, topdown=True, followlinks=True):
            if not subfolders:
                dirs[:] = []
            # os.path.join() mixes up the separators on Windows.
            self.files += [f"{root}/{f}" for f in files if fileFilter(f)]

    def _removeDuplicates(self):
        self.files = list(set(self.files))

    def _sortFiles(self):
        self.files.sort(key=sortKey)


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


    def setData(self, file, key, data, notify=True):
        if file not in self.fileData:
            self.fileData[file] = {}
        self.fileData[file][key] = data

        if notify:
            self.notifyDataChanged(file, key)

    def getData(self, file, key):
        if file not in self.fileData:
            return None
        d = self.fileData[file]
        return d[key] if key in d else None

    def removeData(self, file, key, notify=True):
        if file not in self.fileData:
            return
        d = self.fileData[file]
        if key not in d:
            return

        del d[key]
        if notify:
            self.notifyDataChanged(file, key)


    def addDataListener(self, listener):
        self.dataListeners.append(listener)

    def removeDataListener(self, listener):
        self.dataListeners.remove(listener)

    def notifyDataChanged(self, file, key):
        for l in self.dataListeners:
            l.onFileDataChanged(file, key)
