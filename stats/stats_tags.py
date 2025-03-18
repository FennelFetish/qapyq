from typing import Iterable
from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal, QAbstractItemModel, QModelIndex
from lib.captionfile import FileTypeSelector
from lib.util import CaptionSplitter
import lib.qtlib as qtlib
from ui.tab import ImgTab
from batch.batch_container import BatchContainer
from batch.batch_rules import BatchRules
from caption.caption_container import CaptionContainer
from caption.caption_groups import CaptionControlGroup
from caption.caption_preset import CaptionPreset, CaptionPresetConditional, MutualExclusivity
from .stats_base import StatsLayout, StatsBaseProxyModel, ExportCsv


class TagStats(QtWidgets.QWidget):
    def __init__(self, tab: ImgTab):
        super().__init__()
        self.tab = tab
        self._captionSlotConnected = False

        self.model = TagModel()
        self.proxyModel = TagProxyModel()
        self.proxyModel.setSourceModel(self.model)

        self.table = TagTableView(self)
        self.table.setModel(self.proxyModel)
        self.table.captionRulesChanged.connect(self.reloadColors)

        self._layout = TagStatsLayout(self, tab, self.proxyModel, self.table, 1)
        self._layout.insertLayout(0, self._buildTopRow())
        self._layout.setStatsWidget(self._buildStats())
        self.setLayout(self._layout)

    def _buildTopRow(self):
        self.captionSrc = FileTypeSelector()
        self.captionSrc.type = FileTypeSelector.TYPE_TAGS

        self.txtSepChars = QtWidgets.QLineEdit(",.:;\\n")
        qtlib.setMonospace(self.txtSepChars)
        self.txtSepChars.setMaximumWidth(120)

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(QtWidgets.QLabel("Load From:"))
        layout.addLayout(self.captionSrc)
        layout.addSpacing(20)
        layout.addWidget(QtWidgets.QLabel("Separators:"))
        layout.addWidget(self.txtSepChars)
        layout.addStretch(1)
        return layout

    def _buildStats(self):
        layout = QtWidgets.QFormLayout()
        layout.setHorizontalSpacing(12)

        btnReloadCaptions = QtWidgets.QPushButton("Reload")
        btnReloadCaptions.clicked.connect(self.reload)
        layout.addRow(btnReloadCaptions)

        self.lblNumFiles = QtWidgets.QLabel("0")
        layout.addRow("Tagged Files:", self.lblNumFiles)

        self.lblTotalTags = QtWidgets.QLabel("0")
        layout.addRow("Total Tags:", self.lblTotalTags)

        self.lblUniqueTags = QtWidgets.QLabel("0")
        layout.addRow("Unique Tags:", self.lblUniqueTags)

        self.lblTagsPerImage = QtWidgets.QLabel("0")
        layout.addRow("Per Image:", self.lblTagsPerImage)

        self.lblAvgTagsPerImage = QtWidgets.QLabel("0")
        layout.addRow("Average:", self.lblAvgTagsPerImage)

        group = QtWidgets.QGroupBox("Stats")
        group.setLayout(layout)
        return group


    @Slot()
    def reload(self):
        self.model.reload(self.tab.filelist.getFiles(), self.captionSrc, self.txtSepChars.text())
        self.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self.table.resizeColumnsToContents()

        summary = self.model.summary
        self.lblNumFiles.setText(str(summary.numFiles))
        self.lblTotalTags.setText(str(summary.totalNumTags))
        self.lblUniqueTags.setText(str(summary.uniqueTags))
        self.lblTagsPerImage.setText(f"{summary.minNumTags} - {summary.maxNumTags}")
        self.lblAvgTagsPerImage.setText(f"{summary.getAvgNumTags():.1f}")

        self.reloadColors()

    @Slot()
    def reloadColors(self):
        captionWin: CaptionContainer | None = self.tab.getWindowContent("caption")
        if not captionWin:
            return

        self.model.updateColors(captionWin.ctx.groups.getCaptionCharFormats())
        if not self._captionSlotConnected:
            captionWin.ctx.controlUpdated.connect(self.reloadColors)
            self._captionSlotConnected = True

    def clearData(self):
        self.model.clear()



class TagData:
    def __init__(self, tag: str):
        self.tag = tag
        self.count = 0
        self.files: set[str] = set()
        self.color: QtGui.QColor | None = None

    def addFile(self, file: str):
        self.files.add(file)
        self.count += 1


