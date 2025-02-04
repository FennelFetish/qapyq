from typing import Iterable, Generator
from collections import Counter
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

        self.groupFiles = self._buildFilesGroup(name)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(col1Widget)
        splitter.addWidget(self._buildTableGroup(name))
        splitter.addWidget(self.groupFiles)
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

        row = 0
        layout.addWidget(QtWidgets.QLabel("List files with:"), row, 0)

        self.cboCombineMode = QtWidgets.QComboBox()
        self.cboCombineMode.addItem("Any (Union)", CombineModeUnion)
        self.cboCombineMode.setItemData(0, f"List images which have at least one of the selected {name}", Qt.ItemDataRole.ToolTipRole)
        self.cboCombineMode.addItem("One", CombineModeExclusive)
        self.cboCombineMode.setItemData(1, f"List images which have exactly one of the selected {name}", Qt.ItemDataRole.ToolTipRole)
        self.cboCombineMode.addItem("Multiple", CombineModeMultiple)
        self.cboCombineMode.setItemData(2, f"List images which have more than one of the selected {name}", Qt.ItemDataRole.ToolTipRole)
        self.cboCombineMode.addItem("All (Intersection)", CombineModeIntersection)
        self.cboCombineMode.setItemData(3, f"List images which have all selected {name}", Qt.ItemDataRole.ToolTipRole)

        self.cboCombineMode.currentIndexChanged.connect(self.updateSelection)
        layout.addWidget(self.cboCombineMode, row, 1)

        self.chkFilesNegate = QtWidgets.QCheckBox("Negate")
        self.chkFilesNegate.setToolTip(f"List only images that would be hidden with the selected {name} and listing mode")
        self.chkFilesNegate.checkStateChanged.connect(self.updateSelection)
        layout.addWidget(self.chkFilesNegate, row, 2)

        layout.setColumnStretch(3, 1)

        self.btnWithFiles = QtWidgets.QPushButton("With Files...")
        self.btnWithFiles.setMinimumWidth(100)
        self.btnWithFiles.setMenu(self._buildFilesMenu(self.btnWithFiles))
        layout.addWidget(self.btnWithFiles, row, 4)

        row += 1
        self.listFiles = QtWidgets.QListWidget()
        self.listFiles.setAlternatingRowColors(True)
        qtlib.setMonospace(self.listFiles)
        self.listFiles.selectionModel().selectionChanged.connect(self._onFileSelected)
        layout.addWidget(self.listFiles, row, 0, 1, 5)

        group = QtWidgets.QGroupBox("Files")
        group.setLayout(layout)
        return group

    def _buildFilesMenu(self, parent) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu("Files", parent)

        actOpenInNewTab = menu.addAction("Open in New Tab")
        actOpenInNewTab.triggered.connect(self._loadFilesInNewTab)

        actRemove = menu.addAction("Unload")
        actRemove.triggered.connect(self._unloadFiles)

        return menu

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

    def getSelectedSourceIndexes(self):
        selectedIndexes = self.table.selectionModel().selectedIndexes()
        for index in (idx for idx in selectedIndexes if idx.column() == 0):
            yield self.proxyModel.mapToSource(index)

    @Slot()
    def _onRowsSelected(self, newItem: QItemSelection, oldItem: QItemSelection):
        combineClass = self.cboCombineMode.currentData()
        combiner = combineClass()

        for srcIndex in self.getSelectedSourceIndexes():
            combiner.addFiles( self.proxyModel.getFiles(srcIndex) )

        fileSet = combiner.getFiles()
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

        self.groupFiles.setTitle(f"Files ({len(files)})")


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
            # Also disable focus change to enable navigating through the file list with arrow keys.
            self.tab.imgview.takeFocusOnFilechange = False
            self.tab.filelist.setCurrentFile(file)
        finally:
            self._enableFileUpdate = True
            self.tab.imgview.takeFocusOnFilechange = True

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


    def getListedFiles(self) -> Generator[str, None, None] | None:
        if self.listFiles.count() == 0:
            return None
        return (self.listFiles.item(row).data(self.ROLE_FILEPATH) for row in range(self.listFiles.count()))

    @Slot()
    def _loadFilesInNewTab(self) -> ImgTab | None:
        filesGen = self.getListedFiles()
        if filesGen is None:
            return None

        currentFilelist = self.tab.filelist
        newTab = self.tab.mainWindow.addTab()
        newFilelist: FileList = newTab.filelist
        newFilelist.loadFilesFixed(filesGen, currentFilelist)
        return newTab

    @Slot()
    def _unloadFiles(self):
        filesGen = self.getListedFiles()
        if filesGen is None:
            return

        confirmText = f"Unloading the files will discard all unsaved modifications to captions and masks. Do you really want to unload the listed files?"
        dialog = QtWidgets.QMessageBox(self.btnWithFiles)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Question)
        dialog.setWindowTitle("Confirm Unloading Files")
        dialog.setText(confirmText)
        dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok | QtWidgets.QMessageBox.StandardButton.Cancel)

        if dialog.exec() == QtWidgets.QMessageBox.StandardButton.Ok:
            filesSet = set(filesGen)
            self.tab.filelist.filterFiles(lambda file: file not in filesSet)
            # TODO: Reload data and restore selection



class CombineModeUnion:
    def __init__(self):
        self.fileSet: set[str] = set()

    def addFiles(self, files: Iterable[str]):
        self.fileSet.update(files)

    def getFiles(self) -> set[str]:
        return self.fileSet


class CombineModeIntersection:
    def __init__(self):
        self.fileSet: set[str] = set()
        self.first = True

    def addFiles(self, files: Iterable[str]):
        if self.first:
            self.fileSet.update(files)
            self.first = False
        else:
            self.fileSet.intersection_update(files)

    def getFiles(self) -> set[str]:
        return self.fileSet


class CombineModeExclusive:
    def __init__(self):
        self.fileCounter: Counter[str] = Counter()

    def addFiles(self, files: Iterable[str]):
        self.fileCounter.update(files)

    def getFiles(self) -> set[str]:
        return set(f for f, count in self.fileCounter.items() if count == 1)


class CombineModeMultiple:
    def __init__(self):
        self.fileCounter: Counter[str] = Counter()

    def addFiles(self, files: Iterable[str]):
        self.fileCounter.update(files)

    def getFiles(self) -> set[str]:
        return set(f for f, count in self.fileCounter.items() if count > 1)
