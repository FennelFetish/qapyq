import os, shutil, re
from datetime import datetime
from enum import Enum
from typing import Callable
from typing_extensions import override
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QThreadPool
from PySide6.QtGui import QImageReader
from config import Config
from ui.tab import ImgTab
from lib import qtlib
from lib.filelist import FileList
from .batch_task import BatchTask, BatchSignalHandler, BatchUtil
import ui.export_settings as export


# TODO: Multiple IO threads?


LEGEND_WIDTH = 80


class Mode(Enum):
    Copy    = "copy"
    Move    = "move"
    Symlink = "symlink"


class BatchFile(QtWidgets.QWidget):
    BASEPATH_VAR_PATTERN = re.compile(r'{{.*basepath.*}}')

    def __init__(self, tab: ImgTab, logSlot, progressBar, statusBar):
        super().__init__()
        self.tab = tab
        self.log = logSlot
        self.progressBar: QtWidgets.QProgressBar = progressBar
        self.statusBar: qtlib.ColoredMessageStatusBar = statusBar

        self._task = None
        self._taskSignalHandler = None

        self.btnStart = QtWidgets.QPushButton("Start Batch File")
        self.btnStart.clicked.connect(self.startStop)

        self.destinationSettings = FileDestinationSettings(tab)
        self.imageSettings = FileImageSettings()
        self.captionSettings = FileCaptionSettings()
        self.maskSettings = FileMaskSettings(tab)

        self.imageSettings.toggled.connect(self.maskSettings.onImageToggled)

        layout = QtWidgets.QGridLayout()
        layout.addWidget(self.destinationSettings, 0, 0, 1, 2)
        layout.addWidget(self.imageSettings, 1, 0)
        layout.addWidget(self.captionSettings, 1, 1)
        layout.addWidget(self.maskSettings, 2, 0, 1, 2)
        layout.setRowStretch(3, 1)
        layout.addWidget(self.btnStart, 4, 0, 1, 2)

        self.setLayout(layout)


    def onFileChanged(self, currentFile):
        self.destinationSettings.onFileChanged(currentFile)
        self.maskSettings.onFileChanged(currentFile)


    def _confirmStart(self) -> bool:
        pathTemplate = self.destinationSettings.destinationPathTemplate
        ops = []

        match self.destinationSettings.mode:
            case Mode.Copy: modeText = "Copy the files to"
            case Mode.Move: modeText = "Move the files to"
            case Mode.Symlink: modeText = "Create symlinks in"
            case _: raise ValueError("Invalid mode")

        ops.append(f"{modeText}:")
        ops.append(f"<tab><code>{pathTemplate}</code>")
        ops.append("<tab>and evaluate the path template for each image.")

        if self.destinationSettings.flatFolders or (self.BASEPATH_VAR_PATTERN.search(pathTemplate) is None):
            ops.append("Discard the folder hierarchy and write all files directly into the target folder")
        else:
            basePath = self.destinationSettings.basePath
            if not basePath:
                self.tab.filelist._lazyLoadFolder()
                basePath = self.tab.filelist.commonRoot
            ops.append(f"Keep the folder hierarchy relative to '{os.path.abspath(basePath)}'")

        if self.imageSettings.isChecked():
            if self.imageSettings.overwriteFiles:
                ops.append(qtlib.htmlRed(f"Include images and overwrite existing files!"))
            else:
                ops.append(f"Include images and skip existing files")
        else:
            ops.append(f"Skip images")

        if self.maskSettings.isChecked():
            if self.maskSettings.maskPathSettings.overwriteFiles:
                ops.append(qtlib.htmlRed(f"Include masks and overwrite existing files!"))
            else:
                ops.append(f"Include masks and skip existing files")

            if self.maskSettings.chkRenameToImgName.isChecked():
                ops.append("Rename the mask to the exact filename of the image")
                ops.append("<tab>(but keep extension of mask).")
        else:
            ops.append(f"Skip masks")

        if self.captionSettings.isChecked():
            if self.captionSettings.chkIncludeJson.isChecked():
                if self.captionSettings.chkIncludeTxt.isChecked():
                    captionContent = "JSON and TXT files"
                else:
                    captionContent = "JSON files"
            elif self.captionSettings.chkIncludeTxt.isChecked():
                captionContent = "TXT files"
            else:
                captionContent = ""

            if captionContent:
                if self.captionSettings.chkArchiveTextFiles.isChecked():
                    if self.captionSettings.overwriteFiles:
                        ops.append(qtlib.htmlRed(f"Write {captionContent} into a ZIP archive and overwrite an existing file!"))
                    else:
                        ops.append(f"Write {captionContent} into a ZIP archive and append a counter if the archive already exists")
                else:
                    if self.captionSettings.overwriteFiles:
                        ops.append(qtlib.htmlRed(f"Include {captionContent} and overwrite existing files!"))
                    else:
                        ops.append(f"Include {captionContent} and skip existing files")
            else:
                ops.append(f"Skip captions")
        else:
            ops.append(f"Skip captions")

        return BatchUtil.confirmStart("File", self.tab.filelist.getNumFiles(), ops, self)

    @Slot()
    def startStop(self):
        if self._task:
            if BatchUtil.confirmAbort(self):
                self._task.abort()
            return

        if not self._confirmStart():
            return

        self.destinationSettings.saveExportPreset()
        self.maskSettings.saveExportPreset()
        self.btnStart.setText("Abort")

        basePath = self.destinationSettings.basePath
        if not basePath:
            basePath = self.tab.filelist.commonRoot

        self._task = BatchFileTask(self.log, self.tab.filelist)
        self._task.destPathTemplate = self.destinationSettings.destinationPathTemplate

        self._task.mode        = self.destinationSettings.mode
        self._task.basePath    = os.path.abspath(basePath)
        self._task.flatFolders = self.destinationSettings.flatFolders

        if self.imageSettings.isChecked():
            self._task.includeImages     = True
            self._task.overwriteImages   = self.imageSettings.overwriteFiles

        if self.maskSettings.isChecked():
            self._task.includeMasks      = True
            self._task.renameMasks       = self.maskSettings.chkRenameToImgName.isChecked()
            self._task.overwriteMasks    = self.maskSettings.maskPathSettings.overwriteFiles
            self._task.maskPathTemplate  = self.maskSettings.maskPathSettings.pathTemplate

        if self.captionSettings.isChecked():
            self._task.includeJson       = self.captionSettings.chkIncludeJson.isChecked()
            self._task.includeTxt        = self.captionSettings.chkIncludeTxt.isChecked()
            self._task.overwriteCaptions = self.captionSettings.overwriteFiles
            self._task.createArchive     = self.captionSettings.chkArchiveTextFiles.isChecked()
            self._task.archivePath       = self.captionSettings.txtArchivePath.text()

        self._taskSignalHandler = BatchSignalHandler(self.statusBar, self.progressBar, self._task)
        self._taskSignalHandler.finished.connect(self.taskDone)
        QThreadPool.globalInstance().start(self._task)

    @Slot()
    def taskDone(self):
        self.btnStart.setText("Start Batch File")
        self._task = None
        self._taskSignalHandler = None



