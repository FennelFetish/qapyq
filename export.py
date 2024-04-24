import os



class Export:
    def __init__(self):
        self.basePath = "."
        self._extension = "png"
        self.suffix = ""

        self.skipDirs = 2
        self.subfolders = 1     # Save into nested directory structure
        self.folderNames = 0    # Include folder names in filename


    @property
    def extension(self):
        return self._extension

    @extension.setter
    def extension(self, ext):
        self._extension = ext.lower()


    def getExportPath(self, srcFile):
        filename = self.getFileName(srcFile)
        filename = os.path.join(self.basePath, filename)

        folder = os.path.dirname(filename)
        if not os.path.exists(folder):
            print(f"Creating folder: {folder}")
            os.makedirs(folder)

        path = f"{filename}.{self._extension}"
        counter = 1
        while os.path.exists(path):
            path = f"{filename}_{counter:02}.{self._extension}"
            counter += 1
        
        return path
    

    # Returns filename without extension
    def getFileName(self, srcFile):
        filename = os.path.normpath(srcFile)
        dirname, filename = os.path.split(filename)
        filename = os.path.basename(filename)
        filename = os.path.splitext(filename)[0]

        skipLeft = self.skipDirs
        while dirname and skipLeft > 0:
            dirname = os.path.dirname(dirname)
            skipLeft -= 1

        folderNamesLeft = self.folderNames
        while dirname and folderNamesLeft > 0:
            dirname, currentDir = os.path.split(dirname)
            filename = f"{currentDir}_{filename}"
            folderNamesLeft -= 1

        subfoldersLeft = self.subfolders
        while dirname and subfoldersLeft > 0:
            dirname, currentDir = os.path.split(dirname)
            filename = os.path.join(currentDir, filename)
            subfoldersLeft -= 1

        return filename + self.suffix
