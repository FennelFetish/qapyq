import os

VALID_EXTENSION = ['.jpg', '.jpeg', '.png', '.webp', '.bmp']


class FileList:
    def __init__(self):
        self.files = []
        self.currentFile = ""
        self.currentIndex = -1  # Index < 0 means: File set, but folder not yet scanned


    def setFile(self, file):
        self.files = []
        self.currentFile = file
        self.currentIndex = -1

    def loadFolder(self, path, subfolders=False):
        self._readFolder(path, subfolders)
        self.currentFile = self.files[0] if len(self.files) > 0 else ""
        self.currentIndex = 0


    def getCurrentFile(self):
        return self.currentFile

    def getNextFile(self):
        self._lazyLoadFolder()
        self.currentIndex = (self.currentIndex+1) % len(self.files)
        self.currentFile = self.files[self.currentIndex]
        return self.currentFile

    def getPrevFile(self):
        self._lazyLoadFolder()
        self.currentIndex = (self.currentIndex-1) % len(self.files)
        self.currentFile = self.files[self.currentIndex]
        return self.currentFile


    def getNextFolder(self):
        self._lazyLoadFolder()
        currentFolder = os.path.dirname(self.currentFile)

        for i in range(self.currentIndex, len(self.files)):
            folder = os.path.dirname(self.files[i])
            if folder != currentFolder:
                self.currentIndex = i
                self.currentFile = self.files[self.currentIndex]
                return self.currentFile
        
        for i in range(0, self.currentIndex):
            folder = os.path.dirname(self.files[i])
            if folder != currentFolder:
                self.currentIndex = i
                self.currentFile = self.files[self.currentIndex]
                return self.currentFile
        
        return self.currentFile

    def getPrevFolder(self):
        self._lazyLoadFolder()
        currentFolder = os.path.dirname(self.currentFile)

        for i in range(self.currentIndex-1, -1, -1):
            folder = os.path.dirname(self.files[i])
            if folder != currentFolder:
                self.currentIndex = i
                self.currentFile = self.files[self.currentIndex]
                return self.currentFile
        
        for i in range(len(self.files)-1, self.currentIndex, -1):
            folder = os.path.dirname(self.files[i])
            if folder != currentFolder:
                self.currentIndex = i
                self.currentFile = self.files[self.currentIndex]
                return self.currentFile

        return self.currentFile


    def _lazyLoadFolder(self):
        if self.currentIndex < 0:
            path = os.path.dirname(self.currentFile)
            self._readFolder(path, False)
            self.currentIndex = self.files.index(self.currentFile)

    def _readFolder(self, path, subfolders=False):
        self.files = []
        for (root, dirs, files) in os.walk(path, topdown=True, followlinks=True):
            if not subfolders:
                dirs[:] = []
            self.files += [os.path.join(root, f) for f in files if any(f.lower().endswith(ext) for ext in VALID_EXTENSION)]
        self.files.sort()