class FileDestinationSettings(QtWidgets.QGroupBox):
    EXPORT_PRESET_KEY = "batch-file-dest"

    def __init__(self, tab: ImgTab):
        super().__init__("Destination Path")
        self.tab = tab

        self.destPathParser = DestinationPathVariableParser(tab.filelist)
        self.destPathParser.setup(tab.filelist.getCurrentFile(), None)

        config = Config.exportPresets.get(self.EXPORT_PRESET_KEY, {})
        defaultPathTemplate = os.path.join(Config.pathExport, "{{basepath}}", "{{name.ext}}")

        self.destPathSettings = export.PathSettings(self.destPathParser, showInfo=False)
        self.destPathSettings.setAsInput()
        self.destPathSettings.layout().setColumnMinimumWidth(0, LEGEND_WIDTH)
        self.destPathSettings.btnChoosePath.setMinimumWidth(110)
        self.destPathSettings.pathTemplate = config.get("path_template", defaultPathTemplate)

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 1)
        layout.setColumnStretch(4, 0)
        layout.setColumnMinimumWidth(0, LEGEND_WIDTH)
        layout.setColumnMinimumWidth(2, 8)

        row = 0
        infoText = "This template defines the destination path and must include a filename for the image. " \
                   "If the filename is changed, all included files will be saved with the new name."
        layout.addWidget(QtWidgets.QLabel(infoText), row, 0, 1, 5)

        row += 1
        layout.addWidget(QtWidgets.QLabel("Use the {{basepath}} variable to keep the folder structure."), row, 0, 1, 5)

        row += 1
        layout.setRowMinimumHeight(row, 8)

        row += 1
        layout.addWidget(self.destPathSettings, row, 0, 1, 5)

        row += 1
        layout.setRowMinimumHeight(row, 8)

        row += 1
        layout.addWidget(QtWidgets.QLabel("Mode:"), row, 0)

        self.cboMode = QtWidgets.QComboBox()
        self.cboMode.addItem("Copy Files", Mode.Copy)
        self.cboMode.addItem("Move Files", Mode.Move)
        self.cboMode.addItem("Create Symlinks", Mode.Symlink)
        layout.addWidget(self.cboMode, row, 1)

        self.chkFlatFolders = QtWidgets.QCheckBox("Flatten folder structure")
        self.chkFlatFolders.setToolTip("This will empty the {{basepath}} variable.")
        self.chkFlatFolders.toggled.connect(self._onFlatFoldersToggled)
        layout.addWidget(self.chkFlatFolders, row, 3)

        row += 1
        self.lblBasePath = QtWidgets.QLabel("Base Path:")
        layout.addWidget(self.lblBasePath, row, 0)

        self.txtBasePath = QtWidgets.QLineEdit("")
        self.txtBasePath.textChanged.connect(self._onBasePathChanged)
        qtlib.setMonospace(self.txtBasePath)
        layout.addWidget(self.txtBasePath, row, 1, 1, 3)

        btnChooseBasePath = QtWidgets.QPushButton("Choose Folder...")
        btnChooseBasePath.setMinimumWidth(110)
        btnChooseBasePath.clicked.connect(self._chooseBasePath)
        layout.addWidget(btnChooseBasePath, row, 4)

        self.setLayout(layout)

    @property
    def destinationPathTemplate(self) -> str:
        return self.destPathSettings.pathTemplate

    @property
    def mode(self) -> Mode:
        return self.cboMode.currentData()

    @property
    def basePath(self) -> str:
        return self.txtBasePath.text()

    @property
    def flatFolders(self) -> bool:
        return self.chkFlatFolders.isChecked()


    def onFileChanged(self, currentFile):
        commonRoot = self.tab.filelist.commonRoot
        if not commonRoot:
            self.tab.filelist._lazyLoadFolder()
            commonRoot = self.tab.filelist.commonRoot

        self.txtBasePath.setPlaceholderText(f"If empty, will use common root of current files: {commonRoot}")

        self.destPathParser.setup(currentFile, None)
        self.destPathParser.setImageDimension(self.tab.imgview.image.pixmap())
        self.destPathSettings.updatePreview()

    @Slot()
    def _chooseBasePath(self):
        path = self.txtBasePath.text()
        if not path:
            path = self.tab.filelist.commonRoot

        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose base directory", path)
        if path:
            path = os.path.abspath(path)
            self.txtBasePath.setText(path)

    @Slot()
    def _onBasePathChanged(self, basePath: str):
        self.destPathParser.basePath = basePath
        self.destPathSettings.updatePreview()

    @Slot()
    def _onFlatFoldersToggled(self, state: bool):
        enabled = not state
        self.lblBasePath.setEnabled(enabled)
        self.txtBasePath.setEnabled(enabled)

        self.destPathParser.flatFolders = state
        self.destPathSettings.updatePreview()

    def saveExportPreset(self):
        Config.exportPresets[self.EXPORT_PRESET_KEY] = {
            "path_template": self.destPathSettings.pathTemplate
        }


