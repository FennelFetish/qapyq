from __future__ import annotations
import os
from typing_extensions import override
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QAbstractItemModel, QModelIndex
from lib.filelist import sortKey, removeCommonRoot
from ui.tab import ImgTab
import lib.qtlib as qtlib
from .stats_base import StatsLayout, StatsLoadGroupBox, StatsBaseProxyModel, StatsLoadTask, ExportCsv


# TODO: export folders as concepts in onetrainer config


class FolderStats(QtWidgets.QWidget):
    def __init__(self, tab: ImgTab):
        super().__init__()
        self.tab = tab

        self.model = FolderModel()
        self.proxyModel = FolderProxyModel()
        self.proxyModel.setSourceModel(self.model)

        self.tree = QtWidgets.QTreeView()
        self.tree.setUniformRowHeights(True)
        self.tree.setModel(self.proxyModel)
        self.tree.setSortingEnabled(True)
        self.tree.expanded.connect(self._adjustFolderColumns)

        self._layout = StatsLayout(tab, "Folders", self.proxyModel, self.tree)
        self._layout.setStatsWidget(self._buildStats())
        self.setLayout(self._layout)


    def _buildStats(self):
        loadBox = StatsLoadGroupBox(self._createTask)
        loadBox.dataLoaded.connect(self._onDataLoaded)

        self.lblNumFiles = loadBox.addLabel("Total Files:")
        self.lblNumFolders = loadBox.addLabel("Folders:")
        self.lblFolderSize = loadBox.addLabel("Folder Size:")
        self.lblAvgFolderSize = loadBox.addLabel("Average Size:")

        self._loadBox = loadBox
        return loadBox

    def _createTask(self):
        filelist = self.tab.filelist
        return FolderStatsLoadTask(filelist.getFiles().copy(), filelist.commonRoot)

    @Slot()
    def _onDataLoaded(self, rootFolder: FolderData, summary: FolderSummary):
        self.model.reload(rootFolder, summary)
        self.tree.expandToDepth(0)
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self._adjustFolderColumns()

        self.lblNumFiles.setText(str(summary.numFiles))
        self.lblNumFolders.setText(str(summary.numFolders))
        self.lblFolderSize.setText(f"{summary.minFolderSize} - {summary.maxFolderSize}")
        self.lblAvgFolderSize.setText(f"{summary.avgFolderSize:.1f}")

    def clearData(self):
        self._loadBox.terminateTask()
        self._loadBox.progressBar.reset()
        self._onDataLoaded(None, FolderSummary().finalize())

    @Slot()
    def _adjustFolderColumns(self):
        for col in range(self.model.columnCount(QModelIndex())):
            self.tree.resizeColumnToContents(col)

        colWidth = self.tree.columnWidth(0) + 20
        self.tree.setColumnWidth(0, colWidth)



class FolderStatsLoadTask(StatsLoadTask):
    def __init__(self, files: list[str], commonRoot: str):
        super().__init__("Folders")
        self.files = files
        self.commonRoot = commonRoot

    def runLoad(self) -> tuple[FolderData, FolderSummary]:
        summary = FolderSummary()

        rootName = os.path.basename(self.commonRoot) if self.commonRoot else "/"
        self.rootFolder = FolderData(self.commonRoot, rootName)
        self.rootFolder.indexInParent = 0

        folders: dict[str, FolderData] = dict()
        folders[""] = self.rootFolder

        for file in self.iterate(self.files):
            relFile = removeCommonRoot(file, self.commonRoot)
            folderPath = os.path.dirname(relFile)
            folderData = self._getFolderData(folders, folderPath)
            folderData.addFile(file)

        for folder in folders.values():
            summary.addFolder(folder)
        summary.finalize()

        self.rootFolder.updateTree(summary.numFiles, summary.avgFolderSize)
        return self.rootFolder, summary

    def _getFolderData(self, folders: dict[str, FolderData], folderPath: str) -> FolderData:
        if folderData := folders.get(folderPath):
            return folderData

        entryName = os.path.basename(folderPath)
        folderData = FolderData(folderPath, entryName)
        folders[folderPath] = folderData

        parentFolderData = self._getParentFolderData(folders, folderPath)
        parentFolderData.addSubfolder(folderData)

        return folderData

    def _getParentFolderData(self, folders: dict[str, FolderData], folderPath: str) -> FolderData:
        parentPath = os.path.dirname(folderPath)

        # Check if toplevel
        if os.path.dirname(parentPath) == parentPath:
            return self.rootFolder

        return self._getFolderData(folders, parentPath)



