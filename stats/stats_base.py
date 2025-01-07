from typing import Iterable
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QSortFilterProxyModel, QModelIndex, QItemSelection, QRegularExpression, QSignalBlocker
from ui.tab import ImgTab
import lib.qtlib as qtlib
from lib.filelist import sortKey


class StatsBaseProxyModel(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
    
    def getFiles(self, sourceIndex: QModelIndex) -> Iterable[str]:
        raise NotImplementedError



class StatsLayout(QtWidgets.QGridLayout):
    def __init__(self, tab: ImgTab, name: str, proxyModel: StatsBaseProxyModel, tableView: QtWidgets.QTableView, row=0):
        super().__init__()
        self.tab = tab
        self.proxyModel = proxyModel
        self.table = tableView

        self.setColumnMinimumWidth(0, 200)
        self.setColumnStretch(0, 0)
        self.setColumnStretch(1, 1)
        self.setColumnStretch(2, 2)

        rowSpan = 3
        self.setRowStretch(row, 0)
        self.addWidget(self._buildTableGroup(name), row, 1, rowSpan, 1)
        self.addWidget(self._buildFilesGroup(), row, 2, rowSpan, 1)

        row += 1
        self.setRowStretch(row, 0)
        self.addWidget(self._buildFilterGroup(), row, 0)

        row += 1
        self.setRowStretch(row, 1)


    def _buildTableGroup(self, name: str):
        layout = QtWidgets.QVBoxLayout()

        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QtWidgets.QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QTableView.SelectionMode.SingleSelection) # TODO: Allow multi-selection and combine files (Union, Intersection...)
        self.table.resizeColumnsToContents()
        self.table.selectionModel().selectionChanged.connect(self._onRowSelected)
        self.proxyModel.modelReset.connect(self.clearSelection)
        layout.addWidget(self.table)

        group = QtWidgets.QGroupBox(name)
        group.setLayout(layout)
        return group

    def _buildFilesGroup(self):
        layout = QtWidgets.QVBoxLayout()

        self.listFiles = QtWidgets.QListWidget()
        qtlib.setMonospace(self.listFiles)
        self.listFiles.currentItemChanged.connect(self._onFileSelected)
        layout.addWidget(self.listFiles)

        group = QtWidgets.QGroupBox("Files")
        group.setLayout(layout)
        return group

    def _buildFilterGroup(self):
        layout = QtWidgets.QVBoxLayout()

        self.txtFilter = QtWidgets.QLineEdit()
        self.txtFilter.setPlaceholderText("Regex pattern")
        self.txtFilter.textChanged.connect(self._onFilterChanged)
        layout.addWidget(self.txtFilter)

        btnClearFilter = QtWidgets.QPushButton("Clear")
        btnClearFilter.clicked.connect(lambda: self.txtFilter.setText(""))
        layout.addWidget(btnClearFilter)

        group = QtWidgets.QGroupBox("Filter")
        group.setLayout(layout)
        return group


    @Slot()
    def clearSelection(self):
        selectionModel = self.table.selectionModel()
        selectionModel.clear()
        selection = QItemSelection()
        selectionModel.selectionChanged.emit(selection, selection)

    @Slot()
    def _onRowSelected(self, newItem: QItemSelection, oldItem: QItemSelection):
        self.listFiles.clear()
        if newItem.isEmpty():
            return

        index = newItem.indexes()[0]
        index = self.proxyModel.mapToSource(index)

        files = self.proxyModel.getFiles(index)
        files = sorted(files, key=sortKey)

        for file in files:
            path = self.tab.filelist.removeCommonRoot(file)
            item = QtWidgets.QListWidgetItem(path)
            item.setData(Qt.ItemDataRole.UserRole, file)
            self.listFiles.addItem(item)

    @Slot()
    def _onFileSelected(self, currentItem: QtWidgets.QListWidgetItem | None, prevItem: QtWidgets.QListWidgetItem):
        if currentItem:
            file: str = currentItem.data(Qt.ItemDataRole.UserRole)
            self.tab.filelist.setCurrentFile(file)

    @Slot()
    def _onFilterChanged(self, text: str):
        regex = QRegularExpression(text, QRegularExpression.PatternOption.CaseInsensitiveOption)
        if not regex.isValid():
            self.txtFilter.setStyleSheet("color: red")
            return

        self.txtFilter.setStyleSheet(None)

        # When filter only shows 1 row, it doesn't display files. Clear selection as a workaround.
        # Disable signals as they mess things up and select new files during update.
        with QSignalBlocker(self.listFiles):
            with QSignalBlocker(self.table.selectionModel()):
                self.table.selectionModel().clear()
                self.proxyModel.setFilterRegularExpression(regex)