class DestinationPathVariableParser(export.ExportVariableParser):
    def __init__(self, filelist: FileList | None):
        super().__init__()
        self.filelist = filelist
        self.basePath: str = ""
        self.flatFolders: bool = False

    @override
    def _getImgProperties(self, var: str) -> str | None:
        if var != "basepath":
            return super()._getImgProperties(var)

        if self.flatFolders:
            return None

        basePath = self.basePath
        if not basePath:
            if self.filelist:
                basePath = self.filelist.commonRoot
            else:
                return None

        try:
            path = os.path.dirname(self.imgPath)
            return self.makeRelPath(path, basePath)
        except ValueError:
            return None



class BaseFileSettings(QtWidgets.QGroupBox):
    def __init__(self, title: str):
        super().__init__(title)
        self.setCheckable(True)
        self.setChecked(True)

        self.chkOverwriteFiles = QtWidgets.QCheckBox("Overwrite existing files")
        self.chkOverwriteFiles.toggled.connect(self._onOverwriteToggled)

        self.toggled.connect(self._onGroupToggled)

    @property
    def overwriteFiles(self) -> bool:
        return self.chkOverwriteFiles.isChecked()

    @Slot()
    def _onOverwriteToggled(self, state: bool):
        style = f"color: {qtlib.COLOR_RED}" if state else None
        self.chkOverwriteFiles.setStyleSheet(style)

    @Slot()
    def _onGroupToggled(self, state: bool):
        if state:
            self._onOverwriteToggled(self.chkOverwriteFiles.isChecked())
        else:
            self.chkOverwriteFiles.setStyleSheet("")