class FolderData:
    def __init__(self, path: str, name: str):
        self.path = path
        self.name = name
        self.sortName = sortKey(name)
        self.files: set[str] = set()

        self.parent: FolderData | None = None
        self.subfolders: list[FolderData] = list()
        self.indexInParent = -1

        # Based on count of files including subfolders
        self.numFilesTotal   = 0
        self.percentOfParent = 1.0
        self.percentOfTotal  = 1.0
        self.repeats         = 1.0

        # Based only on count of files directly inside folder
        self.selfPercentOfParent = 1.0
        self.selfPercentOfTotal  = 1.0
        self.selfRepeats         = 1.0

    def addFile(self, file: str):
        self.files.add(file)

    def addSubfolder(self, folder: FolderData):
        folder.parent = self
        self.subfolders.append(folder)

    def getSubfolder(self, row: int) -> FolderData:
        return self.subfolders[row]

    def updateTree(self, totalFiles: int, avgFiles: float) -> int:
        self.numFilesTotal = len(self.files)
        for i, subfolder in enumerate(self.subfolders):
            self.numFilesTotal += subfolder.updateTree(totalFiles, avgFiles)
            subfolder.indexInParent = i

        if self.numFilesTotal <= 0:
            return 0

        for subfolder in self.subfolders:
            subfolder.percentOfParent = subfolder.numFilesTotal / self.numFilesTotal
            subfolder.selfPercentOfParent = len(subfolder.files) / self.numFilesTotal

        self.percentOfTotal = self.numFilesTotal / totalFiles
        self.selfPercentOfTotal = len(self.files) / totalFiles

        self.repeats = avgFiles / self.numFilesTotal
        self.selfRepeats = avgFiles / len(self.files) if self.files else 0.0

        return self.numFilesTotal


class FolderSummary:
    def __init__(self):
        self.reset()

    def reset(self):
        self.numFolders = 0
        self.numFiles   = 0

        self.minFolderSize = 2**31
        self.maxFolderSize = 0
        self.avgFolderSize = 0

    def addFolder(self, folder: FolderData):
        numFolderFiles = len(folder.files)

        # Only count folders with content
        if numFolderFiles < 1:
            return

        self.numFolders += 1
        self.numFiles += numFolderFiles

        self.minFolderSize = min(self.minFolderSize, numFolderFiles)
        self.maxFolderSize = max(self.maxFolderSize, numFolderFiles)

    def finalize(self) -> FolderSummary:
        if self.numFolders == 0:
            self.minFolderSize = 0
            self.avgFolderSize = 0
        else:
            self.avgFolderSize = self.numFiles / self.numFolders

        return self


