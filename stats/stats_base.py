from typing import Iterable
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QSortFilterProxyModel, QModelIndex, QItemSelection, QRegularExpression, QSignalBlocker
from ui.tab import ImgTab
import lib.qtlib as qtlib
from lib.filelist import FileList, DataKeys
from lib.filelist import sortKey


# TODO: Context menu "copy cell content" for all tabs


class StatsBaseProxyModel(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
    
    def getFiles(self, sourceIndex: QModelIndex) -> Iterable[str]:
        raise NotImplementedError



class StatsLayout(QtWidgets.QVBoxLayout):
    ROLE_FILEPATH = Qt.ItemDataRole.UserRole

    def __init__(self, tab: ImgTab, name: str, proxyModel: StatsBaseProxyModel, tableView: QtWidgets.QTableView, row=0):
        super().__init__()
        self.tab = tab
        self.proxyModel = proxyModel
        self.table = tableView

        self._enableFileUpdate = True

        self._build(name)

    def _build(self, name: str):
        self.col1Layout = QtWidgets.QVBoxLayout()
        self.col1Layout.setContentsMargins(0, 0, 0, 0)
        self.col1Layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.col1Layout.addWidget(self._buildFilterGroup(name))

        col1Widget = QtWidgets.QWidget()
        col1Widget.setLayout(self.col1Layout)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(col1Widget)
        splitter.addWidget(self._buildTableGroup(name))
        splitter.addWidget(self._buildFilesGroup(name))
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)
        self.addWidget(splitter)

    def _buildTableGroup(self, name: str):
        layout = QtWidgets.QVBoxLayout()

        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QtWidgets.QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QTableView.SelectionMode.ExtendedSelection)
        self.table.resizeColumnsToContents()
        self.table.selectionModel().selectionChanged.connect(self._onRowsSelected)
        self.proxyModel.modelReset.connect(self.clearSelection)
        layout.addWidget(self.table)

        group = QtWidgets.QGroupBox(name)
        group.setLayout(layout)
        return group

    def _buildFilesGroup(self, name: str):
        layout = QtWidgets.QGridLayout()
        layout.setColumnMinimumWidth(2, 4)
        layout.setColumnStretch(4, 1)
        layout.setColumnMinimumWidth(6, 4)

        row = 0
        self.radioFilesUnion = QtWidgets.QRadioButton(f"Union")
        self.radioFilesUnion.setToolTip(f"Show files which have at least one of the selected {name}")
        self.radioFilesUnion.setChecked(True)
        self.radioFilesUnion.clicked.connect(self.updateSelection)
        layout.addWidget(self.radioFilesUnion, row, 0)

        self.radioFilesIntersect = QtWidgets.QRadioButton(f"Intersection")
        self.radioFilesIntersect.setToolTip(f"Show files which have all selected {name}")
        self.radioFilesIntersect.clicked.connect(self.updateSelection)
        layout.addWidget(self.radioFilesIntersect, row, 1)

        self.chkFilesNegate = QtWidgets.QCheckBox("Negate")
        self.chkFilesNegate.setToolTip(f"Show files which lack the Union/Intersection of the selected {name}")
        self.chkFilesNegate.checkStateChanged.connect(self.updateSelection)
        layout.addWidget(self.chkFilesNegate, row, 3)

        self.lblNumFilesListed = QtWidgets.QLabel("0 Files")
        layout.addWidget(self.lblNumFilesListed, row, 5)

        btnNewTab = QtWidgets.QPushButton("Open Files in New Tab")
        btnNewTab.setMinimumWidth(160)
        btnNewTab.clicked.connect(self._loadFilesInNewTab)
        layout.addWidget(btnNewTab, row, 7)

        row += 1
        self.listFiles = QtWidgets.QListWidget()
        self.listFiles.setAlternatingRowColors(True)
        qtlib.setMonospace(self.listFiles)
        self.listFiles.selectionModel().selectionChanged.connect(self._onFileSelected)
        layout.addWidget(self.listFiles, row, 0, 1, 8)

        group = QtWidgets.QGroupBox("Files")
        group.setLayout(layout)
        return group

    def _buildFilterGroup(self, name: str):
        layout = QtWidgets.QVBoxLayout()

        self.txtFilter = QtWidgets.QLineEdit()
        self.txtFilter.setPlaceholderText("Regex pattern")
        self.txtFilter.textChanged.connect(self._onFilterChanged)
        layout.addWidget(self.txtFilter)

        btnClearFilter = QtWidgets.QPushButton("Clear")
        btnClearFilter.clicked.connect(lambda: self.txtFilter.setText(""))
        layout.addWidget(btnClearFilter)

        group = QtWidgets.QGroupBox(f"Filter {name}")
        group.setLayout(layout)
        return group

    def setStatsWidget(self, widget: QtWidgets.QWidget):
        self.col1Layout.insertWidget(0, widget)


    @Slot()
    def clearSelection(self):
        selectionModel = self.table.selectionModel()
        selectionModel.clear()
        selection = QItemSelection()
        selectionModel.selectionChanged.emit(selection, selection)

    @Slot()
    def updateSelection(self):
        self._onRowsSelected(None, None)

    @Slot()
    def _onRowsSelected(self, newItem: QItemSelection, oldItem: QItemSelection):
        fileSet = set()
        union = self.radioFilesUnion.isChecked()
        first = True
        selectedIndexes = self.table.selectionModel().selectedIndexes()
        for index in selectedIndexes:
            if index.column() != 0:
                continue

            index = self.proxyModel.mapToSource(index)
            rowFiles = self.proxyModel.getFiles(index)

            if union or first:
                fileSet.update(rowFiles)
                first = False
            else:
                fileSet.intersection_update(rowFiles)

        if self.chkFilesNegate.isChecked():
            fileSet = [file for file in self.tab.filelist.getFiles() if file not in fileSet]

        files = sorted(fileSet, key=sortKey)

        with QSignalBlocker(self.listFiles.selectionModel()):
            self.listFiles.clear()
            for file in files:
                path = self.tab.filelist.removeCommonRoot(file)
                item = QtWidgets.QListWidgetItem(path)
                item.setData(self.ROLE_FILEPATH, file)
                self.listFiles.addItem(item)

        numFilesText = f"{len(files)} File"
        if len(files) != 1:
            numFilesText += "s"
        self.lblNumFilesListed.setText(numFilesText)


    @Slot()
    def _onFileSelected(self, selected: QItemSelection, deselected: QItemSelection):
        if selected.isEmpty():
            return

        index = selected.indexes()[0]
        currentItem = self.listFiles.itemFromIndex(index)
        file: str = currentItem.data(self.ROLE_FILEPATH)

        try:
            # Changing file normally clears the selection, so disable that.
            self._enableFileUpdate = False
            self.tab.filelist.setCurrentFile(file)
        finally:
            self._enableFileUpdate = True

    def clearFileSelection(self):
        if self._enableFileUpdate:
            self.listFiles.clearSelection()


    @Slot()
    def _onFilterChanged(self, text: str):
        regex = QRegularExpression(text, QRegularExpression.PatternOption.CaseInsensitiveOption)
        if not regex.isValid():
            self.txtFilter.setStyleSheet("color: red")
            return

        self.txtFilter.setStyleSheet(None)

        # When filter only shows 1 row, it doesn't display files. Clear selection as a workaround.
        # Disable signals as they mess things up and select new files during update.
        with QSignalBlocker(self.table.selectionModel()):
            self.table.selectionModel().clear()
            self.proxyModel.setFilterRegularExpression(regex)

    @Slot()
    def _loadFilesInNewTab(self):
        files = [self.listFiles.item(row).data(self.ROLE_FILEPATH) for row in range(self.listFiles.count())]
        if files:
            currentFilelist = self.tab.filelist
            newTab = self.tab.mainWindow.addTab()
            newFilelist: FileList = newTab.filelist
            newFilelist.loadFilesFixed(files, currentFilelist, [DataKeys.ImageSize, DataKeys.Thumbnail])
