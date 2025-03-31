import os, shutil
from datetime import datetime
from enum import Enum
from typing import Callable
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
from config import Config
from infer import Inference
from ui.tab import ImgTab
from lib import qtlib
from .batch_task import BatchTask, BatchSignalHandler, BatchUtil
import ui.export_settings as export


# TODO: Multiple IO threads?

# TODO: Add checkbox to mask sections: "Rename to match image filename" (only enabled when "Include images" is disabled)


class Mode(Enum):
    Copy    = "copy"
    Move    = "move"
    Symlink = "symlink"


class BatchFile(QtWidgets.QWidget):
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

        self.imageSettings = FileImageSettings()
        self.captionSettings = FileCaptionSettings()
        self.maskSettings = FileMaskSettings(tab)

        layout = QtWidgets.QGridLayout()
        layout.addWidget(self._buildDestination(), 0, 0, 1, 2)
        layout.addWidget(self.imageSettings, 1, 0)
        layout.addWidget(self.captionSettings, 1, 1)
        layout.addWidget(self.maskSettings, 2, 0, 1, 2)
        # TODO: Preview of resulting folder structure, with target path, base path, +archive file
        layout.setRowStretch(3, 1)
        layout.addWidget(self.btnStart, 4, 0, 1, 2)

        self.setLayout(layout)

    def _buildDestination(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 1)
        layout.setColumnStretch(4, 0)
        layout.setColumnMinimumWidth(2, 8)

        row = 0
        layout.addWidget(QtWidgets.QLabel("Target Folder:"), row, 0)

        self.txtTargetPath = QtWidgets.QLineEdit(Config.pathExport)
        qtlib.setMonospace(self.txtTargetPath)
        layout.addWidget(self.txtTargetPath, row, 1, 1, 3)

        btnChooseTargetPath = QtWidgets.QPushButton("Choose Folder...")
        btnChooseTargetPath.setMinimumWidth(110)
        btnChooseTargetPath.clicked.connect(self._chooseTargetFolder)
        layout.addWidget(btnChooseTargetPath, row, 4)

        row += 1
        layout.addWidget(QtWidgets.QLabel("Mode:"), row, 0)

        self.cboMode = QtWidgets.QComboBox()
        self.cboMode.addItem("Copy Files", Mode.Copy)
        self.cboMode.addItem("Move Files", Mode.Move)
        self.cboMode.addItem("Create Symlinks", Mode.Symlink)
        layout.addWidget(self.cboMode, row, 1)

        self.chkFlatFolders = QtWidgets.QCheckBox("Flatten folder structure")
        self.chkFlatFolders.toggled.connect(self._onFlatFoldersToggled)
        layout.addWidget(self.chkFlatFolders, row, 3)

        row += 1
        self.lblBasePath = QtWidgets.QLabel("Base Path:")
        layout.addWidget(self.lblBasePath, row, 0)

        self.txtBasePath = QtWidgets.QLineEdit("")
        qtlib.setMonospace(self.txtBasePath)
        layout.addWidget(self.txtBasePath, row, 1, 1, 3)

        btnChooseBasePath = QtWidgets.QPushButton("Choose Folder...")
        btnChooseBasePath.setMinimumWidth(110)
        btnChooseBasePath.clicked.connect(self._chooseBasePath)
        layout.addWidget(btnChooseBasePath, row, 4)

        groupBox = QtWidgets.QGroupBox("Destination")
        groupBox.setLayout(layout)
        return groupBox


    @Slot()
    def _chooseTargetFolder(self):
        path = self.txtTargetPath.text()
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose target directory", path)
        if path:
            path = os.path.abspath(path)
            self.txtTargetPath.setText(path)

    @Slot()
    def _chooseBasePath(self):
        path = self.txtBasePath.text()
        if not path:
            path = self.tab.filelist.commonRoot
        if not path:
            # commonRoot may be empty if folder wasn't lazy loaded yet
            path = self.txtTargetPath.text()

        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose base directory", path)
        if path:
            path = os.path.abspath(path)
            self.txtBasePath.setText(path)

    @Slot()
    def _onFlatFoldersToggled(self, state: bool):
        enabled = not state
        self.lblBasePath.setEnabled(enabled)
        self.txtBasePath.setEnabled(enabled)


    def onFileChanged(self, currentFile):
        self.maskSettings.onFileChanged(currentFile)
        self.txtBasePath.setPlaceholderText(f"If empty, will use common root of current files: {self.tab.filelist.commonRoot}")


    def _confirmStart(self) -> bool:
        ops = []

        match self.cboMode.currentData():
            case Mode.Copy: modeText = "Copy the files to"
            case Mode.Move: modeText = "Move the files to"
            case Mode.Symlink: modeText = "Create symlinks to the files in"
            case _: raise ValueError("Invalid mode")
        ops.append(f"{modeText} '{os.path.abspath(self.txtTargetPath.text())}'")

        if self.chkFlatFolders.isChecked():
            ops.append("Discard the folder hierarchy and write all files directly into the target folder")
        else:
            basePath = self.txtBasePath.text()
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

        self.btnStart.setText("Abort")

        basePath = self.txtBasePath.text()
        if not basePath:
            basePath = self.tab.filelist.commonRoot

        self._task = BatchFileTask(self.log, self.tab.filelist)
        self._task.mode         = self.cboMode.currentData()
        self._task.targetFolder = os.path.abspath(self.txtTargetPath.text())
        self._task.basePath     = os.path.abspath(basePath)
        self._task.flatFolders  = self.chkFlatFolders.isChecked()

        if self.imageSettings.isChecked():
            self._task.includeImages     = True
            self._task.overwriteImages   = self.imageSettings.overwriteFiles

        if self.maskSettings.isChecked():
            self._task.includeMasks      = True
            self._task.overwriteMasks    = self.maskSettings.maskPathSettings.overwriteFiles
            self._task.maskPathTemplate  = self.maskSettings.maskPathSettings.pathTemplate

        if self.captionSettings.isChecked():
            self._task.includeJson       = self.captionSettings.chkIncludeJson.isChecked()
            self._task.includeTxt        = self.captionSettings.chkIncludeTxt.isChecked()
            self._task.overwriteCaptions = self.captionSettings.overwriteFiles
            self._task.createArchive     = self.captionSettings.chkArchiveTextFiles.isChecked()

            archivePath = self.captionSettings.txtArchivePath.text()
            if not archivePath:
                archivePath = os.path.join(self.txtTargetPath.text(), "captions.zip")
            self._task.archivePath = archivePath

        self._taskSignalHandler = BatchSignalHandler(self.statusBar, self.progressBar, self._task)
        self._taskSignalHandler.finished.connect(self.taskDone)
        Inference().queueTask(self._task)

    @Slot()
    def taskDone(self):
        self.btnStart.setText("Start Batch File")
        self._task = None
        self._taskSignalHandler = None



