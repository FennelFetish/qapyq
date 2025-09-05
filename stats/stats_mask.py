from __future__ import annotations
import os
from enum import Enum
from typing import Generator, NamedTuple
from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QAbstractItemModel, QModelIndex
import cv2 as cv
import lib.imagerw as imagerw
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


STAT_NAMES = {
    MaskStatType.Area: "Area ",
    MaskStatType.RegionsWhite: "Regions ",
    MaskStatType.RegionsBlack: "Regions "
}



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

        self._layout = StatsLayout(tab, "Mask Buckets", self.proxyModel, self.table)
        self._layout.insertLayout(0, topLayout)
        self._layout.setStatsWidget(self._buildStats())
        self.setLayout(self._layout)


    def _buildOptions(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        row = 0
        self.cboStatsType = QtWidgets.QComboBox()
        self.cboStatsType.addItem("White Area", MaskStatType.Area)
        self.cboStatsType.addItem("White Region Count", MaskStatType.RegionsWhite)
        self.cboStatsType.addItem("Black Region Count", MaskStatType.RegionsBlack)
        layout.addWidget(QtWidgets.QLabel("Stats Type:"), row, 0)
        layout.addWidget(self.cboStatsType, row, 1)

        row += 1
        self.chkThreshold = QtWidgets.QCheckBox("Threshold:")
        self.chkThreshold.setToolTip("Binarize the mask with the given threshold color.")
        self.chkThreshold.toggled.connect(self._onThresholdToggled)
        layout.addWidget(self.chkThreshold, row, 0)

        self.spinThreshold = QtWidgets.QDoubleSpinBox()
        self.spinThreshold.setRange(0.0, 1.0)
        self.spinThreshold.setSingleStep(0.1)
        self.spinThreshold.setValue(0.5)
        self.spinThreshold.setEnabled(False)
        layout.addWidget(self.spinThreshold, row, 1)

        groupBox = QtWidgets.QGroupBox("Options")
        groupBox.setLayout(layout)
        return groupBox

    @Slot()
    def _onThresholdToggled(self, state: bool):
        self.spinThreshold.setEnabled(state)


    def _buildMaskSource(self):
        config = Config.exportPresets.get(self.EXPORT_PRESET_KEY, {})
        defaultPathTemplate = "{{path}}-masklabel.png"

        self.maskPathSettings = PathSettings(self.parser, showInfo=False, showSkip=False)
        self.maskPathSettings.pathTemplate = config.get("path_template", defaultPathTemplate)
        self.maskPathSettings.setAsInput()

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.maskPathSettings)
        layout.addStretch()

        groupBox = QtWidgets.QGroupBox("Mask Path")
        groupBox.setLayout(layout)
        return groupBox


    def _buildStats(self):
        loadBox = StatsLoadGroupBox(self._createTask)
        loadBox.dataLoaded.connect(self._onDataLoaded)

        self.lblNumMasks = loadBox.addLabel("Masks:")
        self.lblNumMissing = loadBox.addLabel("Missing Masks:")
        self.lblNumBins = loadBox.addLabel("Buckets:")
        self.lblMin = loadBox.addLabel("Min:")
        self.lblMax = loadBox.addLabel("Max:")
        self.lblMean = loadBox.addLabel("Average:")
        self.lblMedian = loadBox.addLabel("Median:")

        self._loadBox = loadBox
        return loadBox

    def _createTask(self):
        self.saveExportPreset()
        pathTemplate = self.maskPathSettings.pathTemplate

        threshold: int | None = None
        if self.chkThreshold.isChecked():
            threshold = round(self.spinThreshold.value() * 255)

        statsType = self.cboStatsType.currentData()
        match statsType:
            case MaskStatType.Area:         loadFunc = MaskAreaLoadFunctor(pathTemplate, threshold)
            case MaskStatType.RegionsWhite: loadFunc = MaskRegionLoadFunctor(pathTemplate,threshold)
            case MaskStatType.RegionsBlack: loadFunc = MaskRegionLoadFunctor(pathTemplate, threshold, blackRegions=True)
            case _:
                raise ValueError(f"Unknown mask stats type: {statsType}")

        files = self.tab.filelist.getFiles().copy()
        return MaskStatsLoadTask(statsType, files, loadFunc)


    @Slot()
    def _onDataLoaded(self, tags: list[MaskData], summary: MaskSummary):
        self.model.reload(tags, summary)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.resizeColumnsToContents()

        self.lblNumMasks.setText(str(summary.numMasks))
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



