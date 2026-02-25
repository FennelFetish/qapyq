from typing import Iterable
from typing_extensions import override
from PySide6 import QtWidgets
from PySide6.QtWidgets import QTableView, QHeaderView
from PySide6.QtCore import Qt, Signal, Slot, QPoint, QSignalBlocker, QTimer, QModelIndex, QPersistentModelIndex, QObject, QMimeData, QUrl
from PySide6.QtGui import QGuiApplication, QCursor, QWheelEvent, QKeyEvent, QMouseEvent, QDrag
from ui.tab import ImgTab
from .gallery_caption import GalleryCaption
from .gallery_model import GalleryModel, FileItem, SelectionState
from .gallery_delegate import GalleryDelegate, GalleryGridDelegate, GalleryListDelegate


class GalleryView(QTableView):
    VIEW_MODE_GRID = "grid"
    VIEW_MODE_LIST = "list"

    sortByImages = Signal(list)

    def __init__(self, tab: ImgTab, galleryCaption: GalleryCaption, initialItemWidth: int):
        super().__init__()
        self.tab = tab
        self.galleryCaption = galleryCaption
        self.itemWidth = initialItemWidth

        self.delegate: GalleryDelegate = None
        self.editorRows: set[int] = set()

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
        self.verticalScrollBar().valueChanged.connect(self.updateVisibleRows)

        self.setUpdateThreshold(1000)

        self.setSelectionMode(self.SelectionMode.NoSelection)
        self._mouseHandler = GalleryMouseHandler(self)


    @override
    def deleteLater(self):
        if self.delegate:
            self.setItemDelegate(None)
            self.delegate.view = None
            self.delegate.deleteLater()
            self.delegate = None

        return super().deleteLater()


    @override
    def model(self) -> GalleryModel:
        return super().model()

    @override
    def setModel(self, model: GalleryModel):
        if self.model() is not None:
            raise ValueError("GalleryModel already set")

        super().setModel(model)
        model.modelReset.connect(self._onModelReset)


    def setViewMode(self, mode: str):
        with QSignalBlocker(self):
            self.setItemDelegate(None)
            if self.delegate:
                highlightState = self.delegate.highlightState
                self.delegate.deleteLater()
            else:
                highlightState = None

            if mode == self.VIEW_MODE_GRID:
                self.delegate = GalleryGridDelegate(self, self.galleryCaption, highlightState)
            else:
                self.delegate = GalleryListDelegate(self, self.galleryCaption, highlightState)

            self.model().dataChanged.connect(self.delegate.onDataChanged)
            self.setItemDelegate(self.delegate)

        self.updateColumnCount()


    def setItemWidth(self, width: int):
        if width != self.itemWidth:
            self.itemWidth = width
            self.updateColumnCount()

    def updateColumnCount(self):
        spacing = self.delegate.spacing()
        numCols = (self.viewport().width() + spacing) // (self.delegate.itemWidth() + spacing)
        numCols = max(1, numCols)
        self.delegate.setNumColumns(numCols)
        self.model().setNumColumns(numCols, forceReset=True)


    @Slot()
    def _onModelReset(self):
        self.delegate.clearCache()

        # Update header rows
        self.clearSpans()
        numCols = self.model().columnCount()
        if numCols > 1:
            for header in self.model().headerItems:
                self.setSpan(header.row, 0, 1, numCols)

        self.editorRows.clear()
        self.updateVisibleRows()

        # Ensure top row has no header above
        self.scrollToRow(self.rowAt(0))

        QTimer.singleShot(100, self.updateVisibleRows)


    @Slot()
    def updateVisibleRows(self):
        editorRows = set[int]()
        for row, isHeader in self.visibleRows():
            if self.delegate.rowNeedsEditor(isHeader):
                editorRows.add(row)

            self.resizeRowToContents(row)

        deactivate = self.editorRows - editorRows
        for row in deactivate:
            self.delegate.closeRowEditors(row)

        activate = editorRows - self.editorRows
        for row in activate:
            self.delegate.openRowEditors(row)

        self.editorRows = editorRows

    def visibleRows(self) -> Iterable[tuple[int, bool]]:
        model = self.model()
        rect  = self.rect()

        index = self.indexAt(QPoint(0, 0))
        while index.isValid() and self.visualRect(index).intersects(rect):
            isHeader = index.data(GalleryModel.ROLE_TYPE) == GalleryModel.ItemType.Header
            yield index.row(), isHeader
            index = model.index(index.row()+1, 0)


    def setResizing(self, state: bool):
        self.delegate.fastRender = state

        if state:
            for row in self.editorRows:
                self.delegate.closeRowEditors(row)
            self.editorRows.clear()
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
            #QTimer.singleShot(100, self.updateVisibleRows)

    def rowIsVisible(self, row: int) -> bool:
        index = self.model().index(row, 0)
        if index.isValid():
            itemRect = self.visualRect(index)
            visibleRect = itemRect.intersected(self.rect())
            return visibleRect.height() > 0.75 * itemRect.height()

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
                isHeader = index.data(GalleryModel.ROLE_TYPE) == GalleryModel.ItemType.Header
                row += 2 if isHeader else 1
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