class TagSummary:
    def __init__(self):
        self.reset()

    def reset(self):
        self.totalNumTags = 0
        self.minNumTags = 2**31
        self.maxNumTags = 0
        self.numFiles   = 0
        self.uniqueTags = 0

    def addFile(self, tags: list[str]):
        numTags = len(tags)
        self.totalNumTags += numTags
        self.minNumTags = min(self.minNumTags, numTags)
        self.maxNumTags = max(self.maxNumTags, numTags)
        self.numFiles += 1

    def finalize(self, numUniqueTags: int):
        self.uniqueTags = numUniqueTags
        if self.numFiles == 0:
            self.minNumTags = 0

    def getAvgNumTags(self):
        if self.numFiles == 0:
            return 0.0
        return self.totalNumTags / self.numFiles


class TagModel(QAbstractItemModel):
    ROLE_TAG  = Qt.ItemDataRole.UserRole.value
    ROLE_DATA = Qt.ItemDataRole.UserRole.value + 1

    def __init__(self):
        super().__init__()
        self.font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)

        self.tags: list[TagData] = list()
        self.summary = TagSummary()

    def reload(self, files: list[str], captionSrc: FileTypeSelector, sepChars: str):
        splitter = CaptionSplitter(sepChars)
        self.beginResetModel()

        self.tags.clear()
        self.summary.reset()

        tagData: dict[str, TagData] = dict()
        for file in files:
            caption = captionSrc.loadCaption(file)
            if not caption:
                continue

            tags = splitter.split(caption)
            self.summary.addFile(tags)

            for tag in tags:
                data = tagData.get(tag)
                if not data:
                    tagData[tag] = data = TagData(tag)
                data.addFile(file)

        self.tags.extend(tagData.values())
        self.summary.finalize(len(self.tags))
        self.endResetModel()

    def updateColors(self, groupCharFormats: dict[str, QtGui.QTextCharFormat]):
        changedRoles = [Qt.ItemDataRole.ForegroundRole]
        for row, tag in enumerate(self.tags):
            charFormat = groupCharFormats.get(tag.tag)
            color = charFormat.foreground().color() if charFormat else None
            if tag.color != color:
                tag.color = color
                self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount()-1), changedRoles)

    def clear(self):
        self.beginResetModel()
        self.tags.clear()
        self.summary.reset()
        self.summary.finalize(0)
        self.endResetModel()


    # QAbstractItemModel Interface

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.tags)

    def columnCount(self, parent=QModelIndex()):
        return 3

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        tagData: TagData = self.tags[index.row()]

        match role:
            case Qt.ItemDataRole.DisplayRole:
                match index.column():
                    case 0: return tagData.tag
                    case 1: return tagData.count
                    case 2:
                        presence = 0
                        if self.summary.numFiles > 0:
                            presence = len(tagData.files) / self.summary.numFiles
                        return f"{presence*100:.2f} %"

            case Qt.ItemDataRole.FontRole: return self.font
            case Qt.ItemDataRole.ForegroundRole: return tagData.color
            case self.ROLE_TAG:  return tagData.tag
            case self.ROLE_DATA: return tagData

            case ExportCsv.ROLE_CSV:
                match index.column():
                    case 0: return tagData.tag
                    case 1: return tagData.count
                    case 2: return len(tagData.files) / self.summary.numFiles if self.summary.numFiles else 0.0

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole) -> str | None:
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return super().headerData(section, orientation, role)

        match section:
            case 0: return "Tag"
            case 1: return "Count"
            case 2: return "Presence"
        return None

    def index(self, row, column, parent=QModelIndex()):
        return self.createIndex(row, column)

    def parent(self, index):
        return QModelIndex()


class TagProxyModel(StatsBaseProxyModel):
    def __init__(self):
        super().__init__()
        self.setFilterKeyColumn(0)

    @override
    def getFiles(self, sourceIndex: QModelIndex) -> set[str]:
        data: TagData = self.sourceModel().data(sourceIndex, TagModel.ROLE_DATA)
        return data.files

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        column = left.column()
        if column == right.column():
            dataLeft: TagData  = self.sourceModel().data(left, TagModel.ROLE_DATA)
            dataRight: TagData = self.sourceModel().data(right, TagModel.ROLE_DATA)
            match column:
                case 1: return dataRight.count < dataLeft.count
                case 2: return len(dataRight.files) < len(dataLeft.files)

        return super().lessThan(left, right)



