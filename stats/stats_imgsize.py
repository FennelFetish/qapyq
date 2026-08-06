from __future__ import annotations
from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QAbstractItemModel, QModelIndex
from lib import colorlib, imagerw, videorw, qtlib
from ui.tab import ImgTab
from .stats_base import StatsLayout, StatsTableView, StatsLoadGroupBox, StatsBaseProxyModel, StatsLoadTask, ExportCsv


class ImageSizeStats(QtWidgets.QWidget):
    def __init__(self, tab: ImgTab):
        super().__init__()
        self.tab = tab

        self.model = SizeBucketModel()
        self.proxyModel = SizeBucketProxyModel()
        self.proxyModel.setSourceModel(self.model)

        self.table = StatsTableView()
        self.table.setModel(self.proxyModel)

        self._layout = StatsLayout(tab, "Size Buckets", self.proxyModel, self.table)
        self._layout.setStatsWidget(self._buildStats())
        self.setLayout(self._layout)


    def _buildStats(self):
        loadBox = StatsLoadGroupBox(self._createTask)
        loadBox.dataLoaded.connect(self._onDataLoaded)

        self.lblNumFiles = loadBox.addLabel("Files:")
        self.lblNumUnreadable = loadBox.addLabel("Unreadable:")
        self.lblNumBuckets = loadBox.addLabel("Size Buckets:")
        self.lblWidth = loadBox.addLabel("Width:")
        self.lblHeight = loadBox.addLabel("Height:")
        self.lblFrames = loadBox.addLabel("Frames:")
        self.lblPixels = loadBox.addLabel("Mpx:")

        self._loadBox = loadBox
        return loadBox

    def _createTask(self):
        return SizeBucketStatsLoadTask(self.tab.filelist.getFiles().copy())

    @Slot()
    def _onDataLoaded(self, buckets: list[SizeBucketData], summary: SizeBucketSummary):
        self.model.reload(buckets, summary)
        self.table.sortByColumn(4, Qt.SortOrder.AscendingOrder)
        self.table.resizeColumnsToContents()

        self.lblNumFiles.setText(str(summary.numFiles))
        self.lblNumUnreadable.setText(str(summary.numUnreadable))
        self.lblNumBuckets.setText(str(summary.numBuckets))
        self.lblWidth.setText(f"{summary.minWidth} - {summary.maxWidth}")
        self.lblHeight.setText(f"{summary.minHeight} - {summary.maxHeight}")
        self.lblPixels.setText(f"{summary.minPixels:.1f} - {summary.maxPixels:.1f}")

        if summary.maxFrames != 0:
            self.lblFrames.setText(f"{summary.minFrames} - {summary.maxFrames}")
            self.table.showColumn(2)
        else:
            self.lblFrames.setText(f"0")
            self.table.hideColumn(2)

        unreadableStyle = ""
        if summary.numUnreadable > 0:
            unreadableStyle = f"color: {colorlib.RED}"
        self.lblNumUnreadable.setStyleSheet(unreadableStyle)

    def clearData(self):
        self._loadBox.terminateTask()
        self._loadBox.progressBar.reset()
        self._onDataLoaded([], SizeBucketSummary().finalize(0))



class SizeBucketStatsLoadTask(StatsLoadTask):
    def __init__(self, files: list[str]):
        super().__init__("Image Size", 10)
        self.files = files

    def runLoad(self) -> tuple[list[SizeBucketData], SizeBucketSummary]:
        summary = SizeBucketSummary()
        buckets: dict[tuple[int, int, int], SizeBucketData] = dict()

        for file, size in self.map_auto(self.files, self.readSize, chunkSize=32):
            summary.addFile(size)
            bucket = buckets.get(size)
            if not bucket:
                buckets[size] = bucket = SizeBucketData(size)
            bucket.addFile(file)

        summary.finalize(len(buckets))
        return list(buckets.values()), summary

    @staticmethod
    def readSize(file: str) -> tuple[str, tuple[int, int, int]]:
        if videorw.isVideoFile(file):
            w, h, _, frames, _ = videorw.readMetadata(file)
        else:
            w, h = imagerw.readSize(file)
            frames = 0

        return file, (w, h, frames)



