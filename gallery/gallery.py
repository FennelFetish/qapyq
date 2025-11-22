import time
from bisect import bisect_right
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QSignalBlocker, QTimer
import lib.qtlib as qtlib
from lib.captionfile import FileTypeSelector
from ui.tab import ImgTab
from config import Config
from .gallery_model import GalleryModel, HeaderItem
from .gallery_view import GalleryView
from .gallery_sort import GallerySortControl


class Gallery(QtWidgets.QWidget):
    MIN_GRID_UPDATE_DELAY = 1.0
    THUMBNAIL_SIZE_STEP = 50

    def __init__(self, tab: ImgTab):
        super().__init__()
        self.tab = tab

        self.rowToHeader: list[int] = list()
        self._switchingMode = False

        # Initialize grid after delay: Wait for the window width to calculate column count
        self._initTimer = QTimer(singleShot=True, interval=50)
        self._initTimer.timeout.connect(self._initGrid)

        self._gridUpdateTimer = QTimer(singleShot=True, interval=100)
        self._gridUpdateTimer.timeout.connect(self.updateGrid)
        self._lastGridUpdate = 0

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(self._buildTopRow())

        self.galleryView: GalleryView = GalleryView(tab, Config.galleryThumbnailSize)
        self.galleryView.verticalScrollBar().valueChanged.connect(self.updateComboboxFolder)
        layout.addWidget(self.galleryView)

        self.galleryModel = GalleryModel(tab.filelist)
        self.galleryModel.view = self.galleryView
        self.galleryView.setModel(self.galleryModel)
        self.galleryModel.modelReset.connect(self.galleryView.updateFolderRows)

        # self.sortControl = GallerySortControl(self.tab, self.galleryGrid)
        # layout.addWidget(self.sortControl)
        # self.galleryGrid.ctx.gallerySort = self.sortControl

        self._buildStatusBar()
        self.setLayout(layout)

        tab.filelist.addSelectionListener(self)


    def deleteLater(self):
        self.galleryView.deleteLater()
        self.galleryView = None

        super().deleteLater()


    @Slot()
    def _initGrid(self):
        self._initTimer.timeout.disconnect()
        self._initTimer.deleteLater()
        self._initTimer = None

        # Slot onHeadersUpdated() needs access to cboFolders and scrollArea
        self.galleryModel.headersUpdated.connect(self.onHeadersUpdated)
        self.galleryView.setViewMode(self.cboViewMode.currentData())
        self.galleryModel.reloadImages()

        self.galleryModel.reloaded.connect(lambda: self.galleryView.scrollToTop())
        # #self.galleryGrid.reloaded.connect(self.queueGridUpdate)
        # #self.galleryGrid.thumbnailLoaded.connect(self.queueGridUpdate)
        # self.galleryGrid.loadingProgress.connect(self.updateStatusBar)
        # self.galleryGrid.highlighted.connect(self.updateStatusBar)
        # self.galleryGrid.fileChanged.connect(self.ensureVisible)


    def _buildTopRow(self):
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.cboFolders = QtWidgets.QComboBox()
        self.cboFolders.setMinimumWidth(100)
        self.cboFolders.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Preferred)
        self.cboFolders.currentIndexChanged.connect(self.onFolderSelected)
        qtlib.setMonospace(self.cboFolders)
        layout.addWidget(self.cboFolders, 1)

        layout.addSpacing(6)

        self.chkCaptions = QtWidgets.QCheckBox("Captions:")
        self.chkCaptions.toggled.connect(self.onCaptionsToggled)
        layout.addWidget(self.chkCaptions)

        self.captionSrc = FileTypeSelector()
        self.captionSrc.setEnabled(False)
        self.captionSrc.fileTypeUpdated.connect(self.onCaptionSourceChanged)
        layout.addLayout(self.captionSrc)

        layout.addSpacing(2)

        self.chkFilterCaptions = QtWidgets.QCheckBox("Filter")
        self.chkFilterCaptions.setToolTip("Show only tags from visible groups and apply rules from Caption Window")
        self.chkFilterCaptions.setEnabled(False)
        self.chkFilterCaptions.toggled.connect(self.onCaptionFilterToggled)
        layout.addWidget(self.chkFilterCaptions)

        self.btnReloadCaptions = qtlib.SaveButton("↻")
        self.btnReloadCaptions.setToolTip("Reload Captions")
        self.btnReloadCaptions.setEnabled(False)
        self.btnReloadCaptions.setFixedWidth(30)
        self.btnReloadCaptions.clicked.connect(self.reloadCaptions)
        layout.addWidget(self.btnReloadCaptions)

        return layout


    def _buildStatusBar(self):
        self.statusBar = QtWidgets.QStatusBar()

        self.chkFollowSelection = QtWidgets.QCheckBox("Follow Selection")
        self.chkFollowSelection.setChecked(True)
        self.statusBar.addPermanentWidget(self.chkFollowSelection)

        self.statusBar.addPermanentWidget(self._buildThumbnailSize())
        #self.statusBar.addPermanentWidget(self.sortControl.btnSort)

        self.cboViewMode = QtWidgets.QComboBox()
        self.cboViewMode.addItem("▦ Grid View", GalleryView.VIEW_MODE_GRID)
        self.cboViewMode.addItem("▤ List View", GalleryView.VIEW_MODE_LIST)
        self.cboViewMode.currentIndexChanged.connect(self.onViewModeChanged)
        self.statusBar.addPermanentWidget(self.cboViewMode)

    def _buildThumbnailSize(self):
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(6, 0, 6, 0)
        layout.addWidget(QtWidgets.QLabel("Thumbnail Size:"))

        self.slideThumbnailSize = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self.slideThumbnailSize.setRange(100, 400)
        self.slideThumbnailSize.setTickPosition(QtWidgets.QSlider.TickPosition.TicksAbove)
        self.slideThumbnailSize.setTickInterval(self.THUMBNAIL_SIZE_STEP * 2)
        self.slideThumbnailSize.setSingleStep(self.THUMBNAIL_SIZE_STEP)
        self.slideThumbnailSize.setPageStep(self.THUMBNAIL_SIZE_STEP)
        self.slideThumbnailSize.setTracking(False) # TODO: Still snap to steps
        self.slideThumbnailSize.setFixedWidth(120)
        self.slideThumbnailSize.setValue(Config.galleryThumbnailSize)
        self.slideThumbnailSize.valueChanged.connect(self.onThumbnailSizeChanged)
        layout.addWidget(self.slideThumbnailSize)

        self.lblThumbnailSize = QtWidgets.QLabel(str(Config.galleryThumbnailSize))
        self.lblThumbnailSize.setFixedWidth(30)
        layout.addWidget(self.lblThumbnailSize)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Maximum)
        return widget


    @Slot()
    def onCaptionsToggled(self, state: bool):
        # self.galleryGrid.ctx.captionsEnabled = state
        # self.galleryGrid.ctx.updateTextFlags()

        self.captionSrc.setEnabled(state)
        self.btnReloadCaptions.setEnabled(state)
        self.chkFilterCaptions.setEnabled(state and self.isGridView)

        if state:
            self.btnReloadCaptions.setChanged(True)
        elif not self._switchingMode:
            self.reloadCaptions()

    Slot()
    def onCaptionFilterToggled(self, state: bool):
        if self.isGridView:
            self.reloadCaptions()

    @Slot()
    def onCaptionSourceChanged(self):
        self.btnReloadCaptions.setChanged(True)

    @Slot()
    def reloadCaptions(self):
        #self._updateCaptionContext()
        #self.galleryGrid.reloadCaptions()
        self.btnReloadCaptions.setChanged(False)

    # def _updateCaptionContext(self):
    #     ctx = self.galleryGrid.ctx
    #     ctx.filterNode     = None
    #     ctx.rulesProcessor = None

    #     if captionWin := self.tab.getWindowContent("caption"):
    #         from caption.caption_context import CaptionContext
    #         captionCtx: CaptionContext = captionWin.ctx
    #         ctx.captionHighlight = captionCtx.highlight
    #         ctx.separator        = captionCtx.settings.separator

    #         if self.chkFilterCaptions.isChecked():
    #             ctx.filterNode      = captionCtx.groups.getGalleryFilterNode()
    #             ctx.rulesProcessor  = captionCtx.rulesProcessor()

    def onCaptionFilterUpdated(self):
        'Called from Caption Window'
        if self.chkCaptions.isChecked() and self.isGridView:
            self.reloadCaptions()


    @property
    def isGridView(self) -> bool:
        return self.cboViewMode.currentData() == GalleryView.VIEW_MODE_GRID

    @Slot()
    def onViewModeChanged(self, index: int):
        mode = self.cboViewMode.itemData(index)
        if mode == GalleryView.VIEW_MODE_LIST:
            self.chkFilterCaptions.setChecked(False)
            self.chkFilterCaptions.setEnabled(False)

            self.chkCaptions.setChecked(True)
            self.chkCaptions.setEnabled(False)
        else:
            try:
                self._switchingMode = True
                self.chkCaptions.setChecked(False)
                self.chkCaptions.setEnabled(True)
            finally:
                self._switchingMode = False

        #self._updateCaptionContext()
        self.galleryView.setViewMode(mode)
        self.scrollToSelection()
        self.btnReloadCaptions.setChanged(False)

    @Slot()
    def onThumbnailSizeChanged(self, size: int):
        size = round(size / self.THUMBNAIL_SIZE_STEP) * self.THUMBNAIL_SIZE_STEP
        with QSignalBlocker(self.slideThumbnailSize):
            self.slideThumbnailSize.setValue(size)

        self.lblThumbnailSize.setText(f"{size}")
        self.galleryView.setItemWidth(size)
        Config.galleryThumbnailSize = size

    @Slot()
    def updateStatusBar(self):
        filelist = self.tab.filelist

        msgs = list[str]()
        if numSelectedFiles := len(filelist.selectedFiles):
            msgs.append(f"{numSelectedFiles} Selected")
        # if self.galleryGrid.highlightCount:
        #     msgs.append(f"{self.galleryGrid.highlightCount} Highlighted")
        msgsText = "".join(("  (", ", ".join(msgs), ")")) if msgs else ""

        loadPercent = 1.0 #self.galleryGrid.getLoadPercent()
        loadText = f"  (Loading Gallery: {100*loadPercent:.1f} %)" if loadPercent < 1.0 else ""

        numFiles = filelist.getNumFiles()
        numFolders = self.cboFolders.count()
        self.statusBar.showMessage(f"{numFiles} Images in {numFolders} Folders{msgsText}{loadText}")


    def resizeEvent(self, event: QtGui.QResizeEvent):
        if self._initTimer:
            self._initTimer.start()
        else:
            self.queueGridUpdate()

    @Slot()
    def queueGridUpdate(self):
        tNow = time.monotonic()
        tDiff = tNow - self._lastGridUpdate
        self._lastGridUpdate = tNow

        if tDiff > self.MIN_GRID_UPDATE_DELAY:
            self.updateGrid()
        else:
            self._gridUpdateTimer.start()
            #self.scrollArea.setWidgetResizable(False) # Disable auto update because it can be laggy
            self.galleryView.viewport().setUpdatesEnabled(False)
            #self.galleryView.setUpdatesEnabled(False)
            #self.galleryView.setModel(None)
            #self.galleryView.delegate.resizing = True

    @Slot()
    def updateGrid(self):
        # Re-enable size update. Update scroll area size to fit window.
        #self.scrollArea.setWidgetResizable(True)
        self.galleryView.viewport().setUpdatesEnabled(True)
        #self.galleryView.setUpdatesEnabled(True)
        #self.galleryView.setModel(self.galleryModel)
        #self.galleryView.delegate.resizing = False

        if self.isVisible():
            self.galleryView.updateWidth()


    @Slot()
    def onHeadersUpdated(self, headers: list[HeaderItem]):
        self.rowToHeader.clear()
        with QSignalBlocker(self.cboFolders):
            self.cboFolders.clear()
            for header in headers:
                path = self.tab.filelist.removeCommonRoot(header.path)
                self.cboFolders.addItem(path, header.row)
                self.rowToHeader.append(header.row)

        self.updateComboboxFolder()
        self.updateStatusBar()

    @Slot()
    def onFolderSelected(self, index):
        row = self.cboFolders.itemData(index)
        if row is not None:
            self.galleryView.scrollToRow(row)
            self.updateComboboxFolder()

    @Slot()
    def updateComboboxFolder(self):
        row = self.galleryView.getRowAtTop()
        index = bisect_right(self.rowToHeader, row)
        index = max(index-1, 0)

        with QSignalBlocker(self.cboFolders):
            self.cboFolders.setCurrentIndex(index)

    # @Slot()
    # def ensureVisible(self, widget: QtWidgets.QWidget, row: int, delay: bool):
    #     if delay:
    #         QTimer.singleShot(100, lambda: self.ensureVisible(widget, row, False))
    #         return

    #     if self.chkFollowSelection.isChecked() and widget.visibleRegion().isEmpty():
    #         if (y := self.galleryGrid.getYforRow(row)) >= 0:
    #             self.scrollArea.verticalScrollBar().setValue(y)

    def scrollToSelection(self):
        pass
        # if selectedItem := self.galleryGrid.selectedItem:
        #     self.ensureVisible(selectedItem, selectedItem.row, delay=True)


    def onFileSelectionChanged(self, selectedFiles: set[str]):
        self.updateStatusBar()

    def highlightFiles(self, files: list[str]):
        pass
        #self.galleryGrid.highlightFiles(files)