class FileImageSettings(BaseFileSettings):
    def __init__(self):
        super().__init__("Include Images")
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.chkOverwriteFiles, 0, 0)
        self.setLayout(layout)


class FileCaptionSettings(BaseFileSettings):
    def __init__(self):
        super().__init__("Include Captions")

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnStretch(2, 1)

        self.chkIncludeJson = QtWidgets.QCheckBox("Include .json files")
        self.chkIncludeJson.setChecked(True)
        layout.addWidget(self.chkIncludeJson, 0, 0)

        self.chkIncludeTxt = QtWidgets.QCheckBox("Include .txt files")
        self.chkIncludeTxt.setChecked(True)
        layout.addWidget(self.chkIncludeTxt, 1, 0)

        self.chkArchiveTextFiles = QtWidgets.QCheckBox("Write to ZIP archive:")
        self.chkArchiveTextFiles.toggled.connect(self._onArchiveToggled)
        layout.addWidget(self.chkArchiveTextFiles, 0, 1)

        self.txtArchivePath = QtWidgets.QLineEdit("")
        qtlib.setMonospace(self.txtArchivePath)
        layout.addWidget(self.txtArchivePath, 0, 2)

        self.btnChooseArchivePath = QtWidgets.QPushButton("Choose File...")
        self.btnChooseArchivePath.setMinimumWidth(110)
        self.btnChooseArchivePath.clicked.connect(self._chooseArchiveFile)
        layout.addWidget(self.btnChooseArchivePath, 0, 4)

        layout.addWidget(self.chkOverwriteFiles, 1, 1, 1, 2)

        self._onArchiveToggled(self.chkArchiveTextFiles.isChecked())
        self.setLayout(layout)

    @Slot()
    def _onArchiveToggled(self, state: bool):
        self.txtArchivePath.setEnabled(state)
        self.btnChooseArchivePath.setEnabled(state)

    @Slot()
    def _chooseArchiveFile(self):
        path = self.txtArchivePath.text()
        if not path:
            filename = datetime.now().strftime("captions_%Y-%m-%d.zip")
            path = os.path.join(Config.pathExport, filename)

        filter = "Archive Files (*.zip)"
        path, filter = QtWidgets.QFileDialog.getSaveFileName(self, "Choose archive file", path, filter)
        if path:
            path = os.path.abspath(path)
            self.txtArchivePath.setText(path)


class FileMaskSettings(QtWidgets.QGroupBox):
    EXPORT_PRESET_KEY = "batch-file-mask"

    def __init__(self, tab: ImgTab):
        super().__init__("Include Masks from:")
        self.tab = tab

        self.maskPathParser = export.ExportVariableParser()
        self.maskPathParser.setup(tab.filelist.getCurrentFile(), None)

        self.chkRenameToImgName = QtWidgets.QCheckBox("Rename to filename of image")
        self.chkRenameToImgName.setToolTip("Only available when not including images.\nWill keep the file extension of the mask.")
        self.chkRenameToImgName.setEnabled(False)

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        config = Config.exportPresets.get(self.EXPORT_PRESET_KEY, {})
        self.maskPathSettings = export.PathSettings(self.maskPathParser, showInfo=False)
        self.maskPathSettings.layout().addWidget(self.chkRenameToImgName, 2, 2)
        self.maskPathSettings.layout().setColumnMinimumWidth(0, LEGEND_WIDTH)
        self.maskPathSettings.btnChoosePath.setMinimumWidth(110)
        self.maskPathSettings.pathTemplate   = config.get("path_template", "{{path}}-masklabel.png")
        self.maskPathSettings.overwriteFiles = False

        layout.addWidget(self.maskPathSettings, 0, 0)

        self.setCheckable(True)
        self.setChecked(True)
        self.setLayout(layout)

        self.toggled.connect(self._onToggled)

    def onFileChanged(self, currentFile):
        self.maskPathParser.setup(currentFile, None)
        self.maskPathParser.setImageDimension(self.tab.imgview.image.pixmap())
        self.maskPathSettings.updatePreview()

    @Slot()
    def onImageToggled(self, state: bool):
        self.chkRenameToImgName.setEnabled(not state)
        if state:
            self.chkRenameToImgName.setChecked(False)

    def _onToggled(self, state: bool):
        self.maskPathSettings.setEnabled(state)

    def saveExportPreset(self):
        Config.exportPresets[self.EXPORT_PRESET_KEY] = {
            "path_template": self.maskPathSettings.pathTemplate
        }



