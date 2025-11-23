from typing_extensions import override
from PySide6.QtCore import Qt, Signal, Slot, QPoint, QSignalBlocker, QTimer, QModelIndex, QPersistentModelIndex, QObject
from PySide6.QtWidgets import QTableView, QHeaderView, QMenu
from PySide6.QtGui import QGuiApplication, QCursor, QWheelEvent, QKeyEvent
from ui.tab import ImgTab
from .gallery_caption import GalleryCaption
from .gallery_model import GalleryModel, FileItem, SelectionState
from .gallery_delegate import BaseGalleryDelegate, GalleryGridDelegate, GalleryListDelegate


class GalleryView(QTableView):
    VIEW_MODE_GRID = "grid"
    VIEW_MODE_LIST = "list"

    HEADER_HEIGHT = 32

    sortByImages = Signal(list)

    def __init__(self, tab: ImgTab, galleryCaption: GalleryCaption, initialItemWidth: int):
        super().__init__()
        self.tab = tab
        self.galleryCaption = galleryCaption
        self.itemWidth = initialItemWidth

        self.delegate: BaseGalleryDelegate = None
        self.visibleHeaderRows: set[int] = set()

        self._selectedItem: FileItem | None = None

        self.setShowGrid(False)
        self.setCornerButtonEnabled(False)

        self.horizontalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(200)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.verticalHeader().setCascadingSectionResizes(False)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        # self.verticalScrollBar().setSingleStep(1)
        # self.verticalScrollBar().setPageStep(1)
        self.verticalScrollBar().valueChanged.connect(self.updateVisibleRows)

        self.setUpdateThreshold(1000)

        self.setSelectionMode(self.SelectionMode.NoSelection)
        self._mouseHandler = GalleryMouseHandler(self)


    @override
    def model(self) -> GalleryModel:
        return super().model()

    @override
    def setModel(self, model: GalleryModel):
        if self.model() is not None:
            raise ValueError("GalleryModel already set")

        super().setModel(model)
        model.modelReset.connect(self._updateHeaderRows)


    def setViewMode(self, mode: str):
        with QSignalBlocker(self):
            self.setItemDelegate(None)
            if self.delegate:
                self.delegate.deleteLater()

            if mode == self.VIEW_MODE_GRID:
                self.delegate = GalleryGridDelegate(self, self.galleryCaption)
            else:
                self.delegate = GalleryListDelegate(self, self.galleryCaption)

            self.model().dataChanged.connect(self.delegate.onDataChanged)
            self.model().modelReset.connect(self.delegate.clearCache)
            self.setItemDelegate(self.delegate)

        self.updateColumnCount()


    def setItemWidth(self, width: int):
        if width != self.itemWidth:
            self.itemWidth = width
            self.updateColumnCount()
            QTimer.singleShot(0, self.updateVisibleRows)

    def updateColumnCount(self):
        spacing = self.delegate.spacing()
        numCols = (self.viewport().width() + spacing) // (self.delegate.itemWidth() + spacing)
        numCols = max(1, numCols)
        self.delegate.setNumColumns(numCols)
        self.model().setNumColumns(numCols, forceSignal=True)


    @Slot()
    def _updateHeaderRows(self):
        self.clearSpans()

        numCols = self.model().columnCount()
        if numCols > 1:
            for header in self.model().headerItems:
                self.setSpan(header.row, 0, 1, numCols)

        self.visibleHeaderRows.clear()
        self.updateVisibleRows()

    @Slot()
    def updateVisibleRows(self):
        r0, r1 = self._getVisibleRows()

        # Updating more than the visible rows breaks update of folder-combobox.
        # r0 = max(r0 - 2, 0)
        # r1 = min(r1 + 2, self.model().rowCount()-1)

        headerRows = set[int]()
        for row in range(r0, r1+1):
            if self.rowIsHeader(row):
                headerRows.add(row)
            else:
                self.resizeRowToContents(row)

        deactivate = self.visibleHeaderRows - headerRows
        for row in deactivate:
            self.closePersistentEditor(self.model().index(row, 0))

        activate = headerRows - self.visibleHeaderRows
        for row in activate:
            self.setRowHeight(row, self.HEADER_HEIGHT)
            self.openPersistentEditor(self.model().index(row, 0))

        self.visibleHeaderRows = headerRows

    def _getVisibleRows(self):
        topRow = self.getRowAtTop()
        bottomRow = topRow

        # Coarse search
        step = 5
        while self.rowIsVisible(bottomRow+step):
            bottomRow += step

        for bottomRow in range(bottomRow+1, bottomRow+step):
            if not self.rowIsVisible(bottomRow):
                bottomRow -= 1
                break

        return topRow, bottomRow


    def setResizing(self, state: bool):
        if state:
            for row in self.visibleHeaderRows:
                self.closePersistentEditor(self.model().index(row, 0))
            self.visibleHeaderRows.clear()
        else:
            self.updateColumnCount()


    @override
    def scrollTo(self, index: QModelIndex | QPersistentModelIndex, hint=QTableView.ScrollHint.PositionAtTop):
        # QTableView has automatic scrolling that happens when a partially visible item is made the current item.
        # It interferes with drag-selection, so disable it.
        if hint != QTableView.ScrollHint.EnsureVisible:
            return super().scrollTo(index, hint)

    def scrollToRow(self, row: int, alignHeader=True):
        if alignHeader:
            indexAbove = self.model().index(row-1, 0)
            if indexAbove.data(GalleryModel.ROLE_TYPE) == GalleryModel.ItemType.Header:
                self.scrollTo(indexAbove)
                return

        index = self.model().index(row, 0)
        self.scrollTo(index)

    def scrollToFile(self, file: str):
        item = self.model().getFileItem(file)
        if not (item is None or self.rowIsVisible(item.pos.row)):
            self.scrollToRow(item.pos.row)

    def getRowAtTop(self) -> int:
        index = self.indexAt(QPoint(0, 0))
        return index.row() if index.isValid() else -1

    def rowIsHeader(self, row: int) -> bool:
        index = self.model().index(row, 0)
        return index.data(GalleryModel.ROLE_TYPE) == GalleryModel.ItemType.Header

    def rowIsVisible(self, row: int) -> bool:
        index = self.model().index(row, 0)
        if index.isValid():
            return self.visualRect(index).intersects(self.rect())
        return False


    @override
    def wheelEvent(self, event: QWheelEvent):
        index = self.indexAt(QPoint(0, 0))
        if index.isValid():
            row = index.row()
            delta = event.angleDelta().y()

            # Scroll up
            if delta > 0:
                if self.visualRect(index).y() == 0:
                    row -= 1
                self.scrollToRow(row)

            # Scroll down
            elif delta < 0:
                row += 2 if self.rowIsHeader(row) else 1
                self.scrollToRow(row, alignHeader=False)

        event.accept()

    @override
    def keyPressEvent(self, event: QKeyEvent):
        filelist = self.tab.filelist
        match event.key():
            case Qt.Key.Key_Left:
                filelist.setPrevFile()
            case Qt.Key.Key_Right:
                filelist.setNextFile()
            case Qt.Key.Key_Up:
                filelist.setPrevFolder()
            case Qt.Key.Key_Down:
                filelist.setNextFolder()

            case Qt.Key.Key_Home:
                self.scrollToTop()
            case Qt.Key.Key_End:
                self.scrollToBottom()

            case _:
                super().keyPressEvent(event)
                return

        event.accept()



