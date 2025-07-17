from __future__ import annotations
import os
from enum import Enum
from typing import Generator
from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QAbstractItemModel, QModelIndex
import lib.qtlib as qtlib
from ui.tab import ImgTab
from ui.export_settings import PathSettings, ExportVariableParser
from config import Config
from .stats_base import StatsLayout, StatsLoadGroupBox, StatsBaseProxyModel, StatsLoadTask, ExportCsv


# TODO: Region Position (how centered)
class MaskStatType(Enum):
    Area            = "area"
    RegionsWhite    = "regions_white"
    RegionsBlack    = "regions_black"


class MaskStats(QtWidgets.QWidget):
    EXPORT_PRESET_KEY = "stats-mask"

    def __init__(self, tab: ImgTab):
        super().__init__()
        self.tab = tab
        self.tab.filelist.addListener(self)

        self.parser = ExportVariableParser()
        self.parser.setup(self.tab.filelist.getCurrentFile())

        self.model = MaskModel()
        self.proxyModel = MaskProxyModel()
        self.proxyModel.setSourceModel(self.model)

        self.table = QtWidgets.QTableView()
        self.table.setModel(self.proxyModel)

        topLayout = QtWidgets.QHBoxLayout()
        topLayout.addWidget(self._buildOptions())
        topLayout.addWidget(self._buildMaskSource(), 1)

        self._layout = StatsLayout(tab, "Masks", self.proxyModel, self.table)
        self._layout.insertLayout(0, topLayout)
        self._layout.setStatsWidget(self._buildStats())
        self.setLayout(self._layout)


    def _buildOptions(self):
        layout = QtWidgets.QFormLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.cboStatsType = QtWidgets.QComboBox()
        self.cboStatsType.addItem("White Area", MaskStatType.Area)
        self.cboStatsType.addItem("White Region Count", MaskStatType.RegionsWhite)
        self.cboStatsType.addItem("Black Region Count", MaskStatType.RegionsBlack)
        layout.addRow("Stats Type:", self.cboStatsType)

        self.spinBins = QtWidgets.QSpinBox()
        self.spinBins.setRange(1, 1000)
        self.spinBins.setValue(20)
        layout.addRow("Max Bins:", self.spinBins)

        groupBox = QtWidgets.QGroupBox("Options")
        groupBox.setLayout(layout)
        return groupBox

    def _buildMaskSource(self):
        config = Config.exportPresets.get(self.EXPORT_PRESET_KEY, {})
        defaultPathTemplate = "{{path}}-masklabel.png"

        self.maskPathSettings = PathSettings(self.parser, showInfo=False, showSkip=False)
        self.maskPathSettings.pathTemplate = config.get("path_template", defaultPathTemplate)
        self.maskPathSettings.setAsInput()

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.maskPathSettings)

        groupBox = QtWidgets.QGroupBox("Mask Path")
        groupBox.setLayout(layout)
        return groupBox


    def _buildStats(self):
        loadBox = StatsLoadGroupBox(self._createTask)
        loadBox.dataLoaded.connect(self._onDataLoaded)

        self.lblNumFiles = loadBox.addLabel("Files:")
        self.lblNumMissing = loadBox.addLabel("Missing Masks:")
        self.lblNumBins = loadBox.addLabel("Bins:")
        self.lblMin = loadBox.addLabel("Min:")
        self.lblMax = loadBox.addLabel("Max:")
        self.lblMean = loadBox.addLabel("Average:")
        self.lblMedian = loadBox.addLabel("Median:")

        self._loadBox = loadBox
        return loadBox

    def _createTask(self):
        self.saveExportPreset()
        pathTemplate = self.maskPathSettings.pathTemplate

        match self.cboStatsType.currentData():
            case MaskStatType.Area:         loadFunc = MaskAreaLoadFunctor(pathTemplate)
            case MaskStatType.RegionsWhite: loadFunc = MaskRegionLoadFunctor(pathTemplate)
            case MaskStatType.RegionsBlack: loadFunc = MaskRegionLoadFunctor(pathTemplate, blackRegions=True)
            case _:
                raise ValueError(f"Unknown mask stats type: {self.cboStatsType.currentData()}")

        files = self.tab.filelist.getFiles().copy()
        numBins = self.spinBins.value()
        return MaskStatsLoadTask(files, numBins, loadFunc)


    @Slot()
    def _onDataLoaded(self, tags: list[MaskData], summary: MaskSummary):
        self.model.reload(tags, summary)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.resizeColumnsToContents()

        self.lblNumFiles.setText(str(summary.numFiles))
        self.lblNumMissing.setText(str(summary.numMissing))
        self.lblNumBins.setText(str(summary.numBins))
        self.lblMin.setText(f"{summary.min:.3f}")
        self.lblMax.setText(f"{summary.max:.3f}")
        self.lblMean.setText(f"{summary.mean:.3f}")
        self.lblMedian.setText(f"{summary.median:.3f}")

        missingStyle = f"color: {qtlib.COLOR_RED}" if summary.numMissing > 0 else ""
        self.lblNumMissing.setStyleSheet(missingStyle)

    def clearData(self):
        self._loadBox.terminateTask()
        self._loadBox.progressBar.reset()
        self._onDataLoaded([], MaskSummary().finalize([], 0))


    def onFileChanged(self, currentFile: str):
        self.parser.setup(currentFile)
        self.maskPathSettings.updatePreview()

    def onFileListChanged(self, currentFile: str):
        self.onFileChanged(currentFile)


    def saveExportPreset(self):
        Config.exportPresets[self.EXPORT_PRESET_KEY] = {
            "path_template": self.maskPathSettings.pathTemplate
        }



