
from typing_extensions import override
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QAbstractItemModel, QModelIndex
from lib.captionfile import FileTypeSelector
from ui.tab import ImgTab
from caption.caption_container import CaptionContainer
from .stats_base import StatsBaseLayout


# TODO: CSV Export


class TagStats(QtWidgets.QWidget):
    def __init__(self, tab: ImgTab):
        super().__init__()
        self.tab = tab

        self.model = TagModel()
        self.table = TagTableView(self.tab)
        self.table.setModel(self.model)

        self._layout = TagLayout(tab, self.model, self.table, 1)
        self._layout.addLayout(self._buildSourceSelector(), 0, 0, 1, 3)
        self._layout.addWidget(self._buildStats(), 1, 0)
        self.setLayout(self._layout)

    def _buildSourceSelector(self):
        self.captionSrc = FileTypeSelector()
        self.captionSrc.cboType.setCurrentIndex(1) # Tags

        btnReloadCaptions = QtWidgets.QPushButton("Reload")
        btnReloadCaptions.clicked.connect(self.reload)
        
        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(QtWidgets.QLabel("Load From:"))
        layout.addLayout(self.captionSrc)
        layout.addWidget(btnReloadCaptions)
        return layout

    def _buildStats(self):
        layout = QtWidgets.QFormLayout()
        layout.setHorizontalSpacing(12)

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
        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(1)

        #self.table.selectionModel().clear() # TODO <<<

        summary = self.model.summary
        self.lblNumFiles.setText(str(summary.numFiles))
        self.lblTotalTags.setText(str(summary.totalNumTags))
        self.lblUniqueTags.setText(str(summary.uniqueTags))
        self.lblTagsPerImage.setText(f"{summary.minNumTags} - {summary.maxNumTags}")
        self.lblAvgTagsPerImage.setText(f"{summary.getAvgNumTags():.1f}")



class TagData:
    def __init__(self):
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

        self.tagData: dict[str, TagData] = dict()
        self.tagOrder: list[str] = list()
        self.summary = TagSummary()

    def reload(self, files: list[str], captionSrc: FileTypeSelector):
        self.beginResetModel()

        self.tagData.clear()
        self.tagOrder.clear()
        self.summary.reset()

        for file in files:
            caption = captionSrc.loadCaption(file)
            if not caption:
                continue

            tags = caption.split(self.separator)
            tags = (tag.strip() for tag in tags)
            tags = [tag for tag in tags if tag]
            self.summary.addFile(tags)

            for tag in tags:
                data = self.tagData.get(tag)
                if not data:
                    self.tagData[tag] = data = TagData()
                data.addFile(file)
        
        self.tagOrder.extend(tag for tag in self.tagData.keys())
        self.endResetModel()

        self.summary.uniqueTags = len(self.tagOrder)


    # QAbstractItemModel Interface

    def rowCount(self, parent=QModelIndex()):
        return len(self.tagOrder)

    def columnCount(self, parent=QModelIndex()):
        return 3

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        tag = self.tagOrder[index.row()]

        if role == Qt.ItemDataRole.DisplayRole:
            match index.column():
                case 0: return tag
                case 1: return self.tagData[tag].count
                case 2:
                    presence = 0
                    if self.summary.numFiles > 0:
                        presence = len(self.tagData[tag].files) / self.summary.numFiles
                    return f"{presence*100:.2f} %"

        elif role == self.ROLE_TAG:
            return tag
        elif role == self.ROLE_DATA:
            return self.tagData[tag]

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

    def sort(self, column: int, order=Qt.SortOrder.AscendingOrder) -> None:
        defaultOrder = Qt.SortOrder.DescendingOrder
        match column:
            case 0:
                sortFunc = lambda tag: tag
                defaultOrder = Qt.SortOrder.AscendingOrder
            case 1:
                sortFunc = lambda tag: self.tagData[tag].count
            case 2:
                sortFunc = lambda tag: len(self.tagData[tag].files)

        reversed = (order != defaultOrder)

        self.layoutAboutToBeChanged.emit()
        self.tagOrder.sort(reverse=reversed, key=sortFunc)
        self.layoutChanged.emit()



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



class TagLayout(StatsBaseLayout):
    def __init__(self, tab: ImgTab, model, tableView, row=0):
        super().__init__(tab, "Tags", model, tableView, row)
    
    @override
    def getFiles(self, index: QModelIndex) -> list[str]:
        data = self.model.data(index, TagModel.ROLE_DATA)
        return data.files