# TODO: Right-click shouldn't select image but only open context menu.
class GalleryMouseHandler(QObject):
    def __init__(self, view: GalleryView):
        super().__init__(view)
        self.view = view

        view.entered.connect(self._onMouseEntered)
        view.pressed.connect(self._onMousePressed)
        view.doubleClicked.connect(self._onMouseDoubleClick)


    @Slot(QModelIndex)
    def _onMouseEntered(self, index: QModelIndex):
        if self.view.state() != self.view.State.DragSelectingState:
            return

        file = index.data(GalleryModel.ROLE_FILEPATH)
        if not file:
            return

        selection = index.data(GalleryModel.ROLE_SELECTION)
        if selection != SelectionState.Primary:
            if QGuiApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
                if selection == SelectionState.Secondary:
                    self.view.tab.filelist.unselectFile(file)
            elif selection != SelectionState.Secondary:
                self.view.tab.filelist.selectFile(file)


    @Slot(QModelIndex)
    def _onMousePressed(self, index: QModelIndex):
        filelist = self.view.tab.filelist
        buttons = QGuiApplication.mouseButtons()

        file = index.data(GalleryModel.ROLE_FILEPATH)
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


    @Slot(QModelIndex)
    def _onMouseDoubleClick(self, index: QModelIndex):
        buttons = QGuiApplication.mouseButtons()
        if buttons == Qt.MouseButton.LeftButton:
            self.view.tab.filelist.clearSelection()



class GalleryItemMenu(QtWidgets.QMenu):
    def __init__(self, galleryView: GalleryView):
        super().__init__("Gallery")
        self.view = galleryView

        actClearSelection = self.addAction("Clear Selection")
        numSelected = len(galleryView.tab.filelist.selectedFiles)
        if numSelected > 0:
            actClearSelection.triggered.connect(lambda: galleryView.tab.filelist.clearSelection())
            strFiles = f"Files ({numSelected})"
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

        self.addSeparator()

        dragStartWidget = DragStartWidget(f"Drag {strFiles}")
        dragStartWidget.dragStarted.connect(self._startDragFiles)

        actDrag = QtWidgets.QWidgetAction(self)
        actDrag.setDefaultWidget(dragStartWidget)
        self.addAction(actDrag)


    @Slot()
    def _sortBySimilarity(self):
        filelist = self.view.tab.filelist
        files = list(filelist.selectedFiles) if filelist.selectedFiles else [filelist.getCurrentFile()]
        self.view.sortByImages.emit(files)

    @Slot()
    def _openFilesInNewTab(self):
        filelist = self.view.tab.filelist
        files = filelist.selectedFiles or (filelist.getCurrentFile(),)
        newTab: ImgTab = self.view.tab.mainWindow.addTab()
        newTab.filelist.loadFilesFixed(files, filelist)

    @Slot()
    def _unloadSelectedFiles(self):
        filelist = self.view.tab.filelist
        if filelist.selectedFiles:
            filelist.filterFiles(lambda file: file not in filelist.selectedFiles)
        else:
            currentFile = filelist.getCurrentFile()
            filelist.filterFiles(lambda file: file != currentFile)

    @Slot()
    def _startDragFiles(self):
        self.close()

        filelist = self.view.tab.filelist
        if filelist.selectedFiles:
            urls = [QUrl.fromLocalFile(file) for file in filelist.selection.sorted]
        elif filelist.getCurrentFile():
            urls = [QUrl.fromLocalFile(filelist.getCurrentFile())]
        else:
            return

        data = QMimeData()
        data.setUrls(urls)

        # Set the source to GalleryView, otherwise file managers won't receive the drag.
        drag = QDrag(self.view)
        drag.setMimeData(data)
        drag.exec(Qt.DropAction.CopyAction)



class DragStartWidget(QtWidgets.QWidget):
    dragStarted = Signal()

    def __init__(self, text: str):
        super().__init__()
        self.setToolTip("Drag from here to copy the selected files into another application.")
        self.setCursor(Qt.CursorShape.DragCopyCursor)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 1, 1, 1)
        layout.setSpacing(0)
        layout.setColumnMinimumWidth(0, 28)
        layout.setColumnMinimumWidth(2, 6)
        layout.setColumnStretch(3, 1)

        labelIcon = QtWidgets.QLabel("🡸")
        labelIcon.setContentsMargins(11, 4, 0, 0)
        layout.addWidget(labelIcon, 0, 0)

        label = QtWidgets.QLabel(text)
        layout.addWidget(label, 0, 1)

        label2 = QtWidgets.QLabel("(Click and hold)")
        label2.setEnabled(False)
        layout.addWidget(label2, 0, 3)

        self.setLayout(layout)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragStarted.emit()
            event.accept()
        else:
            super().mousePressEvent(event)