class FileSettings(QtWidgets.QGroupBox):
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


class FileImageSettings(FileSettings):
    def __init__(self):
        super().__init__("Include Images")

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self.chkOverwriteFiles, 0, 0)

        self.setLayout(layout)


class FileCaptionSettings(FileSettings):
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

        # TODO: When "Overwrite Files" is disabled, this will append a timestamp (and counter) to the archive's filename. Saved in selected base folder.
        self.chkArchiveTextFiles = QtWidgets.QCheckBox("Write to ZIP archive:")
        self.chkArchiveTextFiles.toggled.connect(self._onArchiveToggled)
        layout.addWidget(self.chkArchiveTextFiles, 0, 1)

        self.txtArchivePath = QtWidgets.QLineEdit("")
        self.txtArchivePath.setPlaceholderText("If empty, will create archive file inside target folder")
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
    def __init__(self, tab: ImgTab):
        super().__init__("Include Masks from:")
        self.tab = tab

        self.maskPathParser = export.ExportVariableParser()
        self.maskPathParser.setup(tab.filelist.getCurrentFile(), None)

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.maskPathSettings = export.PathSettings(self.maskPathParser, showInfo=False)
        self.maskPathSettings.btnChoosePath.setMinimumWidth(110)
        self.maskPathSettings.pathTemplate   = "{{path}}-masklabel.png"
        self.maskPathSettings.overwriteFiles = False

        layout.addWidget(self.maskPathSettings, 0, 0)

        self.setCheckable(True)
        self.setChecked(True)
        self.setLayout(layout)

        self.toggled.connect(self._onToggled)

    def onFileChanged(self, currentFile):
        self.maskPathParser.setup(currentFile, None)
        #self.maskPathParser.setImageDimension(self.tab.imgview.image.pixmap())
        self.maskPathSettings.updatePreview()

    def _onToggled(self, state: bool):
        self.maskPathSettings.setEnabled(state)