class MaskValue(NamedTuple):
    file: str
    value: float

    def sortKey(self) -> float:
        return self.value



class MaskStatsLoadTask(StatsLoadTask):
    def __init__(self, statsType: MaskStatType, files: list[str], loadFunc: MaskLoadFunctor):
        super().__init__("Mask")
        self.statsType = statsType
        self.files = files
        self.loadFunc = loadFunc


    def runLoad(self) -> tuple[list[MaskData], MaskSummary]:
        summary = MaskSummary(self.statsType)

        values: list[MaskValue] = list()
        for file, value in self.map_auto(self.files, self.loadFunc, chunkSize=24):
            values.append(MaskValue(file, value))
            summary.addFile(value)

        values.sort(key=MaskValue.sortKey)
        bins = list[MaskData]()

        idxFirstExisting = next((i for i, val in enumerate(values) if val.value > -0.1), len(values))
        if binVals := values[:idxFirstExisting]:
            # Add non-existing masks to separate bin
            bins.append(MaskData(binVals))
            values = values[idxFirstExisting:]

        for rangeValues in self.loadFunc.getValueRanges(values):
            bins.append(MaskData(rangeValues))

        summary.finalize(values, len(bins))
        return bins, summary



def makeBins(values: list[MaskValue], numBins: int) -> Generator[list[MaskValue]]:
    valMin = values[0].value
    valMax = values[-1].value

    binStep = (valMax - valMin) / numBins
    #binStep = max(binStep, 0.001)

    idxBinStart = 0
    valBinEnd = valMin + binStep
    for i, val in enumerate(values):
        if val.value > valBinEnd:
            if binVals := values[idxBinStart:i]:
                yield binVals

            idxBinStart = i
            valBinEnd = val.value + binStep

    if binVals := values[idxBinStart:]:
        yield binVals


def makeBinsPerValue(values: list[MaskValue]) -> Generator[list[MaskValue]]:
    currentVal = values[0].value
    idxBinStart = 0

    for i, val in enumerate(values):
        if val.value > currentVal:
            if binVals := values[idxBinStart:i]:
                yield binVals

            currentVal = val.value
            idxBinStart = i

    if binVals := values[idxBinStart:]:
        yield binVals



class MaskLoadFunctor:
    def __init__(self, pathTemplate: str, threshold: int | None):
        self.pathTemplate = pathTemplate
        self.parser = ExportVariableParser()
        self.threshold = threshold

    def __call__(self, file: str) -> tuple[str, float]:
        self.parser.setup(file)
        maskPath = self.parser.parsePath(self.pathTemplate, overwriteFiles=True)

        if not os.path.isfile(maskPath):
            return file, -1

        mat = imagerw.loadMatBGR(maskPath, rgb=True)
        if len(mat.shape) > 2:
            mat = mat[..., 0].copy() # First channel (red), make copy to allow inplace operations

        val = self._processMask(mat)
        return file, val

    def _processMask(self, mat) -> float:
        raise NotImplementedError()

    def getValueRanges(self, values: list[MaskValue]) -> Generator[list[MaskValue]]:
        raise NotImplementedError()


class MaskAreaLoadFunctor(MaskLoadFunctor):
    def __init__(self, pathTemplate: str, threshold: int | None, numBins: int = 20):
        super().__init__(pathTemplate, threshold)
        self.numBins = max(numBins-2, 1)

    def _processMask(self, mat) -> float:
        if self.threshold is not None:
            cv.threshold(mat, self.threshold, 255, cv.THRESH_BINARY, dst=mat)

        count = cv.countNonZero(mat)

        h, w = mat.shape
        filledArea = count / (w * h)
        return filledArea

    def getValueRanges(self, values: list[MaskValue]) -> Generator[list[MaskValue]]:
        if not values:
            return

        if values[0].value >= 1.0 or values[-1].value <= 0.0:
            # All masks are completely white or black
            yield values
            return

        idxFirstFract = next(i for i, val in enumerate(values) if val.value > 0.0)
        if idxFirstFract > 0:
            # Completely black masks
            yield values[:idxFirstFract]

        if values[idxFirstFract].value >= 1.0:
            # No fractional area masks, rest is completely white
            yield values[idxFirstFract:]
            return

        # Fractional area masks
        idxFirstWhite = next(len(values)-i for i, val in enumerate(reversed(values)) if val.value < 1.0)
        yield from makeBins(values[idxFirstFract:idxFirstWhite], self.numBins)

        if idxFirstWhite < len(values):
            # The remaining are completely white masks
            yield values[idxFirstWhite:]