class BatchFileTask(BatchTask):
    def __init__(self, log, filelist):
        super().__init__("file", log, filelist)

        self.mode              = Mode.Move
        self.destPathTemplate  = ""
        self.basePath          = ""
        self.flatFolders       = False

        self.includeImages     = False
        self.overwriteImages   = False

        self.includeMasks      = False
        self.renameMasks       = False
        self.overwriteMasks    = False
        self.maskPathTemplate  = ""

        self.includeJson       = False
        self.includeTxt        = False
        self.overwriteCaptions = False
        self.createArchive     = False
        self.archivePath       = ""

        self.fileDest: Callable              = None
        self.captionDest: Callable           = None
        self.captionCleanup: Callable | None = None


    def runPrepare(self):
        self.destinationPathParser = DestinationPathVariableParser(None)
        self.destinationPathParser.basePath = self.basePath
        self.destinationPathParser.flatFolders = self.flatFolders

        self.maskPathParser = export.ExportVariableParser()

        if self.renameMasks and self.includeImages:
            raise ValueError("Cannot rename masks when images are included")

        match self.mode:
            case Mode.Copy: self.fileDest = self.copyFile
            case Mode.Move: self.fileDest = self.moveFile
            case Mode.Symlink: self.fileDest = self.createSymlink
            case _: raise ValueError("Invalid mode")

        if self.createArchive and (self.includeJson or self.includeTxt):
            if not self.archivePath:
                raise ValueError("Archive path is empty")
            if not self.archivePath.endswith(".zip"):
                raise ValueError("Archive path must end with '.zip'")

            self.captionDest, self.captionCleanup = self.createArchiveDest(self.archivePath)
        else:
            self.captionDest = self.processFile


    def runCleanup(self):
        # TODO: Copy the archive before the task ends.
        if self.captionCleanup:
            self.captionCleanup()


    def runProcessFile(self, imgPath: str) -> str | None:
        self.setupPathParsers(imgPath)
        targetPath = self.destinationPathParser.parsePath(self.destPathTemplate, overwriteFiles=True)
        targetFolder, targetFileName = os.path.split(targetPath)

        targetFileNameNoExt, targetFileExt = os.path.splitext(targetFileName)
        if not targetFileExt.lstrip("."):
            self.log(f"WARNING: Missing file extension: {targetPath}")
            return None

        writtenFile = None

        if self.includeImages:
            wrote = self.processFile(imgPath, targetFolder, targetFileName, self.overwriteImages)
            writtenFile = writtenFile or wrote

        if self.includeMasks:
            wrote = self.processMask(imgPath, targetFolder, targetFileName)
            writtenFile = writtenFile or wrote

        srcPathNoExt = os.path.splitext(imgPath)[0]

        if self.includeJson:
            wrote = self.processCaption(f"{srcPathNoExt}.json", targetFolder, f"{targetFileNameNoExt}.json")
            writtenFile = writtenFile or wrote

        if self.includeTxt:
            wrote = self.processCaption(f"{srcPathNoExt}.txt", targetFolder, f"{targetFileNameNoExt}.txt")
            writtenFile = writtenFile or wrote

        return writtenFile


    def setupPathParsers(self, imgPath: str):
        self.destinationPathParser.setup(imgPath)
        self.maskPathParser.setup(imgPath)

        imgReader = QImageReader(imgPath)
        imgSize = imgReader.size()

        self.destinationPathParser.width = imgSize.width()
        self.destinationPathParser.height = imgSize.height()

        self.maskPathParser.width = imgSize.width()
        self.maskPathParser.height = imgSize.height()


    def processFile(self, srcPath: str, targetFolder: str, targetFileName: str, overwrite: bool) -> str | None:
        destPath = os.path.join(targetFolder, targetFileName)
        if (not overwrite) and os.path.exists(destPath):
            return None

        if os.path.isdir(destPath):
            self.log(f"WARNING: Target path is a folder (missing filename?): {destPath}")
            return None

        if not os.path.exists(targetFolder):
            self.log(f"Creating folder: {targetFolder}")
            os.makedirs(targetFolder)

        self.fileDest(srcPath, destPath)
        return destPath

    def processMask(self, imgPath: str, targetFolder: str, targetFileName: str) -> str | None:
        maskSrcPath = self.maskPathParser.parsePath(self.maskPathTemplate, overwriteFiles=True)
        if not os.path.exists(maskSrcPath):
            return None

        targetNameNoExt = os.path.splitext(targetFileName)[0]

        if self.renameMasks:
            maskExt = os.path.splitext(maskSrcPath)[1]
            targetMaskName = targetNameNoExt + maskExt
        else:
            srcNameNoExt = os.path.splitext(os.path.basename(imgPath))[0]
            targetMaskName = os.path.basename(maskSrcPath)
            if srcNameNoExt != targetNameNoExt:
                targetMaskName = targetMaskName.replace(srcNameNoExt, targetNameNoExt, 1)

        return self.processFile(maskSrcPath, targetFolder, targetMaskName, self.overwriteMasks)

    def processCaption(self, srcPath: str, targetFolder: str, targetFileName: str) -> str | None:
        if os.path.exists(srcPath):
            return self.captionDest(srcPath, targetFolder, targetFileName, self.overwriteCaptions)
        else:
            return None


    def copyFile(self, srcPath: str, destPath: str):
        self.log(f"Copy file '{srcPath}' => '{destPath}'")
        shutil.copy2(srcPath, destPath)

    def moveFile(self, srcPath: str, destPath: str):
        self.log(f"Move file '{srcPath}' => '{destPath}'")
        shutil.move(srcPath, destPath)

    def createSymlink(self, srcPath: str, destPath: str):
        # This will fail if destPath exists
        self.log(f"Symlink '{srcPath}' <= '{destPath}'")
        os.symlink(srcPath, destPath)


    def createArchiveDest(self, archivePath: str):
        import zipfile, tempfile
        fd, tempArchivePath = tempfile.mkstemp(suffix=".zip")
        self.log(f"Creating temporary ZIP archive: {tempArchivePath}")
        tempFile = os.fdopen(fd, 'wb')
        archive = zipfile.ZipFile(tempFile, 'w', self.getCompressionMethod())

        # Strip leading components without variables
        head, tail = export.ExportVariableParser.splitPathByVars(self.destPathTemplate)
        archivePathTemplate = tail or head
        del head, tail

        numFilesAdded = 0

        def archiveFile(srcPath: str, targetFolder: str, targetFileName: str, overwrite: bool) -> str:
            arcPath = self.destinationPathParser.parse(archivePathTemplate)
            arcPath = os.path.normpath(os.path.dirname(arcPath))
            arcPath = self.removeUpLevel(arcPath)
            arcPath = os.path.join(arcPath, targetFileName)

            nonlocal numFilesAdded
            numFilesAdded += 1

            self.log(f"Archive file '{srcPath}' => '{arcPath}'")
            archive.write(srcPath, arcname=arcPath)
            return archivePath

        def archiveFinalize() -> None:
            archive.close()
            tempFile.close()

            if numFilesAdded > 0:
                correctedArchivePath = self.prepareArchiveDestination(archivePath)
                self.log(f"Moving temporary ZIP archive to: {correctedArchivePath}")

                # This will overwrite the destination
                shutil.move(tempArchivePath, correctedArchivePath)
            else:
                self.log(f"Resulting ZIP archive is empty, deleting: {tempArchivePath}")
                os.remove(tempArchivePath)

        return archiveFile, archiveFinalize

    def prepareArchiveDestination(self, archivePath: str) -> str:
        if not self.overwriteCaptions:
            archivePathNoExt, archiveExt = os.path.splitext(archivePath)
            counter = 1
            while os.path.exists(archivePath):
                archivePath = f"{archivePathNoExt}_{counter:03}{archiveExt}"
                counter += 1

        archiveFolder = os.path.dirname(archivePath)
        if not os.path.exists(archiveFolder):
            self.log(f"Creating folder for archive: {archiveFolder}")
            os.makedirs(archiveFolder)

        return archivePath

    def getCompressionMethod(self) -> int:
        import zipfile
        try:
            import zlib
            return zipfile.ZIP_DEFLATED
        except:
            return zipfile.ZIP_STORED

    def removeUpLevel(self, path: str) -> str:
        while path.startswith(".."):
            if len(path) == 2:
                return ""
            if len(path) > 2 and path[2] == os.sep:
                path = path[3:]
            else:
                break

        return path
