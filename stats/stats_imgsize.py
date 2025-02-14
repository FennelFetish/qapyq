from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QAbstractItemModel, QModelIndex
from PySide6.QtGui import QImageReader
from ui.tab import ImgTab
from .stats_base import StatsLayout, StatsBaseProxyModel, ExportCsv


class ImageSizeStats(QtWidgets.QWidget):
    def __init__(self, tab: ImgTab):
        super().__init__()
        self.tab = tab

        self.model = SizeBucketModel()
        self.proxyModel = SizeBucketProxyModel()
        self.proxyModel.setSourceModel(self.model)

        self.table = QtWidgets.QTableView()
        self.table.setModel(self.proxyModel)

        self._layout = StatsLayout(tab, "Size Buckets", self.proxyModel, self.table)
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

        self.lblNumBuckets = QtWidgets.QLabel("0")
        layout.addRow("Size Buckets:", self.lblNumBuckets)

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
        self.table.resizeColumnsToContents()

        summary = self.model.summary
        self.lblNumFiles.setText(str(summary.numFiles))
        self.lblNumBuckets.setText(str(summary.numBuckets))
        self.lblWidth.setText(f"{summary.minWidth} - {summary.maxWidth}")
        self.lblHeight.setText(f"{summary.minHeight} - {summary.maxHeight}")
        self.lblPixels.setText(f"{summary.minPixels:.2f} - {summary.maxPixels:.2f}")

    def clearData(self):
        self.model.clear()



class SizeBucketData:
    def __init__(self, size: tuple[int, int]):
        self.width  = size[0]
        self.height = size[1]
        self.aspectRatio = self.width / self.height

        self.pixels = self.width * self.height / 1000000
        self.count  = 0
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

    def finalize(self, numBuckets: int):
        self.numBuckets = numBuckets
        if self.numFiles == 0:
            self.minWidth  = 0
            self.minHeight = 0
            self.minPixels = 0


class SizeBucketModel(QAbstractItemModel):
    ROLE_DATA = Qt.ItemDataRole.UserRole.value

    def __init__(self):
        super().__init__()
        self.font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)

        self.buckets: list[SizeBucketData] = list()
        self.summary = SizeBucketSummary()

    def reload(self, files: list[str]):
        self.beginResetModel()

        self.buckets.clear()
        self.summary.reset()
        buckets: dict[tuple[int, int], SizeBucketData] = dict()

        reader = QImageReader()
        for file in files:
            reader.setFileName(file)
            size = reader.size()
            size = (size.width(), size.height())

            self.summary.addFile(size)
            bucket = buckets.get(size)
            if not bucket:
                buckets[size] = bucket = SizeBucketData(size)
            bucket.addFile(file)

        self.buckets.extend(buckets.values())
        self.summary.finalize(len(self.buckets))
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self.buckets.clear()
        self.summary.reset()
        self.summary.finalize(0)
        self.endResetModel()


    # QAbstractItemModel Interface

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.buckets)

    def columnCount(self, parent=QModelIndex()):
        return 6

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        bucketData = self.buckets[index.row()]

        match role:
            case Qt.ItemDataRole.DisplayRole:
                match index.column():
                    case 0: return bucketData.width
                    case 1: return bucketData.height
                    case 2: return f"{bucketData.aspectRatio:.3f}"
                    case 3: return f"{bucketData.pixels:.2f}"
                    case 4: return bucketData.count
                    case 5:
                        presence = 0
                        if self.summary.numFiles > 0:
                            presence = len(bucketData.files) / self.summary.numFiles
                        return f"{presence*100:.2f} %"

            case Qt.ItemDataRole.FontRole: return self.font
            case self.ROLE_DATA: return bucketData

            case ExportCsv.ROLE_CSV:
                match index.column():
                    case 0: return bucketData.width
                    case 1: return bucketData.height
                    case 2: return bucketData.aspectRatio
                    case 3: return bucketData.pixels
                    case 4: return bucketData.count
                    case 5: return len(bucketData.files) / self.summary.numFiles if self.summary.numFiles else 0.0

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole) -> str | None:
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return super().headerData(section, orientation, role)

        match section:
            case 0: return "Width"
            case 1: return "Height"
            case 2: return "Aspect"
            case 3: return "Mpx"
            case 4: return "Count"
            case 5: return "Percentage"
        return None

    def index(self, row, column, parent=QModelIndex()):
        return self.createIndex(row, column)

    def parent(self, index):
        return QModelIndex()


class SizeBucketProxyModel(StatsBaseProxyModel):
    def __init__(self):
        super().__init__()

    @override
    def getFiles(self, sourceIndex: QModelIndex) -> set[str]:
        data: SizeBucketData = self.sourceModel().data(sourceIndex, SizeBucketModel.ROLE_DATA)
        return data.files

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        column = left.column()
        if column == right.column():
            dataLeft: SizeBucketData  = self.sourceModel().data(left, SizeBucketModel.ROLE_DATA)
            dataRight: SizeBucketData = self.sourceModel().data(right, SizeBucketModel.ROLE_DATA)
            match column:
                case 0 | 1 | 4: return super().lessThan(right, left) # Reversed
                case 2: return dataRight.aspectRatio < dataLeft.aspectRatio
                case 3: return dataRight.pixels < dataLeft.pixels
                case 5: return dataRight.count < dataLeft.count

        return super().lessThan(left, right)

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QModelIndex) -> bool:
        index = self.sourceModel().index(sourceRow, 0, sourceParent)
        bucketData: SizeBucketData = self.sourceModel().data(index, SizeBucketModel.ROLE_DATA)
        sizeString = f"{bucketData.width}x{bucketData.height}"
        filter = self.filterRegularExpression()
        return filter.match(sizeString).hasMatch()
