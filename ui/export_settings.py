import os, superqt
from PySide6 import QtWidgets
from PySide6.QtCore import Slot
import cv2 as cv
from lib import qtlib
from config import Config


INTERP_MODES = {
    "Nearest": cv.INTER_NEAREST,
    "Linear":  cv.INTER_LINEAR,
    "Cubic":   cv.INTER_CUBIC,
    "Area":    cv.INTER_AREA,
    "Lanczos": cv.INTER_LANCZOS4
}

SAVE_PARAMS = {
    "PNG":  [cv.IMWRITE_PNG_COMPRESSION, 9],
    "JPG":  [cv.IMWRITE_JPEG_QUALITY, 100],
    "WEBP": [cv.IMWRITE_WEBP_QUALITY, 100]
}


class ExportSettings(QtWidgets.QWidget):
    def __init__(self, filelist):
        super().__init__()
        self.exportPath = ExportPath()
        self.filelist = filelist

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._buildExport())

        self.txtPathSample = QtWidgets.QPlainTextEdit()
        self.txtPathSample.setReadOnly(True)
        qtlib.setMonospace(self.txtPathSample, 0.9)
        layout.addWidget(self.txtPathSample)

        self.setLayout(layout)


    def _buildExport(self):
        group = superqt.QCollapsible("Export Settings")
        group.layout().setContentsMargins(2, 2, 2, 0)
        group.setFrameStyle(QtWidgets.QFrame.Shape.NoFrame)
        group.setLineWidth(0)

        group.addWidget(self._buildSave())
        group.addWidget(self._buildDestination())
        return group

    def _buildSave(self):
        self.cboInterpUp = QtWidgets.QComboBox()
        self.cboInterpUp.addItems(INTERP_MODES.keys())
        self.cboInterpUp.setCurrentIndex(4) # Default: Lanczos

        self.cboInterpDown = QtWidgets.QComboBox()
        self.cboInterpDown.addItems(INTERP_MODES.keys())
        self.cboInterpDown.setCurrentIndex(3) # Default: Area

        self.cboFormat = QtWidgets.QComboBox()
        self.cboFormat.addItems(SAVE_PARAMS.keys())
        self.cboFormat.currentTextChanged.connect(self.updateExport)

        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addRow("Interp 🠕:", self.cboInterpUp)
        layout.addRow("Interp 🠗:", self.cboInterpDown)
        layout.addRow("Format:", self.cboFormat)

        group = QtWidgets.QGroupBox("Parameter")
        group.setLayout(layout)
        return group

    def _buildDestination(self):
        self.btnChoosePath = QtWidgets.QPushButton("Choose Path...")
        self.btnChoosePath.clicked.connect(self.chooseExportPath)

        self.spinFolderSkip = QtWidgets.QSpinBox()
        self.spinFolderSkip.valueChanged.connect(self.updateExport)

        self.spinFolderNames = QtWidgets.QSpinBox()
        self.spinFolderNames.valueChanged.connect(self.updateExport)

        self.spinSubfolders = QtWidgets.QSpinBox()
        self.spinSubfolders.valueChanged.connect(self.updateExport)

        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addRow(self.btnChoosePath)
        layout.addRow("Folder Skip:", self.spinFolderSkip)
        layout.addRow("Folder Names:", self.spinFolderNames)
        layout.addRow("Subfolders:", self.spinSubfolders)

        group = QtWidgets.QGroupBox("Destination")
        group.setLayout(layout)
        return group


    def getInterpolationMode(self, upscale):
        cbo = self.cboInterpUp if upscale else self.cboInterpDown
        return INTERP_MODES[ cbo.currentText() ]

    def getSaveParams(self):
        key = self.cboFormat.currentText()
        return SAVE_PARAMS[key]


    @Slot()
    def chooseExportPath(self):
        path = self.exportPath.basePath
        opts = QtWidgets.QFileDialog.ShowDirsOnly
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose save folder", path, opts)
        if path:
            self.exportPath.basePath = path
            self.updateExport()

    @Slot()
    def setExportSize(self, width: int, height: int):
        self.exportPath.suffix = f"_{width}x{height}"

    @Slot()
    def updateExport(self):
        self.exportPath.extension   = self.cboFormat.currentText()
        self.exportPath.skipDirs    = self.spinFolderSkip.value()
        self.exportPath.subfolders  = self.spinSubfolders.value()
        self.exportPath.folderNames = self.spinFolderNames.value()
        #self.export.suffix = f"_{self.spinW.value()}x{self.spinH.value()}"

        examplePath = self.exportPath.getExportPath(self.filelist.getCurrentFile())
        examplePath = "/\n\n".join(os.path.split(examplePath))
        self.txtPathSample.setPlainText(examplePath)



class ExportPath:
    def __init__(self):
        self.basePath = Config.pathExport
        self._extension = "png"
        self.suffix = ""

        self.skipDirs = 0       # Skip path components
        self.folderNames = 0    # Include folder names in filename
        self.subfolders = 0     # Save into nested directory structure


    @property
    def extension(self) -> str:
        return self._extension

    @extension.setter
    def extension(self, ext) -> None:
        self._extension = ext.lower()


    def getExportPath(self, srcFile) -> str:
        filename = self.getFileName(srcFile)
        filename = os.path.join(self.basePath, filename)

        path = f"{filename}.{self._extension}"
        counter = 1
        while os.path.exists(path):
            path = f"{filename}_{counter:02}.{self._extension}"
            counter += 1
        
        return path

    @staticmethod
    def createFolders(filename) -> None:
        folder = os.path.dirname(filename)
        if not os.path.exists(folder):
            print(f"Creating folder: {folder}")
            os.makedirs(folder)
    

    # Returns filename without extension
    def getFileName(self, srcFile) -> str:
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
            if not currentDir:
                break
            filename = f"{currentDir}_{filename}"
            folderNamesLeft -= 1

        subfoldersLeft = self.subfolders
        while dirname and subfoldersLeft > 0:
            dirname, currentDir = os.path.split(dirname)
            if not currentDir:
                break
            filename = os.path.join(currentDir, filename)
            subfoldersLeft -= 1

        return filename + self.suffix


    @staticmethod
    def getSavePath(srcFile: str, extension: str, suffix: str = None) -> str:
        filename = os.path.normpath(srcFile)
        dirname, filename = os.path.split(filename)
        filename = os.path.basename(filename)
        filename = os.path.splitext(filename)[0]

        extension = extension.lstrip(".")
        filename = f"{filename}{suffix}.{extension}"
        return os.path.join(dirname, filename)