class MaskStatsLoadTask(StatsLoadTask):
    def __init__(self, files: list[str], numBins: int, loadFunc: MaskLoadFunctor):
        super().__init__("Mask")
        self.files = files
        self.numBins = max(numBins-2, 1)
        self.loadFunc = loadFunc


    def runLoad(self) -> tuple[list[MaskData], MaskSummary]:
        summary = MaskSummary()

        maskArea: dict[str, float] = dict()
        for file, value in self.map_auto(self.files, self.loadFunc, chunkSize=32):
            maskArea[file] = value
            summary.addFile(value)

        bins = list[MaskData]()
        values = sorted(maskArea.items(), key=lambda x: x[1])

        idxFirstExisting = next((i for i, val in enumerate(values) if val[1] > -0.1), len(values))
        if binVals := values[:idxFirstExisting]:
            # Add non-existing masks to separate bin
            bins.append(MaskData(binVals))
            values = values[idxFirstExisting:]

        for needsBinning, rangeValues in self.loadFunc.getValueRanges(values):
            if needsBinning:
                for binVals in self.makeBins(rangeValues):
                    bins.append(MaskData(binVals))
            else:
                bins.append(MaskData(rangeValues))

        summary.finalize(values, len(bins))
        return bins, summary


    def makeBins(self, values: list[tuple[str, float]]) -> Generator[list[tuple[str, float]]]:
        valMin = values[0][1]
        valMax = values[-1][1]

        binStep = (valMax - valMin) / self.numBins
        #binStep = max(binStep, 0.001)

        idxBinStart = 0
        valBinEnd = valMin + binStep
        for i, (file, val) in enumerate(values):
            if val > valBinEnd:
                if binVals := values[idxBinStart:i]:
                    yield binVals

                idxBinStart = i
                valBinEnd = val + binStep

        if binVals := values[idxBinStart:]:
            yield binVals



class MaskLoadFunctor:
    def __init__(self, pathTemplate: str):
        self.pathTemplate = pathTemplate
        self.parser = ExportVariableParser()

    def __call__(self, file: str) -> tuple[str, float]:
        self.parser.setup(file)
        maskPath = self.parser.parsePath(self.pathTemplate, overwriteFiles=True)
        val = self._processMask(maskPath) if os.path.exists(maskPath) else -1.0
        return file, val

    def _processMask(self, maskPath: str) -> float:
        raise NotImplementedError()

    def getValueRanges(self, values: list[tuple[str, float]]) -> Generator[tuple[bool, list[tuple[str, float]]]]:
        raise NotImplementedError()


class MaskAreaLoadFunctor(MaskLoadFunctor):
    def __init__(self, pathTemplate: str):
        super().__init__(pathTemplate)

    def _processMask(self, maskPath: str) -> float:
        import cv2 as cv
        mat = cv.imread(maskPath, cv.IMREAD_GRAYSCALE)
        count = cv.countNonZero(mat)

        h, w = mat.shape
        filledArea = count / (w * h)
        return filledArea

    def getValueRanges(self, values: list[tuple[str, float]]) -> Generator[tuple[bool, list[tuple[str, float]]]]:
        if not values:
            return

        if values[0][1] >= 1.0 or values[-1][1] <= 0.0:
            # All masks are completely white or black
            yield False, values
            return

        idxFirstFract = next(i for i, val in enumerate(values) if val[1] > 0.0)
        if idxFirstFract > 0:
            # Completely black masks
            yield False, values[:idxFirstFract]

        if values[idxFirstFract][1] >= 1.0:
            # No fractional area masks, rest is completely white
            yield False, values[idxFirstFract:]
            return

        # Fractional area masks
        idxFirstWhite = next(len(values)-i for i, val in enumerate(reversed(values)) if val[1] < 1.0)
        yield True, values[idxFirstFract:idxFirstWhite]

        if idxFirstWhite < len(values):
            # The remaining are completely white masks
            yield False, values[idxFirstWhite:]