class TagTableView(QtWidgets.QTableView):
    captionRulesChanged = Signal()

    def __init__(self, tagStats: TagStats):
        super().__init__()
        self.tagStats = tagStats
        self.tab = tagStats.tab

        self._menu = self._buildMenu()
        self._index: QModelIndex | None = None

    def _buildMenu(self) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu("Tag Menu", self)

        actAdd = menu.addAction("Add to Caption")
        actAdd.triggered.connect(self._addTags)

        self._groupMenu = QtWidgets.QMenu("Add to Group")
        menu.addMenu(self._groupMenu)

        actFocus = menu.addAction("Add to Focus")
        actFocus.triggered.connect(self._focusTags)

        menu.addSeparator()

        actBan = menu.addAction("Ban")
        actBan.triggered.connect(self._banTags)

        menu.addSeparator()
        menu.addMenu(self._buildBatchMenu())

        return menu

    def _buildBatchMenu(self) -> QtWidgets.QMenu:
        batchMenu = QtWidgets.QMenu("Batch")

        actAdd = batchMenu.addAction("Add to All...")
        actAdd.triggered.connect(self._batchAddTags)

        actRemove = batchMenu.addAction("Remove Tag(s)...")
        actRemove.triggered.connect(self._batchRemoveTags)

        actReplace = batchMenu.addAction("Replace Tag(s)...")
        actReplace.triggered.connect(self._batchReplaceTags)

        actPrioritizeSelected = batchMenu.addAction("Prioritize Selected Tag...")
        actPrioritizeSelected.triggered.connect(self._batchPrioritizeSelectedTag)

        return batchMenu


    def _rebuildGroupMenu(self):
        self._groupMenu.clear()

        captionWin: CaptionContainer | None = self.tab.getWindowContent("caption")
        if captionWin:
            for group in captionWin.ctx.groups.groups:
                act = self._groupMenu.addAction(group.name)
                act.triggered.connect(lambda checked, group=group: self._addTagsToGroup(group))

            self._groupMenu.addSeparator()
            actNewGroup = self._groupMenu.addAction("New Group")
            actNewGroup.triggered.connect(lambda checked, captionWin=captionWin: self._addTagsToNewGroup(captionWin))

        if self._groupMenu.isEmpty():
            actEmpty = self._groupMenu.addAction("Caption Window not open")
            actEmpty.setEnabled(False)

    def contextMenuEvent(self, event):
        try:
            self._index = self.indexAt(event.pos())
            if self._index.isValid():
                self._rebuildGroupMenu()
                self._menu.exec_(event.globalPos())
        finally:
            self._index = None


    def currentTag(self) -> str:
        if self._index is None:
            return ""
        return self.model().data(self._index, TagModel.ROLE_TAG)

    def selectedTags(self) -> Iterable[str]:
        return (
            self.model().data(index, TagModel.ROLE_TAG)
            for index in self.selectionModel().selectedRows()
        )


    @Slot()
    def _addTags(self):
        if captionWin := getCaptionWindow(self.tab, self):
            for tag in self.selectedTags():
                captionWin.appendToCaption(tag)

            # Not needed, but will connect the update signal
            self.captionRulesChanged.emit()

    @Slot()
    def _focusTags(self):
        if captionWin := getCaptionWindow(self.tab, self):
            for tag in self.selectedTags():
                captionWin.ctx.focus.appendFocusTag(tag)
            self.captionRulesChanged.emit()

    @Slot()
    def _banTags(self):
        if captionWin := getCaptionWindow(self.tab, self):
            for tag in self.selectedTags():
                captionWin.ctx.settings.addBannedCaption(tag)
            self.captionRulesChanged.emit()

    def _addTagsToGroup(self, group: CaptionControlGroup):
        for tag in self.selectedTags():
            group._addCaptionDrop(tag)
        self.captionRulesChanged.emit()

    def _addTagsToNewGroup(self, captionWin: CaptionContainer):
        group = captionWin.ctx.groups.addGroup()
        self._addTagsToGroup(group)


    @Slot()
    def _batchAddTags(self):
        preset = CaptionPreset()
        for tag in self.selectedTags():
            cond = CaptionPresetConditional.Condition()
            cond.key = "AllTagsPresent"
            cond.params = {"tags": tag}

            actionAdd = CaptionPresetConditional.Action()
            actionAdd.key = "AddTags"
            actionAdd.params = {"tags": tag}

            rule = CaptionPresetConditional()
            rule.expression = "not A"
            rule.conditions.append(cond)
            rule.actions.append(actionAdd)
            preset.conditionals.append(rule)

        applyBatchRulesPreset(self.tab, self, preset, self.tagStats.captionSrc, "conditionals")

    @Slot()
    def _batchRemoveTags(self):
        preset = CaptionPreset()
        preset.banned.extend(self.selectedTags())
        applyBatchRulesPreset(self.tab, self, preset, self.tagStats.captionSrc, "rules")

    @Slot()
    def _batchReplaceTags(self):
        preset = CaptionPreset()
        for tag in self.selectedTags():
            actionReplace = CaptionPresetConditional.Action()
            actionReplace.key = "ReplaceTags"
            actionReplace.params = {"search": tag, "replace": ""}

            rule = CaptionPresetConditional()
            rule.expression = "True"
            rule.actions.append(actionReplace)
            preset.conditionals.append(rule)

        applyBatchRulesPreset(self.tab, self, preset, self.tagStats.captionSrc, "conditionals")

    @Slot()
    def _batchPrioritizeSelectedTag(self):
        currentTag = self.currentTag()
        tags = [tag for tag in self.selectedTags() if tag != currentTag]
        tags.append(currentTag)

        preset = CaptionPreset()
        preset.addGroup("Group", "#000", MutualExclusivity.Priority, False, tags)
        applyBatchRulesPreset(self.tab, self, preset, self.tagStats.captionSrc, "groups")