class MaskRegionLoadFunctor(MaskLoadFunctor):
    def __init__(self, pathTemplate: str, threshold: int | None, blackRegions=False):
        super().__init__(pathTemplate, threshold)
        self.blackRegions = blackRegions

        if blackRegions:
            self.threshold = 1 if threshold is None else max(threshold, 1)

    def _processMask(self, mat) -> float:
        if self.blackRegions:
            cv.threshold(mat, self.threshold, 255, cv.THRESH_BINARY, dst=mat)
            cv.bitwise_not(mat, dst=mat)
        elif self.threshold is not None:
            cv.threshold(mat, self.threshold, 255, cv.THRESH_BINARY, dst=mat)

        numRegions, labels = cv.connectedComponents(mat, None, 8, cv.CV_16U)
        numRegions -= 1
        return numRegions

    def getValueRanges(self, values: list[MaskValue]) -> Generator[list[MaskValue]]:
        if values:
            yield from makeBinsPerValue(values)



class MaskData:
    def __init__(self, fileValues: list[MaskValue]):
        self.files: set[str] = set(val.file for val in fileValues)

        self.min = min((val.value for val in fileValues), default=0)
        self.max = max((val.value for val in fileValues), default=0)



class MaskSummary:
    def __init__(self, statsType: MaskStatType = None):
        self.statsType = statsType
        self.reset()

    def reset(self):
        self.numFiles   = 0
        self.numMasks   = 0
        self.numMissing = 0
        self.numBins    = 0

        self.min  = 2**31
        self.max  = -self.min
        self.mean = 0
        self.median = 0

    def addFile(self, value: float):
        self.numFiles += 1
        if value >= 0.0:
            self.numMasks += 1
            self.min = min(self.min, value)
            self.max = max(self.max, value)
        else:
            self.numMissing += 1

    def finalize(self, sortedItems: list[MaskValue], numBins: int) -> MaskSummary:
        self.numBins = numBins

        if not sortedItems:
            self.min = self.max = 0
            return self

        self.mean = sum(val.value for val in sortedItems) / len(sortedItems)
        self.median = sortedItems[len(sortedItems) // 2].value
        return self



class MaskModel(QAbstractItemModel):
    ROLE_DATA = Qt.ItemDataRole.UserRole.value

    def __init__(self):
        super().__init__()
        self.font = qtlib.getMonospaceFont()
        self.colorRed = QtGui.QColor(qtlib.COLOR_RED)

        self.statsName: str = ""
        self.maskBins: list[MaskData] = list()
        self.summary = MaskSummary()

    def reload(self, maskBins: list[MaskData], summary: MaskSummary):
        self.beginResetModel()
        self.statsName = STAT_NAMES.get(summary.statsType, "")
        self.maskBins = maskBins
        self.summary = summary
        self.endResetModel()


    # QAbstractItemModel Interface

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.maskBins)

    def columnCount(self, parent=QModelIndex()):
        return 4

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        data: MaskData = self.maskBins[index.row()]

        match role:
            case Qt.ItemDataRole.DisplayRole:
                match index.column():
                    case 0: return f"{data.min:.3f}"
                    case 1: return f"{data.max:.3f}"
                    case 2: return len(data.files)
                    case 3:
                        percentage = 0
                        if self.summary.numFiles > 0:
                            percentage = len(data.files) / self.summary.numFiles
                        return f"{percentage*100:.2f} %"

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
                    case 3: return len(data.files) / self.summary.numFiles if self.summary.numFiles else 0.0

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole) -> str | None:
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return super().headerData(section, orientation, role)

        match section:
            case 0: return f"{self.statsName}Min"
            case 1: return f"{self.statsName}Max"
            case 2: return "Count"
            case 3: return "Percentage"
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
                case 2 | 3: return len(dataRight.files) < len(dataLeft.files)

        return super().lessThan(left, right)