class GalleryMouseHandler(QObject):
    def __init__(self, view: GalleryView):
        super().__init__()
        self.view = view

        view.entered.connect(self._onMouseEntered)
        view.pressed.connect(self._onMousePressed)
        view.doubleClicked.connect(self._onMouseDoubleClick)


    @Slot(object)
    def _onMouseEntered(self, index: QModelIndex):
        if self.view.state() != self.view.State.DragSelectingState:
            return

        file = index.data(Qt.ItemDataRole.DisplayRole)
        if not file:
            return

        selection = index.data(GalleryModel.ROLE_SELECTION)
        if selection != SelectionState.Primary:
            if QGuiApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
                if selection == SelectionState.Secondary:
                    self.view.tab.filelist.unselectFile(file)
            elif selection != SelectionState.Secondary:
                self.view.tab.filelist.selectFile(file)


    @Slot(object)
    def _onMousePressed(self, index: QModelIndex):
        filelist = self.view.tab.filelist
        buttons = QGuiApplication.mouseButtons()

        file = index.data(Qt.ItemDataRole.DisplayRole)
        if not file:
            return

        if buttons == Qt.MouseButton.LeftButton:
            modifiers = QGuiApplication.keyboardModifiers()
            shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
            ctrl  = bool(modifiers & Qt.KeyboardModifier.ControlModifier)

            selection = index.data(GalleryModel.ROLE_SELECTION)

            # Secondary range selection
            if shift:
                if ctrl:
                    filelist.unselectFileRange(file)
                else:
                    filelist.selectFileRange(file)

            # Toggle secondary selection
            elif ctrl:
                if selection != SelectionState.Primary:
                    if selection == SelectionState.Secondary:
                        filelist.unselectFile(file)
                    else:
                        filelist.selectFile(file)

            # Select for comparison
            elif modifiers & Qt.KeyboardModifier.AltModifier:
                self.view.tab.mainWindow.setTool("compare")
                self.view.tab.imgview.tool.onGalleryRightClick(file)

            # Primary selection
            elif selection != SelectionState.Primary:
                with self.view.tab.takeFocus():
                    filelist.setCurrentFile(file)

        # Primary selection and open menu
        elif buttons == Qt.MouseButton.RightButton:
            with self.view.tab.takeFocus():
                filelist.setCurrentFile(file)

            menu = GalleryItemMenu(self.view)
            menu.exec(QCursor.pos())


    @Slot(object)
    def _onMouseDoubleClick(self, index: QModelIndex):
        buttons = QGuiApplication.mouseButtons()
        if buttons == Qt.MouseButton.LeftButton:
            self.view.tab.filelist.clearSelection()