class TagStatsLayout(StatsLayout):
    def __init__(self, tagStats: TagStats, tab: ImgTab, proxyModel: StatsBaseProxyModel, tableView: QtWidgets.QTableView, row=0):
        super().__init__(tab, "Tags", proxyModel, tableView, row)
        self.tagStats = tagStats

    def _buildFilesMenu(self, parent) -> QtWidgets.QMenu:
        menu = super()._buildFilesMenu(parent)
        menu.addSeparator()

        actFocus = menu.addAction("Focus in New Tab")
        actFocus.triggered.connect(self._openNewTabWithFocus)

        return menu

    @Slot()
    def _openNewTabWithFocus(self):
        if not self.hasListedFiles():
            return

        oldTab = self.tab
        oldCaptionWin = getCaptionWindow(oldTab, self.tagStats, show=True)
        if not oldCaptionWin:
            return

        newTab: ImgTab | None = self._loadFilesInNewTab()
        if not newTab:
            return

        newCaptionWin: CaptionContainer | None = newTab.getWindowContent("caption")
        if not newCaptionWin:
            return

        selectedTags = []
        for srcIndex in self.getSelectedSourceIndexes():
            tag = self.proxyModel.sourceModel().data(srcIndex, TagModel.ROLE_TAG)
            selectedTags.append(tag)

        captionPreset = oldCaptionWin.ctx.settings.getPreset()
        newCaptionWin.ctx.settings.applyPreset(captionPreset)

        newCaptionWin.ctx.focus.setFocusTags(selectedTags)
        newCaptionWin.ctx.setCurrentWidget(newCaptionWin.ctx.focus)

        newCaptionWin.srcSelector.type = self.tagStats.captionSrc.type
        newCaptionWin.srcSelector.name = self.tagStats.captionSrc.name
        newCaptionWin.resetCaption()



def getCaptionWindow(tab: ImgTab, parent: QtWidgets.QWidget, show=False) -> CaptionContainer | None:
    return getAuxWindow("caption", tab, parent, show)

def getBatchWindow(tab: ImgTab, parent: QtWidgets.QWidget, show=False) -> BatchContainer | None:
    return getAuxWindow("batch", tab, parent, show)


def applyBatchRulesPreset(tab: ImgTab, parent: QtWidgets.QWidget, captionPreset: CaptionPreset, captionSrc: FileTypeSelector, subtab=""):
    batchWin = getBatchWindow(tab, parent, show=True)
    if not batchWin:
        return

    rulesTab: BatchRules = batchWin.getTab("rules", selectTab=True)
    rulesTab.srcSelector.type = captionSrc.type
    rulesTab.srcSelector.name = captionSrc.name
    rulesTab.destSelector.type = captionSrc.type
    rulesTab.destSelector.name = captionSrc.name

    captionPreset.removeDuplicates = False
    captionPreset.sortCaptions = False
    rulesTab.applyPreset(captionPreset)

    if subtab:
        rulesTab.showSubtab(subtab)


def getAuxWindow(windowName: str, tab: ImgTab, parent: QtWidgets.QWidget, show: bool) -> QtWidgets.QWidget | None:
    if not show and (win := tab.getWindowContent(windowName)):
        return win

    # If Window didn't exist, show it
    if win := tab.mainWindow.showAuxWindow(windowName, tab):
        return win

    QtWidgets.QMessageBox.information(parent, "Failed", f"{windowName.capitalize()} Window is not open.")
    return None