# class GalleryScrollArea(QtWidgets.QScrollArea):
#     def __init__(self, tab: ImgTab):
#         super().__init__()
#         self.tab = tab

#     def wheelEvent(self, event):
#         scrollBar = self.verticalScrollBar()
#         gallery: GalleryGrid = self.widget()

#         scrollDown = event.angleDelta().y() < 0

#         row = gallery.getRowForY(scrollBar.value(), scrollDown)
#         row += 1 if scrollDown else -1
#         y = gallery.getYforRow(row, scrollDown)
#         if y >= 0:
#             scrollBar.setValue(y)

#     def keyPressEvent(self, event: QtGui.QKeyEvent):
#         filelist = self.tab.filelist
#         match event.key():
#             case Qt.Key.Key_Left:
#                 filelist.setPrevFile()
#             case Qt.Key.Key_Right:
#                 filelist.setNextFile()
#             case Qt.Key.Key_Up:
#                 filelist.setPrevFolder()
#             case Qt.Key.Key_Down:
#                 filelist.setNextFolder()

#             case Qt.Key.Key_Home:
#                 self.verticalScrollBar().setValue(0)
#             case Qt.Key.Key_End:
#                 scrollBar = self.verticalScrollBar()
#                 scrollBar.setValue(scrollBar.maximum()+1000)

#             case _:
#                 super().keyPressEvent(event)
#                 return

#         event.accept()
