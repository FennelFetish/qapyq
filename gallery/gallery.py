import time
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QSignalBlocker, QTimer
from bisect import bisect_right
from .gallery_grid import GalleryGrid, GalleryHeader
import lib.qtlib as qtlib
from lib.captionfile import FileTypeSelector
from ui.tab import ImgTab
from config import Config


# TODO: Contains directory tree toolbar ... folder navigation with hierarchal menu?

class Gallery(QtWidgets.QWidget):
    MIN_GRID_UPDATE_DELAY = 1.0
    THUMBNAIL_SIZE_STEP = 50

    def __init__(self, tab: ImgTab):
        super().__init__()
        self.tab = tab
        self.galleryGrid = None
        self.rowToHeader: list[int] = list()

        self.gridUpdateTimer = QTimer()
        self.gridUpdateTimer.setSingleShot(True)
        self.gridUpdateTimer.setInterval(100)
        self.gridUpdateTimer.timeout.connect(self.updateGrid)
        self.lastGridUpdate = 0

        self.chkFollowSelection = QtWidgets.QCheckBox("Follow Selection")
        self.chkFollowSelection.setChecked(True)

        self.cboViewMode = QtWidgets.QComboBox()
        self.cboViewMode.addItem("Grid View", GalleryGrid.VIEW_MODE_GRID)
        self.cboViewMode.addItem("List View", GalleryGrid.VIEW_MODE_LIST)
        self.cboViewMode.currentIndexChanged.connect(self.onViewModeChanged)

        self.statusBar = QtWidgets.QStatusBar()
        self.statusBar.addPermanentWidget(self.chkFollowSelection)
        self.statusBar.addPermanentWidget(self._buildThumbnailSize())
        self.statusBar.addPermanentWidget(self.cboViewMode)

        self._build()
        tab.filelist.addSelectionListener(self)

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

    def _build(self):
        self.captionSrc = FileTypeSelector()
        self.captionSrc.fileTypeUpdated.connect(self.onCaptionSourceChanged)

        self.btnReloadCaptions = qtlib.SaveButton("↻")
        self.btnReloadCaptions.setFixedWidth(28)
        self.btnReloadCaptions.clicked.connect(self.reloadCaptions)

        self.cboFolders = QtWidgets.QComboBox()
        self.cboFolders.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Preferred)
        self.cboFolders.currentIndexChanged.connect(self.onFolderSelected)
        qtlib.setMonospace(self.cboFolders)

        self.scrollArea = FastScrollArea()
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scrollArea.setSizeAdjustPolicy(FastScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.verticalScrollBar().valueChanged.connect(self.updateComboboxFolder)

        self.galleryGrid = GalleryGrid(self.tab, self.captionSrc)
        self.galleryGrid.thumbnailSize = Config.galleryThumbnailSize

        self.galleryGrid.headersUpdated.connect(self.onHeadersUpdated)
        self.galleryGrid.reloadImages() # Slot onHeadersUpdated() needs access to cboFolders and scrollArea
        self.galleryGrid.reloaded.connect(self.scrollTop)
        self.galleryGrid.reloaded.connect(self.queueGridUpdate)
        self.galleryGrid.thumbnailLoaded.connect(self.queueGridUpdate)
        self.galleryGrid.loadingProgress.connect(self.onLoadProgress)
        self.galleryGrid.fileChanged.connect(self.ensureVisible)
        self.scrollArea.setWidget(self.galleryGrid)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 0)
        layout.setColumnStretch(4, 0)
        layout.setColumnMinimumWidth(1, 6)
        layout.addWidget(self.cboFolders, 0, 0)
        layout.addWidget(QtWidgets.QLabel("Captions:"), 0, 2)
        layout.addLayout(self.captionSrc, 0, 3)
        layout.addWidget(self.btnReloadCaptions, 0, 4)
        layout.addWidget(self.scrollArea, 1, 0, 1, 5)
        self.setLayout(layout)


    @Slot()
    def onViewModeChanged(self, index: int):
        mode = self.cboViewMode.itemData(index)
        self.galleryGrid.setViewMode(mode)
        self.scrollToSelection()
        self.btnReloadCaptions.setChanged(False)

    @Slot()
    def onThumbnailSizeChanged(self, size: int):
        size = round(size / self.THUMBNAIL_SIZE_STEP) * self.THUMBNAIL_SIZE_STEP
        with QSignalBlocker(self.slideThumbnailSize):
            self.slideThumbnailSize.setValue(size)

        self.lblThumbnailSize.setText(f"{size}")
        self.galleryGrid.setThumbnailSize(size)
        Config.galleryThumbnailSize = size

    @Slot()
    def onCaptionSourceChanged(self):
        if self.cboViewMode.currentData() == GalleryGrid.VIEW_MODE_LIST:
            self.btnReloadCaptions.setChanged(True)

    @Slot()
    def reloadCaptions(self):
        self.galleryGrid.reloadCaptions()
        self.btnReloadCaptions.setChanged(False)


    @Slot()
    def onLoadProgress(self):
        self.updateStatusBar(self.cboFolders.count())

    def updateStatusBar(self, numFolders: int):
        filelist = self.galleryGrid.filelist

        selectionText = ""
        numSelectedFiles = len(filelist.selectedFiles)
        if numSelectedFiles > 0:
            selectionText = f"  ({numSelectedFiles} Selected)"

        loadText = ""
        loadPercent = self.galleryGrid.getLoadPercent()
        if loadPercent < 1.0:
            loadText = f"  (Loading Gallery: {100*loadPercent:.1f} %)"

        numFiles = filelist.getNumFiles()
        self.statusBar.showMessage(f"{numFiles} Images in {numFolders} Folders{selectionText}{loadText}")


    def resizeEvent(self, event):
        self.queueGridUpdate()

    @Slot()
    def queueGridUpdate(self):
        tNow = time.time()
        tDiff = tNow - self.lastGridUpdate
        self.lastGridUpdate = tNow

        if tDiff > self.MIN_GRID_UPDATE_DELAY:
            self.updateGrid()
        else:
            self.gridUpdateTimer.start()
            self.scrollArea.setWidgetResizable(False) # Disable auto update because it can be laggy

    @Slot()
    def updateGrid(self):
        # Re-enable size update. Update scroll area size to fit window.
        self.scrollArea.setWidgetResizable(True)

        if self.galleryGrid and self.isVisible():
            self.galleryGrid.adjustGrid()


    @Slot()
    def onHeadersUpdated(self, headers: list[GalleryHeader]):
        self.rowToHeader.clear()
        with QSignalBlocker(self.cboFolders):
            self.cboFolders.clear()
            for header in headers:
                path = self.tab.filelist.removeCommonRoot(header.dir)
                self.cboFolders.addItem(path, header.row)
                self.rowToHeader.append(header.row)

        self.updateComboboxFolder(self.scrollArea.verticalScrollBar().value())
        self.updateStatusBar(len(headers))

    @Slot()
    def onFolderSelected(self, index):
        row = self.cboFolders.itemData(index)
        if row == None:
            return
        if row == 0:
            self.scrollArea.verticalScrollBar().setValue(0)
        else:
            y = self.galleryGrid.getYforRow(row)
            self.scrollArea.verticalScrollBar().setValue(y)

    @Slot()
    def updateComboboxFolder(self, y):
        row = self.galleryGrid.getRowForY(y, True)
        index = bisect_right(self.rowToHeader, row)
        index = max(index-1, 0)

        with QSignalBlocker(self.cboFolders):
            self.cboFolders.setCurrentIndex(index)

    @Slot()
    def scrollTop(self):
        self.scrollArea.verticalScrollBar().setValue(0)

    @Slot()
    def ensureVisible(self, widget, row):
        if self.chkFollowSelection.isChecked() and widget.visibleRegion().isEmpty():
            if (y := self.galleryGrid.getYforRow(row)) >= 0:
                self.scrollArea.verticalScrollBar().setValue(y)

    def scrollToSelection(self):
        if self.galleryGrid and (selectedItem := self.galleryGrid._selectedItem):
            QTimer.singleShot(100, lambda: self.ensureVisible(selectedItem, selectedItem.row))

    def onFileSelectionChanged(self, selectedFiles: set[str]):
        self.updateStatusBar(self.cboFolders.count())


    def highlightFiles(self, files: list[str]):
        self.galleryGrid.highlightFiles(files)



class FastScrollArea(QtWidgets.QScrollArea):
    def __init__(self):
        super().__init__()

    def wheelEvent(self, event):
        scrollBar = self.verticalScrollBar()
        gallery: GalleryGrid = self.widget()

        scrollDown = event.angleDelta().y() < 0

        row = gallery.getRowForY(scrollBar.value(), scrollDown)
        row += 1 if scrollDown else -1
        y = gallery.getYforRow(row, scrollDown)
        if y >= 0:
            scrollBar.setValue(y)
