import locale
from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QSignalBlocker, QTimer
from lib import qtlib
from lib.captionfile import FileTypeSelector
from ui.tab import ImgTab
from config import Config
from .gallery_caption import GalleryCaption
from .gallery_model import GalleryModel, HeaderItem
from .gallery_view import GalleryView
from .gallery_sort import GallerySortControl


class Gallery(QtWidgets.QWidget):
    THUMBNAIL_SIZE_STEP = 50

    def __init__(self, tab: ImgTab):
        super().__init__()
        self.tab = tab

        self._switchingMode = False

        # Initialize grid after delay: Wait for the window width to calculate column count
        self._initTimer = QTimer(singleShot=True, interval=50)
        self._initTimer.timeout.connect(self._initGrid)

        self._gridUpdateTimer = QTimer(singleShot=True, interval=100)
        self._gridUpdateTimer.timeout.connect(self.updateGrid)

        self.captionSrc = FileTypeSelector()
        self.galleryCaption = GalleryCaption(self.captionSrc)

        self.galleryModel: GalleryModel = GalleryModel(tab.filelist, self.galleryCaption)
        self.galleryView: GalleryView = GalleryView(tab, self.galleryCaption, Config.galleryThumbnailSize)
        self.galleryView.verticalScrollBar().valueChanged.connect(self.updateComboboxFolder)
        self.galleryView.setModel(self.galleryModel)

        self.sortControl = GallerySortControl(self.tab)
        self.sortControl.sortDone.connect(self.galleryModel.updateGrid)
        self.galleryView.sortByImages.connect(self.sortControl.updateSortByImage)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(self._buildTopRow())
        layout.addWidget(self.galleryView)
        layout.addWidget(self.sortControl)
        self.setLayout(layout)

        self._buildStatusBar()


    @override
    def deleteLater(self):
        self.galleryModel.deleteLater()
        super().deleteLater()


    @Slot()
    def _initGrid(self):
        self._initTimer.timeout.disconnect()
        self._initTimer.deleteLater()
        self._initTimer = None

        self.galleryView.setViewMode(self.cboViewMode.currentData())

        # Register model before self: Build grid before jumping to selected file
        filelist = self.tab.filelist
        filelist.addListener(self.galleryModel)
        filelist.addDataListener(self.galleryModel)
        filelist.addSelectionListener(self.galleryModel)

        filelist.addListener(self)
        filelist.addSelectionListener(self)

        self.galleryModel.headersUpdated.connect(self.onHeadersUpdated)
        self.galleryModel.reloadImages()


    def _buildTopRow(self):
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # TODO: Use MenuComboBox and build tree structure when num headers > 30?
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
        self.btnReloadCaptions.clicked.connect(lambda: self.reloadCaptions(clear=True))
        layout.addWidget(self.btnReloadCaptions)

        return layout


    def _buildStatusBar(self):
        self.statusBar = QtWidgets.QStatusBar()

        self.chkFollowSelection = QtWidgets.QCheckBox("Follow Selection")
        self.chkFollowSelection.setChecked(True)
        self.chkFollowSelection.toggled.connect(self.onFollowSelectionToggled)
        self.statusBar.addPermanentWidget(self.chkFollowSelection)

        self.statusBar.addPermanentWidget(self._buildThumbnailSize())
        self.statusBar.addPermanentWidget(self.sortControl.btnSort)

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


    @Slot(bool)
    def onCaptionsToggled(self, state: bool):
        self.galleryCaption.captionsEnabled = state

        self.captionSrc.setEnabled(state)
        self.btnReloadCaptions.setEnabled(state)
        self.chkFilterCaptions.setEnabled(state and self.isGridView)

        if state:
            self.btnReloadCaptions.setChanged(True)
        elif not self._switchingMode:
            self.reloadCaptions(clear=True)

    @Slot(bool)
    def onCaptionFilterToggled(self, state: bool):
        if self.isGridView:
            self.reloadCaptions(clear=False)

    @Slot()
    def onCaptionSourceChanged(self):
        self.btnReloadCaptions.setChanged(True)

    def reloadCaptions(self, clear: bool, modelReset: bool = True):
        self._updateCaptionContext()
        self.btnReloadCaptions.setChanged(False)
        self.galleryModel.resetCaptions(clear=clear, modelReset=modelReset)

    def _updateCaptionContext(self):
        cap = self.galleryCaption
        cap.filterNode     = None
        cap.rulesProcessor = None

        if captionWin := self.tab.getWindowContent("caption"):
            from caption.caption_context import CaptionContext
            captionCtx: CaptionContext = captionWin.ctx
            cap.captionHighlight = captionCtx.highlight
            cap.separator        = captionCtx.settings.separator

            if self.chkFilterCaptions.isChecked():
                cap.filterNode      = captionCtx.groups.getGalleryFilterNode()
                cap.rulesProcessor  = captionCtx.rulesProcessor()

    def onCaptionFilterUpdated(self):
        'Called from Caption Window'
        if self.chkCaptions.isChecked():
            self.reloadCaptions(clear=False)


    @property
    def isGridView(self) -> bool:
        return self.cboViewMode.currentData() == GalleryView.VIEW_MODE_GRID

    @Slot(int)
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

        self.reloadCaptions(clear=True, modelReset=False)
        self.galleryView.setViewMode(mode)
        self.ensureVisible(self.tab.filelist.currentFile)


    @Slot(bool)
    def onFollowSelectionToggled(self, state: bool):
        if state:
            self.ensureVisible(self.tab.filelist.currentFile)

    @Slot(int)
    def onThumbnailSizeChanged(self, size: int):
        size = round(size / self.THUMBNAIL_SIZE_STEP) * self.THUMBNAIL_SIZE_STEP
        with QSignalBlocker(self.slideThumbnailSize):
            self.slideThumbnailSize.setValue(size)

        Config.galleryThumbnailSize = size
        self.lblThumbnailSize.setText(f"{size}")
        self.galleryView.setItemWidth(size)
        self.ensureVisible(self.tab.filelist.currentFile)

    @Slot()
    def updateStatusBar(self):
        filelist = self.tab.filelist

        numFiles = filelist.getNumFiles()
        numFolders = self.cboFolders.count()
        text = locale.format_string("%d Images in %d Folders", (numFiles, numFolders), grouping=True)

        msgs = list[str]()
        if numSelectedFiles := len(filelist.selectedFiles):
            msgs.append(f"{numSelectedFiles} Selected")
        if self.galleryModel.numHighlighted:
            msgs.append(f"{self.galleryModel.numHighlighted} Highlighted")
        if filelist.isLoading():
            msgs.append("Loading")

        if msgs:
            msgs = ", ".join(msgs)
            text += f"  ({msgs})"

        self.statusBar.showMessage(text)


    @override
    def resizeEvent(self, event: QtGui.QResizeEvent):
        if self._initTimer:
            self._initTimer.start()
        else:
            self.galleryView.setResizing(True)
            self._gridUpdateTimer.start()

        event.accept()

    @Slot()
    def updateGrid(self):
        self.galleryView.setResizing(False)


    @Slot(list)
    def onHeadersUpdated(self, headers: list[HeaderItem]):
        filelist = self.tab.filelist

        with QSignalBlocker(self.cboFolders):
            self.cboFolders.clear()
            for header in headers:
                path = filelist.removeCommonRoot(header.path)
                self.cboFolders.addItem(path, header.row)

        self.updateComboboxFolder()
        self.updateStatusBar()
        self.galleryView.setFocus()

        self.sortControl.setSortAvailable(not filelist.isLoading())


    @Slot(int)
    def onFolderSelected(self, index: int):
        row = self.cboFolders.itemData(index)
        if row is not None:
            self.galleryView.scrollToRow(row)

    @Slot()
    def updateComboboxFolder(self):
        row = self.galleryView.rowAt(0)
        index = self.galleryModel.headerIndexForRow(row)

        with QSignalBlocker(self.cboFolders):
            self.cboFolders.setCurrentIndex(index)

    @Slot(str, bool)
    def ensureVisible(self, file: str, delay: bool = False):
        if delay:
            QTimer.singleShot(400, lambda: self.ensureVisible(file, False))
            return

        if self.chkFollowSelection.isChecked():
            self.galleryView.scrollToFile(file)


    def onFileChanged(self, currentFile: str):
        self.ensureVisible(currentFile)

    def onFileListChanged(self, currentFile: str):
        self.ensureVisible(currentFile)
        self.ensureVisible(currentFile, delay=True)

    def onFileSelectionChanged(self, selectedFiles: set[str]):
        self.updateStatusBar()


    def highlightFiles(self, files: list[str]):
        self.galleryModel.highlightFiles(files)
        self.updateStatusBar()
