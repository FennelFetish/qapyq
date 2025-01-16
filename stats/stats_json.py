from typing_extensions import override
import json, os
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QAbstractItemModel, QModelIndex
from ui.tab import ImgTab
from .stats_base import StatsLayout, StatsBaseProxyModel


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
        layout = QtWidgets.QFormLayout()
        layout.setHorizontalSpacing(12)

        btnReloadCaptions = QtWidgets.QPushButton("Reload")
        btnReloadCaptions.clicked.connect(self.reload)
        layout.addRow(btnReloadCaptions)

        self.lblNumFiles = QtWidgets.QLabel("0")
        layout.addRow("JSON Files:", self.lblNumFiles)

        self.lblTotalKeys = QtWidgets.QLabel("0")
        layout.addRow("Total Keys:", self.lblTotalKeys)

        self.lblUniqueKeys = QtWidgets.QLabel("0")
        layout.addRow("Unique Keys:", self.lblUniqueKeys)

        self.lblKeysPerFile = QtWidgets.QLabel("0")
        layout.addRow("Per File:", self.lblKeysPerFile)

        self.lblAvgKeysPerImage = QtWidgets.QLabel("0")
        layout.addRow("Average:", self.lblAvgKeysPerImage)

        group = QtWidgets.QGroupBox("Stats")
        group.setLayout(layout)
        return group


    @Slot()
    def reload(self):
        self.model.reload(self.tab.filelist.getFiles())
        self.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self.table.resizeColumnsToContents()

        summary = self.model.summary
        self.lblNumFiles.setText(str(summary.numFiles))
        self.lblTotalKeys.setText(str(summary.totalNumKeys))
        self.lblUniqueKeys.setText(str(summary.uniqueKeys))
        self.lblKeysPerFile.setText(f"{summary.minNumKeys} - {summary.maxNumKeys}")
        self.lblAvgKeysPerImage.setText(f"{summary.getAvgNumKeys():.1f}")

    def clearData(self):
        self.model.clear()



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

    def finalize(self, numUniqueKeys: int):
        self.uniqueKeys = numUniqueKeys
        if self.numFiles == 0:
            self.minNumKeys = 0

    def getAvgNumKeys(self):
        if self.numFiles == 0:
            return 0.0
        return self.totalNumKeys / self.numFiles


class JsonModel(QAbstractItemModel):
    ROLE_KEY  = Qt.ItemDataRole.UserRole.value
    ROLE_DATA = Qt.ItemDataRole.UserRole.value + 1

    def __init__(self):
        super().__init__()
        self.separator = ","
        self.font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)

        self.keys: list[JsonKeyData] = list()
        self.summary = JsonKeySummary()

    def reload(self, files: list[str]):
        self.beginResetModel()

        self.keys.clear()
        self.summary.reset()

        keyData: dict[str, JsonKeyData] = dict()
        for file in files:
            keys = self.loadJsonKeys(file)
            if keys is None:
                continue

            self.summary.addFile(len(keys))
            for key in keys:
                data = keyData.get(key)
                if not data:
                    keyData[key] = data = JsonKeyData(key)
                data.addFile(file)
        
        self.keys.extend(keyData.values())
        self.summary.finalize(len(self.keys))
        self.endResetModel()

    @classmethod
    def loadJsonKeys(cls, path: str) -> list[str] | None:
        path, ext = os.path.splitext(path)
        path = f"{path}.json"
        if not os.path.exists(path):
            return None

        with open(path, 'r') as file:
            data = json.load(file)
        
        keys: list[str] = list()
        if isinstance(data, dict):
            cls.walkJsonData(keys, "", data)
        return keys

    @classmethod
    def walkJsonData(cls, keys: list[str], keyPath: str, data: dict) -> None:
        for k, v in data.items():
            key = f"{keyPath}.{k}" if keyPath else k
            if isinstance(v, dict):
                cls.walkJsonData(keys, key, v)
            else:
                keys.append(key)

    def clear(self):
        self.beginResetModel()
        self.keys.clear()
        self.summary.reset()
        self.summary.finalize(0)
        self.endResetModel()


    # QAbstractItemModel Interface

    def rowCount(self, parent=QModelIndex()):
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
