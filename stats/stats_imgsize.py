from __future__ import annotations
from typing import Iterable
from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QAbstractItemModel, QModelIndex
from lib import colorlib, imagerw, videorw, qtlib
from lib.filelist import FileList, DataKeys
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
        self._layout.col1Layout.insertWidget(0, self._buildOptions())
        self.setLayout(self._layout)

    def _buildOptions(self):
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(8, 2, 8, 3)

        self.chkFrameBuckets = QtWidgets.QCheckBox("Separate videos\nby frame count")
        layout.addWidget(self.chkFrameBuckets)

        self.chkFromCache = QtWidgets.QCheckBox("Load from cache")
        self.chkFromCache.setChecked(True)
        layout.addWidget(self.chkFromCache)

        group = QtWidgets.QGroupBox("Options")
        group.setLayout(layout)
        return group

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
        frameBuckets = self.chkFrameBuckets.isChecked()
        fromCache = self.chkFromCache.isChecked()
        return SizeBucketStatsLoadTask(self.tab.filelist, frameBuckets, fromCache)

    @Slot()
    def _onDataLoaded(self, buckets: list[SizeBucketData], summary: SizeBucketSummary):
        # Show column 2 before resizing below
        if summary.maxFrames != 0:
            self.lblFrames.setText(f"{summary.minFrames} - {summary.maxFrames}")
            self.table.showColumn(2)
        else:
            self.lblFrames.setText(f"0")
            self.table.hideColumn(2)

        self.model.reload(buckets, summary)
        self.table.sortByColumn(4, Qt.SortOrder.AscendingOrder)
        self.table.resizeColumnsToContents()

        self.lblNumFiles.setText(str(summary.numFiles))
        self.lblNumUnreadable.setText(str(summary.numUnreadable))
        self.lblNumBuckets.setText(str(summary.numBuckets))
        self.lblWidth.setText(f"{summary.minWidth} - {summary.maxWidth}")
        self.lblHeight.setText(f"{summary.minHeight} - {summary.maxHeight}")
        self.lblPixels.setText(f"{summary.minPixels:.1f} - {summary.maxPixels:.1f}")

        unreadableStyle = ""
        if summary.numUnreadable > 0:
            unreadableStyle = f"color: {colorlib.RED}"
        self.lblNumUnreadable.setStyleSheet(unreadableStyle)

        self._cacheSizes(summary)

    def _cacheSizes(self, summary: SizeBucketSummary):
        filelist = self.tab.filelist
        for file, (w, h, frames) in summary.cacheSizes.items():
            filelist.setData(file, DataKeys.ImageSize, (w, h))
            if frames > 0:
                filelist.setData(file, DataKeys.VideoFrames, frames)

    def clearData(self):
        self._loadBox.terminateTask()
        self._loadBox.progressBar.reset()
        self._onDataLoaded([], SizeBucketSummary().finalize(0))



class SizeBucketStatsLoadTask(StatsLoadTask):
    def __init__(self, filelist: FileList, frameBuckets: bool, fromCache: bool):
        super().__init__("Media Size", 10)
        self.frameBuckets = frameBuckets

        if fromCache:
            self.remainingFiles = list[str]()
            keys = (DataKeys.ImageSize, DataKeys.VideoFrames)
            self.fileSizes = {
                file: filelist.getMultipleData(file, keys)
                for file in filelist.getFiles()
            }
        else:
            self.remainingFiles = filelist.getFiles().copy()
            self.fileSizes = dict[str, dict]()

    def runLoad(self) -> tuple[list[SizeBucketData], SizeBucketSummary]:
        """Runs in worker thread"""
        summary = SizeBucketSummary()
        buckets: dict[tuple[int, int, int], SizeBucketData] = dict()

        def addFileSize(file: str, size: tuple[int, int, int]):
            summary.addFile(size)

            bucketSize = size if self.frameBuckets else self._normalizeFrames(size)
            bucket = buckets.get(bucketSize)
            if bucket is None:
                buckets[bucketSize] = bucket = SizeBucketData(bucketSize)
            bucket.addFile(file, size[2])

        for file, size in self._cachedSizes(self.remainingFiles):
            addFileSize(file, size)

        for file, size in self.map_auto(self.remainingFiles, self.readSize, chunkSize=16, countOffset=summary.numFiles):
            addFileSize(file, size)
            summary.cacheSizes[file] = size

        summary.finalize(len(buckets))
        return list(buckets.values()), summary

    def _cachedSizes(self, files: list[str]) -> Iterable[tuple[str, tuple[int, int, int]]]:
        for file, data in self.fileSizes.items():
            if videorw.isVideoFile(file):
                if len(data) == 2:
                    yield file, (*data[DataKeys.ImageSize], data[DataKeys.VideoFrames])
                    continue
            elif size := data.get(DataKeys.ImageSize):
                yield file, (*size, 0)
                continue

            files.append(file)

    @staticmethod
    def readSize(file: str) -> tuple[str, tuple[int, int, int]]:
        """Runs in multiple separate processes"""
        if videorw.isVideoFile(file):
            w, h, _, frames, _ = videorw.readMetadata(file)
        else:
            w, h = imagerw.readSize(file)
            frames = 0

        return file, (w, h, frames)

    @staticmethod
    def _normalizeFrames(size: tuple[int, int, int]) -> tuple[int, int, int]:
        """Returns the same size with a frame count of 0 for images and 1 for videos
        so all videos of size WxH are added to the same bucket. Keeps -1 for errors.
        """
        w, h, f = size
        return (w, h, min(f, 1))


class SizeBucketData:
    def __init__(self, size: tuple[int, int, int]):
        self.width, self.height, _ = size
        self.aspectRatio = self.width / self.height
        self.pixels = self.width * self.height / 1000000

        self.minFrames = 2**31
        self.maxFrames = 0

        self.count  = 0
        self.files: set[str] = set()

    def addFile(self, file: str, frames: int):
        self.files.add(file)
        self.count += 1

        self.minFrames = min(self.minFrames, frames)
        self.maxFrames = max(self.maxFrames, frames)

    @property
    def frames(self) -> int | str:
        if self.minFrames == self.maxFrames:
            return self.minFrames or ""
        return f"{self.minFrames} - {self.maxFrames}"


class SizeBucketSummary:
    def __init__(self):
        self.cacheSizes: dict[str, tuple[int, int, int]] = {}
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
        bucketData: SizeBucketData = self.buckets[index.row()]

        match role:
            case Qt.ItemDataRole.DisplayRole:
                match index.column():
                    case 0: return bucketData.width
                    case 1: return bucketData.height
                    case 2: return bucketData.frames
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
                case 0 | 1 : return super().lessThan(right, left) # Reversed
                case 2: return dataRight.minFrames < dataLeft.minFrames
                case 3: return dataRight.aspectRatio < dataLeft.aspectRatio
                case 4: return dataRight.pixels < dataLeft.pixels
                case 5 | 6: return dataRight.count < dataLeft.count

        return super().lessThan(left, right)

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QModelIndex) -> bool:
        index = self.sourceModel().index(sourceRow, 0, sourceParent)
        bucketData: SizeBucketData = self.sourceModel().data(index, SizeBucketModel.ROLE_DATA)
        sizeString = f"{bucketData.width}x{bucketData.height}x{bucketData.minFrames}"
        filter = self.filterRegularExpression()
        return filter.match(sizeString).hasMatch()
