from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QAbstractItemModel, QModelIndex, QItemSelection
from ui.tab import ImgTab
from lib.filelist import sortKey


class StatsBaseLayout(QtWidgets.QGridLayout):
    def __init__(self, tab: ImgTab, name: str, model: QAbstractItemModel, tableView: QtWidgets.QTableView, row=0):
        super().__init__()
        self.tab = tab
        self.model = model
        self.table = tableView

        self.setColumnMinimumWidth(0, 200)
        self.setColumnStretch(0, 0)
        self.setColumnStretch(1, 1)
        self.setColumnStretch(2, 2)

        self.setRowStretch(row, 0)
        self.setRowStretch(row+1, 1)

        self.addWidget(self._buildTableGroup(name), row, 1, 2, 1)
        self.addWidget(self._buildFilesGroup(), row, 2, 2, 1)


    def _buildTableGroup(self, name: str):
        layout = QtWidgets.QVBoxLayout()

        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QtWidgets.QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QTableView.SelectionMode.SingleSelection) # TODO: Allow multi-selection and combine files (Union, Intersection...)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.table.selectionModel().selectionChanged.connect(self._onRowSelected)
        layout.addWidget(self.table)

        group = QtWidgets.QGroupBox(name)
        group.setLayout(layout)
        return group

    def _buildFilesGroup(self):
        layout = QtWidgets.QVBoxLayout()

        self.listFiles = QtWidgets.QListWidget()
        self.listFiles.currentTextChanged.connect(self._onFileSelected)
        layout.addWidget(self.listFiles)

        group = QtWidgets.QGroupBox("Files")
        group.setLayout(layout)
        return group


    # TODO: Deselect on reload
    @Slot()
    def _onRowSelected(self, newItem: QItemSelection, oldItem: QItemSelection):
        self.listFiles.clear()
        if newItem.isEmpty():
            return

        index = newItem.indexes()[0]
        files = self.getFiles(index)
        files = sorted(files, key=sortKey)
        self.listFiles.addItems(files)
        # TODO: Find longest common root of all paths and only display relative to it (implement in FileList)

    @Slot()
    def _onFileSelected(self, file: str):
        if file:
            self.tab.filelist.setCurrentFile(file)


    def getFiles(self, index: QModelIndex) -> list[str]:
        raise NotImplementedError()
