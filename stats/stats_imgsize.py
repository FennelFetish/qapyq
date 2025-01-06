
from typing_extensions import override
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QAbstractItemModel, QModelIndex
from PySide6.QtGui import QImageReader
from ui.tab import ImgTab
from .stats_base import StatsBaseLayout


class ImageSizeStats(QtWidgets.QWidget):
    def __init__(self, tab: ImgTab):
        super().__init__()
        self.tab = tab

        self.model = SizeBucketModel()
        self.table = QtWidgets.QTableView(self.tab)
        self.table.setModel(self.model)

        self._layout = SizeBucketLayout(tab, self.model, self.table)
        self._layout.addWidget(self._buildStats(), 0, 0)
        self.setLayout(self._layout)


    def _buildStats(self):
        layout = QtWidgets.QFormLayout()
        layout.setHorizontalSpacing(12)

        btnReload = QtWidgets.QPushButton("Reload")
        btnReload.clicked.connect(self.reload)
        layout.addRow(btnReload)

        self.lblNumFiles = QtWidgets.QLabel("0")
        layout.addRow("Images:", self.lblNumFiles)

        self.lblNumBuckets = QtWidgets.QLabel("0")
        layout.addRow("Bucket Count:", self.lblNumBuckets)

        self.lblWidth = QtWidgets.QLabel("0")
        layout.addRow("Width:", self.lblWidth)

        self.lblHeight = QtWidgets.QLabel("0")
        layout.addRow("Height:", self.lblHeight)

        self.lblPixels = QtWidgets.QLabel("0")
        layout.addRow("Megapixels:", self.lblPixels)

        group = QtWidgets.QGroupBox("Stats")
        group.setLayout(layout)
        return group


    @Slot()
    def reload(self):
        self.model.reload(self.tab.filelist.getFiles())
        self.table.sortByColumn(3, Qt.SortOrder.AscendingOrder)
        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(1)
        self.table.resizeColumnToContents(2)
        self.table.resizeColumnToContents(3)

        summary = self.model.summary
        self.lblNumFiles.setText(str(summary.numFiles))
        self.lblNumBuckets.setText(str(summary.numBuckets))
        self.lblWidth.setText(f"{summary.minWidth} - {summary.maxWidth}")
        self.lblHeight.setText(f"{summary.minHeight} - {summary.maxHeight}")
        self.lblPixels.setText(f"{summary.minPixels:.2f} - {summary.maxPixels:.2f}")


class SizeBucketData:
    def __init__(self, size: tuple[int, int]):
        self.pixels = size[0] * size[1] / 1000000
        self.count = 0
        self.files: set[str] = set()

    def addFile(self, file: str):
        self.files.add(file)
        self.count += 1


class SizeBucketSummary:
    def __init__(self):
        self.reset()

    def reset(self):
        self.minWidth  = 2**31
        self.maxWidth  = 0

        self.minHeight = 2**31
        self.maxHeight = 0

        self.minPixels = 2**31
        self.maxPixels = 0

        self.numFiles   = 0
        self.numBuckets = 0

    def addFile(self, size: tuple[int, int]):
        self.minWidth = min(self.minWidth, size[0])
        self.maxWidth = max(self.maxWidth, size[0])

        self.minHeight = min(self.minHeight, size[1])
        self.maxHeight = max(self.maxHeight, size[1])

        pixels = size[0] * size[1] / 1000000
        self.minPixels = min(self.minPixels, pixels)
        self.maxPixels = max(self.maxPixels, pixels)

        self.numFiles += 1


class SizeBucketModel(QAbstractItemModel):
    ROLE_DATA = Qt.ItemDataRole.UserRole.value

    def __init__(self):
        super().__init__()

        self.buckets: dict[tuple[int, int], SizeBucketData] = dict()
        self.bucketOrder: list[tuple[int, int]] = list()
        self.summary = SizeBucketSummary()


    def reload(self, files: list[str]):
        self.beginResetModel()

        self.buckets.clear()
        self.bucketOrder.clear()
        self.summary.reset()

        reader = QImageReader()
        for file in files:
            reader.setFileName(file)
            size = reader.size()
            size = (size.width(), size.height())

            self.summary.addFile(size)
            bucket = self.buckets.get(size)
            if not bucket:
                self.buckets[size] = bucket = SizeBucketData(size)
            bucket.addFile(file)

        self.bucketOrder.extend(bucket for bucket in self.buckets.keys())
        self.endResetModel()

        self.summary.numBuckets = len(self.bucketOrder)


    # QAbstractItemModel Interface

    def rowCount(self, parent=QModelIndex()):
        return len(self.buckets)

    def columnCount(self, parent=QModelIndex()):
        return 5

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        size = self.bucketOrder[index.row()]

        if role == Qt.ItemDataRole.DisplayRole:
            match index.column():
                case 0: return size[0]
                case 1: return size[1]
                case 2: return f"{self.buckets[size].pixels:.2f}"
                case 3: return self.buckets[size].count
                case 4:
                    presence = 0
                    if self.summary.numFiles > 0:
                        presence = len(self.buckets[size].files) / self.summary.numFiles
                    return f"{presence*100:.2f} %"

        elif role == self.ROLE_DATA:
            return self.buckets[size]

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole) -> str | None:
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return super().headerData(section, orientation, role)

        match section:
            case 0: return "Width"
            case 1: return "Height"
            case 2: return "MP"
            case 3: return "Count"
            case 4: return "Percentage"
        return None

    def index(self, row, column, parent=QModelIndex()):
        return self.createIndex(row, column)

    def parent(self, index):
        return QModelIndex()

    def sort(self, column: int, order=Qt.SortOrder.AscendingOrder) -> None:
        defaultOrder = Qt.SortOrder.DescendingOrder
        match column:
            case 0: sortFunc = lambda size: size[0]
            case 1: sortFunc = lambda size: size[1]
            case 2: sortFunc = lambda size: self.buckets[size].pixels
            case 3 | 4: sortFunc = lambda size: self.buckets[size].count

        reversed = (order != defaultOrder)

        self.layoutAboutToBeChanged.emit()
        self.bucketOrder.sort(reverse=reversed, key=sortFunc)
        self.layoutChanged.emit()



class SizeBucketLayout(StatsBaseLayout):
    def __init__(self, tab: ImgTab, model, tableView, row=0):
        super().__init__(tab, "Size Buckets", model, tableView, row)
    
    @override
    def getFiles(self, index: QModelIndex) -> list[str]:
        data = self.model.data(index, SizeBucketModel.ROLE_DATA)
        return data.files