class MaskRegionLoadFunctor(MaskLoadFunctor):
    def __init__(self, pathTemplate: str, blackRegions=False):
        super().__init__(pathTemplate)
        self.blackRegions = blackRegions

    def _processMask(self, maskPath: str) -> float:
        import cv2 as cv
        mat = cv.imread(maskPath, cv.IMREAD_GRAYSCALE)

        if self.blackRegions:
            cv.threshold(mat, 1, 255, cv.THRESH_BINARY, dst=mat)
            cv.bitwise_not(mat, dst=mat)

        numRegions, labels = cv.connectedComponents(mat, None, 8, cv.CV_16U)
        numRegions -= 1
        return numRegions

    def getValueRanges(self, values: list[tuple[str, float]]) -> Generator[tuple[bool, list[tuple[str, float]]]]:
        if values:
            yield True, values



class MaskData:
    def __init__(self, fileValues: list[tuple[str, float]]):
        self.files: set[str] = set(x[0] for x in fileValues)

        self.min = min((x[1] for x in fileValues), default=0)
        self.max = max((x[1] for x in fileValues), default=0)



class MaskSummary:
    def __init__(self):
        self.reset()

    def reset(self):
        self.numFiles = 0
        self.numMissing = 0
        self.numBins = 0

        self.min  = 2**31
        self.max  = -self.min
        self.mean = 0
        self.median = 0

    def addFile(self, value: float):
        self.numFiles += 1

        if value >= 0.0:
            self.min = min(self.min, value)
            self.max = max(self.max, value)
        else:
            self.numMissing += 1

    def finalize(self, sortedItems: list[tuple[str, float]], numBins: int) -> MaskSummary:
        if not sortedItems:
            self.min = self.max = 0
            return self

        self.numBins = numBins
        self.mean = sum(x[1] for x in sortedItems) / len(sortedItems)
        self.median = sortedItems[len(sortedItems) // 2][1]
        return self



class MaskModel(QAbstractItemModel):
    ROLE_DATA = Qt.ItemDataRole.UserRole.value

    def __init__(self):
        super().__init__()
        self.font = qtlib.getMonospaceFont()
        self.colorRed = QtGui.QColor(qtlib.COLOR_RED)

        self.maskBins: list[MaskData] = list()
        self.summary = MaskSummary()

    def reload(self, maskBins: list[MaskData], summary: MaskSummary):
        self.beginResetModel()
        self.maskBins = maskBins
        self.summary = summary
        self.endResetModel()


    # QAbstractItemModel Interface

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.maskBins)

    def columnCount(self, parent=QModelIndex()):
        return 3

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        data: MaskData = self.maskBins[index.row()]

        match role:
            case Qt.ItemDataRole.DisplayRole:
                match index.column():
                    case 0: return f"{data.min:.3f}"
                    case 1: return f"{data.max:.3f}"
                    case 2: return len(data.files)

            case Qt.ItemDataRole.ForegroundRole:
                if data.max < 0:
                    return self.colorRed

            case Qt.ItemDataRole.FontRole: return self.font
            case self.ROLE_DATA: return data

            case ExportCsv.ROLE_CSV:
                match index.column():
                    case 0: return data.min
                    case 1: return data.max
                    case 2: return len(data.files)

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole) -> str | None:
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return super().headerData(section, orientation, role)

        match section:
            case 0: return "Bin Min"
            case 1: return "Bin Max"
            case 2: return "Count"
        return None

    def index(self, row, column, parent=QModelIndex()):
        return self.createIndex(row, column)

    def parent(self, index):
        return QModelIndex()


class MaskProxyModel(StatsBaseProxyModel):
    def __init__(self):
        super().__init__()

    @override
    def getFiles(self, sourceIndex: QModelIndex) -> set[str]:
        data: MaskData = self.sourceModel().data(sourceIndex, MaskModel.ROLE_DATA)
        return data.files

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        column = left.column()
        if column == right.column():
            dataLeft: MaskData  = self.sourceModel().data(left, MaskModel.ROLE_DATA)
            dataRight: MaskData = self.sourceModel().data(right, MaskModel.ROLE_DATA)
            match column:
                case 0: return dataRight.min < dataLeft.min
                case 1: return dataRight.max < dataLeft.max
                case 2: return len(dataRight.files) < len(dataLeft.files)

        return super().lessThan(left, right)