class BatchFileTask(BatchTask):
    def __init__(self, log, filelist):
        super().__init__("file", log, filelist)

        self.mode              = Mode.Move
        self.targetFolder      = ""
        self.basePath          = ""
        self.flatFolders       = False

        self.includeImages     = False
        self.overwriteImages   = False

        self.includeMasks      = False
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
        if not os.path.isdir(self.targetFolder):
            raise ValueError("Target folder doesn't exist")

        self.maskPathParser = export.ExportVariableParser()

        match self.mode:
            case Mode.Copy: self.fileDest = self.copyFile
            case Mode.Move: self.fileDest = self.moveFile
            case Mode.Symlink: self.fileDest = self.createSymlink
            case _: raise ValueError("Invalid mode")

        if self.createArchive and (self.includeJson or self.includeTxt):
            if not self.archivePath.endswith(".zip"):
                raise ValueError("Archive path must end with '.zip'")
            self.captionDest, self.captionCleanup = self.createArchiveDest(self.archivePath)
        else:
            self.captionDest = self.processFile


    def runCleanup(self):
        if self.captionCleanup:
            self.captionCleanup()


    def runProcessFile(self, imgPath: str) -> str | None:
        imgFolder, imgFileName = os.path.split(imgPath)

        if self.flatFolders:
            targetFolder = self.targetFolder
        else:
            relPath = os.path.relpath(imgFolder, self.basePath)
            targetFolder = os.path.join(self.targetFolder, relPath)
            targetFolder = os.path.normpath(targetFolder)

        writtenFile = None

        if self.includeImages:
            wrote = self.processFile(imgPath, targetFolder, imgFileName, self.overwriteImages)
            writtenFile = writtenFile or wrote

        if self.includeMasks:
            wrote = self.processMask(imgPath, targetFolder)
            writtenFile = writtenFile or wrote

        srcPathNoExt  = os.path.splitext(imgPath)[0]
        fileNameNoExt = os.path.splitext(imgFileName)[0]

        if self.includeJson:
            wrote = self.processCaption(f"{srcPathNoExt}.json", targetFolder, f"{fileNameNoExt}.json", self.overwriteCaptions)
            writtenFile = writtenFile or wrote

        if self.includeTxt:
            wrote = self.processCaption(f"{srcPathNoExt}.txt", targetFolder, f"{fileNameNoExt}.txt", self.overwriteCaptions)
            writtenFile = writtenFile or wrote

        return writtenFile


    def processFile(self, srcPath: str, targetFolder: str, targetFileName: str, overwrite: bool) -> str | None:
        destPath = os.path.join(targetFolder, targetFileName)
        if (not overwrite) and os.path.exists(destPath):
            return None

        if not os.path.exists(targetFolder):
            self.log(f"Creating folder: {targetFolder}")
            os.makedirs(targetFolder)

        self.fileDest(srcPath, destPath)
        return destPath

    def processMask(self, imgPath: str, targetFolder: str) -> str | None:
        self.maskPathParser.setup(imgPath)

        # Really necessary?
        # imgReader = QImageReader(imgPath)
        # imgSize = imgReader.size()
        # self.maskPathParser.width = imgSize.width()
        # self.maskPathParser.height = imgSize.height()

        maskSrcPath = self.maskPathParser.parsePath(self.maskPathTemplate, True)
        if os.path.exists(maskSrcPath):
            return self.processFile(maskSrcPath, targetFolder, os.path.basename(maskSrcPath), self.overwriteMasks)
        return None

    def processCaption(self, srcPath: str, targetFolder: str, targetFileName: str, overwrite: bool) -> str | None:
        if os.path.exists(srcPath):
            return self.captionDest(srcPath, targetFolder, targetFileName, overwrite)
        else:
            return None


    def copyFile(self, srcPath: str, destPath: str):
        shutil.copy2(srcPath, destPath)

    def moveFile(self, srcPath: str, destPath: str):
        shutil.move(srcPath, destPath)

    def createSymlink(self, srcPath: str, destPath: str):
        # This will fail if destPath exists
        os.symlink(srcPath, destPath)


    def createArchiveDest(self, archivePath: str):
        import zipfile, tempfile
        fd, tempArchivePath = tempfile.mkstemp(suffix=".zip")
        self.log(f"Creating temporary ZIP archive: {tempArchivePath}")
        tempFile = os.fdopen(fd, 'wb')
        archive = zipfile.ZipFile(tempFile, 'w')
        numFilesAdded = 0

        def archiveFile(srcPath: str, targetFolder: str, targetFileName: str, overwrite: bool) -> str:
            if self.flatFolders:
                arcPath = os.path.basename(srcPath)
            else:
                arcPath = os.path.relpath(srcPath, self.basePath)

            nonlocal numFilesAdded
            numFilesAdded += 1

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
