import os
from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QAbstractItemModel, QModelIndex
from ui.tab import ImgTab
from lib.filelist import FileList
from .stats_base import StatsLayout, StatsBaseProxyModel


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
        layout = QtWidgets.QFormLayout()
        layout.setHorizontalSpacing(12)

        btnReload = QtWidgets.QPushButton("Reload")
        btnReload.clicked.connect(self.reload)
        layout.addRow(btnReload)

        self.lblNumFiles = QtWidgets.QLabel("0")
        layout.addRow("Images:", self.lblNumFiles)

        self.lblNumSuffixes = QtWidgets.QLabel("0")
        layout.addRow("Suffixes:", self.lblNumSuffixes)

        group = QtWidgets.QGroupBox("Stats")
        group.setLayout(layout)
        return group


    @Slot()
    def reload(self):
        self.model.reload(self.tab.filelist)
        self.table.sortByColumn(3, Qt.SortOrder.AscendingOrder)
        self.table.resizeColumnsToContents()

        summary = self.model.summary
        self.lblNumFiles.setText(str(summary.numFiles))
        self.lblNumSuffixes.setText(str(summary.numSuffixes))

    def clearData(self):
        self.model.clear()



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

    def finalize(self, numSuffixes: int):
        self.numSuffixes = numSuffixes



class SuffixModel(QAbstractItemModel):
    ROLE_DATA = Qt.ItemDataRole.UserRole.value

    def __init__(self):
        super().__init__()
        self.font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)

        self.suffixes: list[SuffixData] = list()
        self.summary = SuffixSummary()

    def reload(self, filelist: FileList):
        fileSet = set(filelist.removeCommonRoot(file) for file in filelist.getFiles())

        self.beginResetModel()

        self.suffixes.clear()
        self.summary.reset()
        suffixes: dict[str, SuffixData] = dict()

        for files in self._walkSortedFolders(filelist):
            minSearchIndex = 0
            i = 0
            while i < len(files):
                imgFile = files[i]
                if imgFile not in fileSet:
                    i += 1
                    continue

                i, groupFiles = self._getFileGroup(files, i, minSearchIndex)
                minSearchIndex = i
                numImages = self._trySplitGroup(imgFile, fileSet, groupFiles, filelist.commonRoot, suffixes)
                self.summary.addFiles(numImages)

        self.suffixes.extend(suffixes.values())
        self.summary.finalize(len(self.suffixes))
        self.endResetModel()


    def _walkSortedFolders(self, filelist: FileList):
        folders: set[str] = set()
        for file in filelist.getFiles():
            folders.add(os.path.dirname(file))

        for folder in folders:
            for (root, subdirs, files) in os.walk(folder, topdown=True):
                subdirs.clear() # Do not descend into subdirs
                files.sort()

                root = filelist.removeCommonRoot(root)
                root = "" if root == "." else root + "/"
                files = [f"{root}{f}" for f in files]
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

    def _trySplitGroup(self, imgFile: str, fileSet: set[str], groupFiles: list[str], root: str, suffixes: dict[str, SuffixData]) -> int:
        # Detect and split groups that contain multiple images.
        # This can happen if a filename is contained in another filename, like when images are saved with a counter suffix (img.png / img_001.png).
        # Deduplicate prefixes with a set. Duplicates can appear when images have the same name but different extensions.
        prefixes: set[str] = set()
        prefix = ""
        for file in groupFiles:
            if file in fileSet:
                fileNoExt = os.path.splitext(file)[0]
                prefixes.add(fileNoExt)
                prefix = fileNoExt

        numImages = len(prefixes)
        if numImages < 2:
            # Images with identical filenames but different extension:
            # Only the first one is added (imgFile), but with both suffixes.
            # Using the intersection of multiple extensions will show this file, and the summary's file count will be off.
            self._addToSuffixDict(imgFile, groupFiles, prefix, root, suffixes)
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
                    if file in fileSet:
                        imgFile = file
                    group.append(file)
                    del groupFiles[i]

            self._addToSuffixDict(imgFile, group, prefix, root, suffixes)

        # The remaining files belong to the skipped prefix
        imgFile = ""
        for file in groupFiles:
            if file in fileSet:
                imgFile = file

        self._addToSuffixDict(imgFile, groupFiles, sortedPrefixes[-1], root, suffixes)
        return numImages

    @staticmethod
    def _addToSuffixDict(imgFile: str, files: list[str], prefix: str, root: str, suffixes: dict[str, SuffixData]) -> None:
        for file in files:
            suffix = file[len(prefix):]

            data = suffixes.get(suffix)
            if not data:
                suffixes[suffix] = data = SuffixData(suffix)

            data.addFile(f"{root}/{imgFile}")


    def clear(self):
        self.beginResetModel()
        self.suffixes.clear()
        self.summary.reset()
        self.summary.finalize(0)
        self.endResetModel()


    # QAbstractItemModel Interface

    def rowCount(self, parent=QModelIndex()):
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