class GalleryItemMenu(QMenu):
    def __init__(self, galleryView: GalleryView):
        super().__init__("Gallery")
        self.view = galleryView

        actClearSelection = self.addAction("Clear Selection")
        if galleryView.tab.filelist.selectedFiles:
            actClearSelection.triggered.connect(lambda: galleryView.tab.filelist.clearSelection())
            strFiles = "Files"
        else:
            actClearSelection.setEnabled(False)
            strFiles = "File"

        actSemanticSort = self.addAction(f"Sort by Similarity to Selected {strFiles}")
        actSemanticSort.triggered.connect(self._sortBySimilarity)

        actNewTab = self.addAction(f"Open Selected {strFiles} in New Tab")
        actNewTab.triggered.connect(self._openFilesInNewTab)

        self.addSeparator()

        actUnloadSelection = self.addAction(f"Unload Selected {strFiles}")
        actUnloadSelection.triggered.connect(self._unloadSelectedFiles)

    @Slot()
    def _sortBySimilarity(self):
        filelist = self.view.tab.filelist
        files = list(filelist.selectedFiles) if filelist.selectedFiles else [filelist.getCurrentFile()]
        self.view.sortByImages.emit(files)

    @Slot()
    def _openFilesInNewTab(self):
        filelist = self.view.tab.filelist
        files = filelist.selectedFiles or (filelist.getCurrentFile(),)
        newTab = self.view.tab.mainWindow.addTab()
        newTab.filelist.loadFilesFixed(files, filelist)

    @Slot()
    def _unloadSelectedFiles(self):
        filelist = self.view.tab.filelist
        if filelist.selectedFiles:
            filelist.filterFiles(lambda file: file not in filelist.selectedFiles)
        else:
            currentFile = filelist.getCurrentFile()
            filelist.filterFiles(lambda file: file != currentFile)
