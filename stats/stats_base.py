import os
from typing import Iterable, Generator
from collections import Counter
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QSortFilterProxyModel, QModelIndex, QItemSelection, QRegularExpression, QSignalBlocker
from ui.tab import ImgTab
import lib.qtlib as qtlib
from lib.filelist import FileList, sortKey
from config import Config


# TODO: Context menu "copy cell content" for all tabs


class StatsBaseProxyModel(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()

    def getFiles(self, sourceIndex: QModelIndex) -> Iterable[str]:
        raise NotImplementedError



class StatsLayout(QtWidgets.QVBoxLayout):
    ROLE_FILEPATH = Qt.ItemDataRole.UserRole

    def __init__(self, tab: ImgTab, name: str, proxyModel: StatsBaseProxyModel, view: QtWidgets.QTableView | QtWidgets.QTreeView, row=0):
        super().__init__()
        self.tab = tab
        self.name = name
        self.proxyModel = proxyModel
        self.view = view

        self._enableFileUpdate = True

        self._build(name)

        if isinstance(view, QtWidgets.QTableView):
            view.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
            view.verticalHeader().setVisible(False)
            view.resizeColumnsToContents()


    def _build(self, name: str):
        self.col1Layout = QtWidgets.QVBoxLayout()
        self.col1Layout.setContentsMargins(0, 0, 0, 0)
        self.col1Layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.col1Layout.addWidget(self._buildFilterGroup(name))
        self.col1Layout.addWidget(self._buildExportGroup())

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

        self.view.setAlternatingRowColors(True)
        self.view.setSortingEnabled(True)
        self.view.setSelectionBehavior(QtWidgets.QTableView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QtWidgets.QTableView.SelectionMode.ExtendedSelection)
        self.view.selectionModel().selectionChanged.connect(self._onRowsSelected)
        self.proxyModel.modelReset.connect(self.clearSelection)
        layout.addWidget(self.view)

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

    def _buildExportGroup(self):
        layout = QtWidgets.QVBoxLayout()

        btnExportCsv = QtWidgets.QPushButton("Export CSV...")
        btnExportCsv.clicked.connect(self._exportCsv)
        layout.addWidget(btnExportCsv)

        group = QtWidgets.QGroupBox(f"Export Data")
        group.setLayout(layout)
        return group


    def setStatsWidget(self, widget: QtWidgets.QWidget):
        self.col1Layout.insertWidget(0, widget)


    @Slot()
    def clearSelection(self):
        selectionModel = self.view.selectionModel()
        selectionModel.clear()
        selection = QItemSelection()
        selectionModel.selectionChanged.emit(selection, selection)

    @Slot()
    def updateSelection(self):
        self._onRowsSelected(None, None)

    def getSelectedSourceIndexes(self):
        selectedIndexes = self.view.selectionModel().selectedIndexes()
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
            self.txtFilter.setStyleSheet(f"color: {qtlib.COLOR_RED}")
            return

        self.txtFilter.setStyleSheet(None)

        # When filter only shows 1 row, it doesn't display files. Clear selection as a workaround.
        # Disable signals as they mess things up and select new files during update.
        with QSignalBlocker(self.view.selectionModel()):
            self.view.selectionModel().clear()
            self.proxyModel.setFilterRegularExpression(regex)


    @Slot()
    def _exportCsv(self):
        name = self.name.replace(" ", "").lower()
        topDir = os.path.basename(self.tab.filelist.commonRoot)
        topDir = topDir.replace(" ", "").replace(":", "").lower()
        if topDir:
            name = f"{topDir}-{name}"
        ExportCsv.export(name, self.proxyModel, self.view)


    def getListedFiles(self) -> Generator[str, None, None] | None:
        if self.listFiles.count() == 0:
            return None
        return (self.listFiles.item(row).data(self.ROLE_FILEPATH) for row in range(self.listFiles.count()))

    def hasListedFiles(self) -> bool:
        return self.listFiles.count() > 0

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
        dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)

        if dialog.exec() == QtWidgets.QMessageBox.StandardButton.Yes:
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



class ExportCsv:
    ROLE_CSV = Qt.ItemDataRole.UserRole + 1000

    @classmethod
    def export(cls, filename: str, model: StatsBaseProxyModel, parentWidget: QtWidgets.QWidget):
        filter = "CSV Files (*.csv)"
        path = os.path.join(Config.pathExport, f"{filename}.csv")
        path, filter = QtWidgets.QFileDialog.getSaveFileName(parentWidget, "Choose destination file", path, filter)
        if not path:
            return

        path = os.path.abspath(path)
        print(f"Writing CSV data to: {path}")
        cls.writeData(path, model)


    @classmethod
    def writeData(cls, path: str, model: StatsBaseProxyModel):
        import csv
        with open(path, 'w', newline='') as csvFile:
            writer = csv.writer(csvFile)
            writer.writerow((
                model.headerData(col, Qt.Orientation.Horizontal)
                for col in range(model.columnCount())
            ))

            cls.writeRows(writer, model, QModelIndex())


    @classmethod
    def writeRows(cls, writer, model: StatsBaseProxyModel, parent: QModelIndex):
        for row in range(model.rowCount(parent)):
            writer.writerow((
                model.data(model.index(row, col, parent), cls.ROLE_CSV)
                for col in range(model.columnCount(parent))
            ))

            # Recurse
            child = model.index(row, 0, parent)
            if model.hasChildren(child):
                cls.writeRows(writer, model, child)
