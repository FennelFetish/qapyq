from __future__ import annotations
import os, time
from typing import Generator
from typing_extensions import override
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QAbstractItemModel, QModelIndex
from ui.tab import ImgTab
import lib.qtlib as qtlib
from lib.filelist import removeCommonRoot
from .stats_base import StatsLayout, StatsLoadGroupBox, StatsBaseProxyModel, StatsLoadTask, ExportCsv


class FileSuffixStats(QtWidgets.QWidget):
    def __init__(self, tab: ImgTab):
        super().__init__()
        self.tab = tab

        self.model = SuffixModel()
        self.proxyModel = SuffixProxyModel()
        self.proxyModel.setSourceModel(self.model)

        self.table = QtWidgets.QTableView()
        self.table.setModel(self.proxyModel)

        self._layout = StatsLayout(tab, "Suffixes", self.proxyModel, self.table)
        self._layout.setStatsWidget(self._buildStats())
        self.setLayout(self._layout)


    def _buildStats(self):
        loadBox = StatsLoadGroupBox(self._createTask)
        loadBox.dataLoaded.connect(self._onDataLoaded)

        self.lblNumFiles = loadBox.addLabel("Images:")
        self.lblNumSuffixes = loadBox.addLabel("Suffixes:")

        self._loadBox = loadBox
        return loadBox

    def _createTask(self):
        filelist = self.tab.filelist
        return SuffixStatsLoadTask(filelist.getFiles().copy(), filelist.commonRoot)

    @Slot()
    def _onDataLoaded(self, suffixes: list[SuffixData], summary: SuffixSummary):
        self.model.reload(suffixes, summary)
        self.table.sortByColumn(3, Qt.SortOrder.AscendingOrder)
        self.table.resizeColumnsToContents()

        self.lblNumFiles.setText(str(summary.numFiles))
        self.lblNumSuffixes.setText(str(summary.numSuffixes))

    def clearData(self):
        self._loadBox.terminateTask()
        self._loadBox.progressBar.reset()
        self._onDataLoaded([], SuffixSummary().finalize(0))



class SuffixStatsLoadTask(StatsLoadTask):
    def __init__(self, files: list[str], commonRoot: str):
        super().__init__("File Suffix")
        self.files = files
        self.commonRoot = commonRoot


    def runLoad(self) -> tuple[list[SuffixData], SuffixSummary]:
        summary = SuffixSummary()

        self.suffixes: dict[str, SuffixData] = dict()
        self.fileSet = set(removeCommonRoot(file, self.commonRoot) for file in self.files)
        count = len(self.fileSet)

        self.signals.progress.emit(0, count)
        tStart = time.monotonic_ns()
        fileNr = self._process(summary)
        tDiff = (time.monotonic_ns() - tStart) / 1_000_000
        print(f"Stats {self.name}: Read {fileNr}/{count} items in {tDiff:.2f} ms")
        self.signals.progress.emit(fileNr, count)

        summary.finalize(len(self.suffixes))
        return list(self.suffixes.values()), summary

    def _process(self, summary: SuffixSummary):
        fileNr = 0

        for folderFiles in self._walkSortedFolders():
            minSearchIndex = 0
            i = 0
            while i < len(folderFiles):
                if self.isAborted():
                    return fileNr

                imgFile = folderFiles[i]
                if imgFile not in self.fileSet:
                    i += 1
                    continue

                i, groupFiles = self._getFileGroup(folderFiles, i, minSearchIndex)
                minSearchIndex = i
                numImages = self._trySplitGroup(imgFile, groupFiles)
                summary.addFiles(numImages)

                fileNr += numImages
                self.notifyProgress(fileNr, len(self.fileSet))

        return fileNr

    def _walkSortedFolders(self) -> Generator[list[str]]:
        folders: set[str] = set(os.path.dirname(file) for file in self.files)
        for folder in folders:
            for (root, subdirs, files) in os.walk(folder, topdown=True):
                subdirs.clear() # Do not descend into subdirs

                root = os.path.normpath(root)
                root = removeCommonRoot(root, self.commonRoot, allowEmpty=True)

                files.sort()
                files = [os.path.join(root, f) for f in files]
                yield files

    def _getFileGroup(self, files: list[str], index: int, minSearchIndex: int) -> tuple[int, list[str]]:
        file = files[index]
        groupFiles = [file]
        fileNoExt = os.path.splitext(file)[0]

        # Search first file with same prefix
        i = index-1
        while i>=minSearchIndex and files[i].startswith(fileNoExt):
            groupFiles.append(files[i])
            i -= 1

        # Search last file with same prefix
        i = index+1
        while i<len(files) and files[i].startswith(fileNoExt):
            groupFiles.append(files[i])
            i += 1

        return i, groupFiles

    def _trySplitGroup(self, imgFile: str, groupFiles: list[str]) -> int:
        # Detect and split groups that contain multiple images.
        # This can happen if a filename is contained in another filename, like when images are saved with a counter suffix (img.png / img_001.png).
        # Deduplicate prefixes with a set. Duplicates can appear when images have the same name but different extensions.
        prefixes: set[str] = set()
        prefix = ""
        for file in groupFiles:
            if file in self.fileSet:
                fileNoExt = os.path.splitext(file)[0]
                prefixes.add(fileNoExt)
                prefix = fileNoExt

        numImages = len(prefixes)
        if numImages < 2:
            # Images with identical filenames but different extension:
            # Only the first one is added (imgFile), but with both suffixes.
            # Using the intersection of multiple extensions will show this file, and the summary's file count will be off.
            self._addToSuffixDict(imgFile, groupFiles, prefix)
            return numImages

        # Sort by prefix length, longest first.
        sortedPrefixes = sorted(prefixes, key=lambda prefix: len(prefix), reverse=True)
        for prefix in sortedPrefixes[:-1]: # Skip last element
            group: list[str] = list()
            imgFile = ""

            # Move elements of 'groupFiles' to new list for current prefix
            for i in range(len(groupFiles)-1, -1, -1):
                file = groupFiles[i]
                if file.startswith(prefix):
                    if file in self.fileSet:
                        imgFile = file
                    group.append(file)
                    del groupFiles[i]

            self._addToSuffixDict(imgFile, group, prefix)

        # The remaining files belong to the skipped prefix
        imgFile = ""
        for file in groupFiles:
            if file in self.fileSet:
                imgFile = file

        self._addToSuffixDict(imgFile, groupFiles, sortedPrefixes[-1])
        return numImages

    def _addToSuffixDict(self, imgFile: str, files: list[str], prefix: str) -> None:
        for file in files:
            suffix = file[len(prefix):]

            data = self.suffixes.get(suffix)
            if not data:
                self.suffixes[suffix] = data = SuffixData(suffix)

            data.addFile(os.path.join(self.commonRoot, imgFile))



