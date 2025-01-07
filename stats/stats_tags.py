from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QAbstractItemModel, QModelIndex
from lib.captionfile import FileTypeSelector
from ui.tab import ImgTab
from caption.caption_container import CaptionContainer
from .stats_base import StatsLayout, StatsBaseProxyModel


# TODO: CSV Export


class TagStats(QtWidgets.QWidget):
    def __init__(self, tab: ImgTab):
        super().__init__()
        self.tab = tab

        self.model = TagModel()
        self.proxyModel = TagProxyModel()
        self.proxyModel.setSourceModel(self.model)

        self.table = TagTableView(self.tab)
        self.table.setModel(self.proxyModel)

        self._layout = StatsLayout(tab, "Tags", self.proxyModel, self.table, 1)
        self._layout.addLayout(self._buildSourceSelector(), 0, 0, 1, 3)
        self._layout.addWidget(self._buildStats(), 1, 0)
        self.setLayout(self._layout)

    def _buildSourceSelector(self):
        self.captionSrc = FileTypeSelector()
        self.captionSrc.cboType.setCurrentIndex(1) # Tags
        
        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(QtWidgets.QLabel("Load From:"))
        layout.addLayout(self.captionSrc)
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
        self.model.reload(self.tab.filelist.getFiles(), self.captionSrc)
        self.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self.table.resizeColumnsToContents()

        summary = self.model.summary
        self.lblNumFiles.setText(str(summary.numFiles))
        self.lblTotalTags.setText(str(summary.totalNumTags))
        self.lblUniqueTags.setText(str(summary.uniqueTags))
        self.lblTagsPerImage.setText(f"{summary.minNumTags} - {summary.maxNumTags}")
        self.lblAvgTagsPerImage.setText(f"{summary.getAvgNumTags():.1f}")



class TagData:
    def __init__(self, tag: str):
        self.tag = tag
        self.count = 0
        self.files: set[str] = set()

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
        self.separator = ","
        self.font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)

        self.tags: list[TagData] = list()
        self.summary = TagSummary()

    def reload(self, files: list[str], captionSrc: FileTypeSelector):
        self.beginResetModel()

        self.tags.clear()
        self.summary.reset()

        tagData: dict[str, TagData] = dict()
        for file in files:
            caption = captionSrc.loadCaption(file)
            if not caption:
                continue

            tags = caption.split(self.separator)
            tags = (tag.strip() for tag in tags)
            tags = [tag for tag in tags if tag]
            self.summary.addFile(tags)

            for tag in tags:
                data = tagData.get(tag)
                if not data:
                    tagData[tag] = data = TagData(tag)
                data.addFile(file)
        
        self.tags.extend(tagData.values())
        self.endResetModel()
        self.summary.finalize(len(self.tags))


    # QAbstractItemModel Interface

    def rowCount(self, parent=QModelIndex()):
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
            case self.ROLE_TAG:  return tagData.tag
            case self.ROLE_DATA: return tagData

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
    def __init__(self, tab: ImgTab):
        super().__init__()
        self.tab = tab

        self._menu = self._buildMenu()
        self._index: QModelIndex | None = None

    def _buildMenu(self) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu(self)

        actAdd = menu.addAction("Add to Caption")
        actAdd.triggered.connect(self._addTag)

        menu.addSeparator()

        actBan = menu.addAction("Ban")
        actBan.triggered.connect(self._banTag)

        return menu

    def contextMenuEvent(self, event):
        try:
            self._index = self.indexAt(event.pos())
            if self._index.isValid():
                self._menu.exec_(event.globalPos())
        finally:
            self._index = None

    def getCaptionWindow(self) -> CaptionContainer | None:
        if captionWin := self.tab.getWindowContent("caption"):
            return captionWin
        
        QtWidgets.QMessageBox.warning(self, "Failed", "Caption Window is not open.")
        return None

    @Slot()
    def _addTag(self):
        if captionWin := self.getCaptionWindow():
            tag = self.model().data(self._index, TagModel.ROLE_TAG)
            captionWin.appendToCaption(tag)

    @Slot()
    def _banTag(self):
        if captionWin := self.getCaptionWindow():
            tag = self.model().data(self._index, TagModel.ROLE_TAG)
            captionWin.ctx.settings.addBannedCaption(tag)