class SizeBucketData:
    def __init__(self, size: tuple[int, int, int]):
        self.width, self.height, self.frames = size
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
        defaultMin = 2**31

        self.minWidth  = defaultMin
        self.maxWidth  = 0

        self.minHeight = defaultMin
        self.maxHeight = 0

        self.minFrames = defaultMin
        self.maxFrames = 0

        self.minPixels = defaultMin
        self.maxPixels = 0

        self.numFiles   = 0
        self.numBuckets = 0
        self.numUnreadable = 0

        self._empty = True

    def addFile(self, size: tuple[int, int, int]):
        self.numFiles += 1
        w, h, frames = size

        if w < 0 or h < 0:
            self.numUnreadable += 1
            return

        self._empty = False

        self.minWidth = min(self.minWidth, w)
        self.maxWidth = max(self.maxWidth, w)

        self.minHeight = min(self.minHeight, h)
        self.maxHeight = max(self.maxHeight, h)

        self.minFrames = min(self.minFrames, frames)
        self.maxFrames = max(self.maxFrames, frames)

        pixels = w * h / 1000000
        self.minPixels = min(self.minPixels, pixels)
        self.maxPixels = max(self.maxPixels, pixels)

    def finalize(self, numBuckets: int) -> SizeBucketSummary:
        self.numBuckets = numBuckets
        if self._empty:
            self.minWidth  = 0
            self.minHeight = 0
            self.minFrames = 0
            self.minPixels = 0

        return self


class SizeBucketModel(QAbstractItemModel):
    ROLE_DATA = Qt.ItemDataRole.UserRole.value

    def __init__(self):
        super().__init__()
        self.font = qtlib.getMonospaceFont()
        self.colorRed = QtGui.QColor(colorlib.RED)

        self.buckets: list[SizeBucketData] = list()
        self.summary = SizeBucketSummary()

    def reload(self, buckets: list[SizeBucketData], summary: SizeBucketSummary):
        self.beginResetModel()
        self.buckets = buckets
        self.summary = summary
        self.endResetModel()


    # QAbstractItemModel Interface

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.buckets)

    def columnCount(self, parent=QModelIndex()):
        return 7

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        bucketData = self.buckets[index.row()]

        match role:
            case Qt.ItemDataRole.DisplayRole:
                match index.column():
                    case 0: return bucketData.width
                    case 1: return bucketData.height
                    case 2: return bucketData.frames or ""
                    case 3: return f"{bucketData.aspectRatio:.3f}"
                    case 4: return f"{bucketData.pixels:.2f}"
                    case 5: return bucketData.count
                    case 6:
                        presence = 0
                        if self.summary.numFiles > 0:
                            presence = len(bucketData.files) / self.summary.numFiles
                        return f"{presence*100:.2f} %"

            case Qt.ItemDataRole.ForegroundRole:
                if bucketData.width < 0 or bucketData.height < 0:
                    return self.colorRed

            case Qt.ItemDataRole.FontRole: return self.font
            case self.ROLE_DATA: return bucketData

            case ExportCsv.ROLE_CSV:
                match index.column():
                    case 0: return bucketData.width
                    case 1: return bucketData.height
                    case 2: return bucketData.frames
                    case 3: return bucketData.aspectRatio
                    case 4: return bucketData.pixels
                    case 5: return bucketData.count
                    case 6: return len(bucketData.files) / self.summary.numFiles if self.summary.numFiles else 0.0

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole) -> str | None:
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return super().headerData(section, orientation, role)

        match section:
            case 0: return "Width"
            case 1: return "Height"
            case 2: return "Frames"
            case 3: return "Aspect"
            case 4: return "Mpx"
            case 5: return "Count"
            case 6: return "Percentage"
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
                case 0 | 1 | 2: return super().lessThan(right, left) # Reversed
                case 3: return dataRight.aspectRatio < dataLeft.aspectRatio
                case 4: return dataRight.pixels < dataLeft.pixels
                case 5 | 6: return dataRight.count < dataLeft.count

        return super().lessThan(left, right)

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QModelIndex) -> bool:
        index = self.sourceModel().index(sourceRow, 0, sourceParent)
        bucketData: SizeBucketData = self.sourceModel().data(index, SizeBucketModel.ROLE_DATA)
        sizeString = f"{bucketData.width}x{bucketData.height}x{bucketData.frames}"
        filter = self.filterRegularExpression()
        return filter.match(sizeString).hasMatch()