class SuffixData:
    def __init__(self, suffix: str):
        self.suffix = suffix
        self.count  = 0
        self.files: set[str] = set()

    def addFile(self, file: str):
        self.files.add(file)
        self.count += 1


class SuffixSummary:
    def __init__(self):
        self.reset()

    def reset(self):
        self.numFiles   = 0
        self.numSuffixes = 0

    def addFiles(self, count: int):
        self.numFiles += count

    def finalize(self, numSuffixes: int) -> SuffixSummary:
        self.numSuffixes = numSuffixes
        return self



class SuffixModel(QAbstractItemModel):
    ROLE_DATA = Qt.ItemDataRole.UserRole.value

    def __init__(self):
        super().__init__()
        self.font = qtlib.getMonospaceFont()

        self.suffixes: list[SuffixData] = list()
        self.summary = SuffixSummary()

    def reload(self, suffixes: list[SuffixData], summary: SuffixSummary):
        self.beginResetModel()
        self.suffixes = suffixes
        self.summary = summary
        self.endResetModel()


    # QAbstractItemModel Interface

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.suffixes)

    def columnCount(self, parent=QModelIndex()):
        return 3

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        data = self.suffixes[index.row()]

        match role:
            case Qt.ItemDataRole.DisplayRole:
                match index.column():
                    case 0: return data.suffix
                    case 1: return data.count
                    case 2:
                        presence = 0
                        if self.summary.numFiles > 0:
                            presence = len(data.files) / self.summary.numFiles
                        return f"{presence*100:.2f} %"

            case Qt.ItemDataRole.FontRole: return self.font
            case self.ROLE_DATA: return data

            case ExportCsv.ROLE_CSV:
                match index.column():
                    case 0: return data.suffix
                    case 1: return data.count
                    case 2: return len(data.files) / self.summary.numFiles if self.summary.numFiles else 0.0

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole) -> str | None:
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return super().headerData(section, orientation, role)

        match section:
            case 0: return "Suffix"
            case 1: return "Count"
            case 2: return "Presence"
        return None

    def index(self, row, column, parent=QModelIndex()):
        return self.createIndex(row, column)

    def parent(self, index):
        return QModelIndex()



class SuffixProxyModel(StatsBaseProxyModel):
    def __init__(self):
        super().__init__()
        self.setFilterKeyColumn(0)

    @override
    def getFiles(self, sourceIndex: QModelIndex) -> set[str]:
        data: SuffixData = self.sourceModel().data(sourceIndex, SuffixModel.ROLE_DATA)
        return data.files

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        column = left.column()
        if column == right.column():
            dataLeft: SuffixData  = self.sourceModel().data(left, SuffixModel.ROLE_DATA)
            dataRight: SuffixData = self.sourceModel().data(right, SuffixModel.ROLE_DATA)
            match column:
                case 1: return dataRight.count < dataLeft.count
                case 2: return len(dataRight.files) < len(dataLeft.files)

        return super().lessThan(left, right)