class FolderModel(QAbstractItemModel):
    ROLE_DATA = Qt.ItemDataRole.UserRole.value

    def __init__(self):
        super().__init__()
        self.font = qtlib.getMonospaceFont()

        self.rootFolder: FolderData | None = None
        self.summary = FolderSummary()

    def reload(self, rootFolder: FolderData | None, summary: FolderSummary):
        self.beginResetModel()
        self.rootFolder = rootFolder
        self.summary = summary
        self.endResetModel()


    # QAbstractItemModel Interface

    def rowCount(self, parentIndex=QModelIndex()):
        if parentIndex.column() > 0:
            return 0

        # Root's parent has invalid index
        if not parentIndex.isValid():
            return 1 if self.rootFolder else 0

        parent: FolderData = parentIndex.internalPointer()
        return len(parent.subfolders)

    def columnCount(self, parent=QModelIndex()):
        return 5

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole) -> str | None:
        match role:
            case Qt.ItemDataRole.DisplayRole:
                match section:
                    case 0: return "Folder"
                    case 1: return "Images"
                    case 2: return "% of Parent"
                    case 3: return "% of Total"
                    case 4: return "Repeats"

            case Qt.ItemDataRole.ToolTipRole:
                match section:
                    case 1: return "Total image count inside folder and subfolders.\n(In parantheses): Images directly inside folder, without subfolders."
                    case 2: return "Percentage of parent folder.\n(In parantheses): Percentage of own images without subfolders."
                    case 3: return "Percentage of total.\n(In parantheses): Percentage of own images without subfolders."
                    case 4: return "Estimate for balancing concepts. Average folder size divided by image count in folder and subfolders.\n(In parantheses): Average folder size divided by image count without subfolders."

        return super().headerData(section, orientation, role)


    def index(self, row, column, parentIndex=QModelIndex()) -> QModelIndex:
        if not self.rootFolder:
            return QModelIndex()

        # Root's parent has invalid index
        if not parentIndex.isValid():
            return self.createIndex(0, column, self.rootFolder)

        parent: FolderData = parentIndex.internalPointer()
        if folder := parent.getSubfolder(row):
            return self.createIndex(row, column, folder)
        return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid() or not self.rootFolder:
            return QModelIndex()

        folder: FolderData = index.internalPointer()
        if parent := folder.parent:
            # For root: indexInParent is set to 0
            return self.createIndex(parent.indexInParent, 0, parent)

        # Root's parent has invalid index
        return QModelIndex()


    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        folder: FolderData = index.internalPointer()

        match role:
            case Qt.ItemDataRole.DisplayRole:
                match index.column():
                    case 0:
                        return folder.name

                    case 1: # Images
                        if folder.subfolders and folder.files:
                            return f"{folder.numFilesTotal} ({len(folder.files)})"
                        return f"{folder.numFilesTotal}"

                    case 2: # % of Parent
                        if folder.subfolders and folder.files:
                            return f"{100*folder.percentOfParent:.1f}% ({100*folder.selfPercentOfParent:.1f}%)"
                        return f"{100*folder.percentOfParent:.1f}%"

                    case 3: # % of Total
                        if folder.subfolders and folder.files:
                            return f"{100*folder.percentOfTotal:.1f}% ({100*folder.selfPercentOfTotal:.1f}%)"
                        return f"{100*folder.percentOfTotal:.1f}%"

                    case 4: # Repeats
                        if folder.subfolders and folder.files:
                            return f"{folder.repeats:.2f} ({folder.selfRepeats:.2f})"
                        return f"{folder.repeats:.2f}"

            case Qt.ItemDataRole.FontRole: return self.font
            case self.ROLE_DATA: return folder

            case ExportCsv.ROLE_CSV:
                match index.column():
                    case 0: return folder.path
                    case 1: return folder.numFilesTotal
                    case 2: return folder.percentOfParent
                    case 3: return folder.percentOfTotal
                    case 4: return folder.repeats

        return None



class FolderProxyModel(StatsBaseProxyModel):
    def __init__(self):
        super().__init__()
        self.setFilterKeyColumn(0)
        self.setRecursiveFilteringEnabled(True)

    @override
    def getFiles(self, sourceIndex: QModelIndex) -> set[str]:
        data: FolderData = self.sourceModel().data(sourceIndex, FolderModel.ROLE_DATA)
        return data.files

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        column = left.column()
        if column == right.column():
            dataLeft: FolderData  = self.sourceModel().data(left, FolderModel.ROLE_DATA)
            dataRight: FolderData = self.sourceModel().data(right, FolderModel.ROLE_DATA)
            match column:
                case 0:
                    return dataLeft.sortName < dataRight.sortName
                case 1 | 2 | 3:
                    return dataLeft.numFilesTotal > dataRight.numFilesTotal
                case 4:
                    return dataLeft.numFilesTotal < dataRight.numFilesTotal

        return super().lessThan(left, right)

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QModelIndex) -> bool:
        parentFolder: FolderData|None = sourceParent.internalPointer()
        if not parentFolder:
            return True # Always show root node

        folder = parentFolder.getSubfolder(sourceRow)
        filter = self.filterRegularExpression()
        return filter.match(folder.name).hasMatch()
