from __future__ import annotations
from typing_extensions import override
import json, os
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QAbstractItemModel, QModelIndex
import lib.qtlib as qtlib
from ui.tab import ImgTab
from .stats_base import StatsLayout, StatsLoadGroupBox, StatsBaseProxyModel, StatsLoadTask, ExportCsv


class JsonStats(QtWidgets.QWidget):
    def __init__(self, tab: ImgTab):
        super().__init__()
        self.tab = tab

        self.model = JsonModel()
        self.proxyModel = JsonProxyModel()
        self.proxyModel.setSourceModel(self.model)

        self.table = QtWidgets.QTableView()
        self.table.setModel(self.proxyModel)

        self._layout = StatsLayout(tab, "Keys", self.proxyModel, self.table)
        self._layout.setStatsWidget(self._buildStats())
        self.setLayout(self._layout)


    def _buildStats(self):
        loadBox = StatsLoadGroupBox(self._createTask)
        loadBox.dataLoaded.connect(self._onDataLoaded)

        self.lblNumFiles = loadBox.addLabel("JSON Files:")
        self.lblTotalKeys = loadBox.addLabel("Total Keys:")
        self.lblUniqueKeys = loadBox.addLabel("Unique Keys:")
        self.lblKeysPerFile = loadBox.addLabel("Per File:")
        self.lblAvgKeysPerImage = loadBox.addLabel("Average:")

        self._loadBox = loadBox
        return loadBox

    def _createTask(self):
        return JsonStatsLoadTask(self.tab.filelist.getFiles().copy())

    @Slot()
    def _onDataLoaded(self, keys: list[JsonKeyData], summary: JsonKeySummary):
        self.model.reload(keys, summary)
        self.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self.table.resizeColumnsToContents()

        self.lblNumFiles.setText(str(summary.numFiles))
        self.lblTotalKeys.setText(str(summary.totalNumKeys))
        self.lblUniqueKeys.setText(str(summary.uniqueKeys))
        self.lblKeysPerFile.setText(f"{summary.minNumKeys} - {summary.maxNumKeys}")
        self.lblAvgKeysPerImage.setText(f"{summary.getAvgNumKeys():.1f}")

    def clearData(self):
        self._loadBox.terminateTask()
        self._loadBox.progressBar.reset()
        self._onDataLoaded([], JsonKeySummary().finalize(0))



class JsonStatsLoadTask(StatsLoadTask):
    def __init__(self, files: list[str]):
        super().__init__("JSON Keys")
        self.files = files

    def runLoad(self) -> tuple[list[JsonKeyData], JsonKeySummary]:
        summary = JsonKeySummary()

        keyData: dict[str, JsonKeyData] = dict()
        for file, keys in self.map_auto(self.files, self.loadJsonKeys):
            if keys is None:
                continue

            summary.addFile(len(keys))
            for key in keys:
                data = keyData.get(key)
                if not data:
                    keyData[key] = data = JsonKeyData(key)
                data.addFile(file)

        summary.finalize(len(keyData))
        return list(keyData.values()), summary

    @classmethod
    def loadJsonKeys(cls, imgFile: str) -> tuple[str, list[str] | None]:
        jsonFile = os.path.splitext(imgFile)[0] + ".json"
        if not os.path.exists(jsonFile):
            return imgFile, None

        with open(jsonFile, 'r') as file:
            data = json.load(file)

        keys: list[str] = list()
        if isinstance(data, dict):
            cls.walkJsonData(keys, "", data)
        return imgFile, keys

    @classmethod
    def walkJsonData(cls, keys: list[str], keyPath: str, data: dict) -> None:
        for k, v in data.items():
            key = f"{keyPath}.{k}" if keyPath else k
            if isinstance(v, dict):
                cls.walkJsonData(keys, key, v)
            else:
                keys.append(key)



class JsonKeyData:
    def __init__(self, key: str):
        self.key = key
        self.count = 0
        self.files: set[str] = set()

    def addFile(self, file: str):
        self.files.add(file)
        self.count += 1


class JsonKeySummary:
    def __init__(self):
        self.reset()

    def reset(self):
        self.totalNumKeys = 0
        self.minNumKeys = 2**31
        self.maxNumKeys = 0
        self.numFiles   = 0
        self.uniqueKeys = 0

    def addFile(self, numKeys: int):
        self.totalNumKeys += numKeys
        self.minNumKeys = min(self.minNumKeys, numKeys)
        self.maxNumKeys = max(self.maxNumKeys, numKeys)
        self.numFiles += 1

    def finalize(self, numUniqueKeys: int) -> JsonKeySummary:
        self.uniqueKeys = numUniqueKeys
        if self.numFiles == 0:
            self.minNumKeys = 0
        return self

    def getAvgNumKeys(self):
        if self.numFiles == 0:
            return 0.0
        return self.totalNumKeys / self.numFiles


class JsonModel(QAbstractItemModel):
    ROLE_KEY  = Qt.ItemDataRole.UserRole.value
    ROLE_DATA = Qt.ItemDataRole.UserRole.value + 1

    def __init__(self):
        super().__init__()
        self.font = qtlib.getMonospaceFont()

        self.keys: list[JsonKeyData] = list()
        self.summary = JsonKeySummary()

    def reload(self, keys: list[JsonKeyData], summary: JsonKeySummary):
        self.beginResetModel()
        self.keys = keys
        self.summary = summary
        self.endResetModel()


    # QAbstractItemModel Interface

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.keys)

    def columnCount(self, parent=QModelIndex()):
        return 3

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        keyData: JsonKeyData = self.keys[index.row()]

        match role:
            case Qt.ItemDataRole.DisplayRole:
                match index.column():
                    case 0: return keyData.key
                    case 1: return keyData.count
                    case 2:
                        presence = 0
                        if self.summary.numFiles > 0:
                            presence = len(keyData.files) / self.summary.numFiles
                        return f"{presence*100:.2f} %"

            case Qt.ItemDataRole.FontRole: return self.font
            case self.ROLE_KEY:  return keyData.key
            case self.ROLE_DATA: return keyData

            case ExportCsv.ROLE_CSV:
                match index.column():
                    case 0: return keyData.key
                    case 1: return keyData.count
                    case 2: return len(keyData.files) / self.summary.numFiles if self.summary.numFiles else 0.0

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole) -> str | None:
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return super().headerData(section, orientation, role)

        match section:
            case 0: return "Key"
            case 1: return "Count"
            case 2: return "Presence"
        return None

    def index(self, row, column, parent=QModelIndex()):
        return self.createIndex(row, column)

    def parent(self, index):
        return QModelIndex()


class JsonProxyModel(StatsBaseProxyModel):
    def __init__(self):
        super().__init__()
        self.setFilterKeyColumn(0)

    @override
    def getFiles(self, sourceIndex: QModelIndex) -> set[str]:
        data: JsonKeyData = self.sourceModel().data(sourceIndex, JsonModel.ROLE_DATA)
        return data.files

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        column = left.column()
        if column == right.column():
            dataLeft: JsonKeyData  = self.sourceModel().data(left, JsonModel.ROLE_DATA)
            dataRight: JsonKeyData = self.sourceModel().data(right, JsonModel.ROLE_DATA)
            match column:
                case 1: return dataRight.count < dataLeft.count
                case 2: return len(dataRight.files) < len(dataLeft.files)

        return super().lessThan(left, right)
