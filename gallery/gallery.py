import time
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QSignalBlocker, QTimer
from bisect import bisect_right
from .gallery_grid import GalleryGrid
import lib.qtlib as qtlib
from lib.captionfile import FileTypeSelector


# TODO: Contains directory tree toolbar ... folder navigation with hierarchal menu?

class Gallery(QtWidgets.QWidget):
    MIN_GRID_UPDATE_DELAY = 0.5

    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.galleryGrid = None
        self.rowToHeader: list[int] = list()

        self.gridUpdateTimer = QTimer()
        self.gridUpdateTimer.setSingleShot(True)
        self.gridUpdateTimer.setInterval(200)
        self.gridUpdateTimer.timeout.connect(self.updateGrid)
        self.lastGridUpdate = 0

        self.chkFollowSelection = QtWidgets.QCheckBox("Follow Selection")
        self.chkFollowSelection.setChecked(True)

        self.cboViewMode = QtWidgets.QComboBox()
        self.cboViewMode.addItem("Grid View", "grid")
        self.cboViewMode.addItem("List View", "list")
        self.cboViewMode.currentIndexChanged.connect(self.onViewModeChanged)

        self.statusBar = QtWidgets.QStatusBar()
        self.statusBar.addPermanentWidget(self.chkFollowSelection)
        self.statusBar.addPermanentWidget(self.cboViewMode)

        self._build()


    def _build(self):
        self.captionSrc = FileTypeSelector()
        btnReloadCaptions = QtWidgets.QPushButton("↻")
        btnReloadCaptions.setFixedWidth(28)
        btnReloadCaptions.clicked.connect(lambda: self.galleryGrid.reloadCaptions())

        self.cboFolders = QtWidgets.QComboBox()
        self.cboFolders.currentIndexChanged.connect(self.onFolderSelected)
        qtlib.setMonospace(self.cboFolders)

        self.scrollArea = FastScrollArea()
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scrollArea.setSizeAdjustPolicy(FastScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.verticalScrollBar().valueChanged.connect(self.updateComboboxFolder)

        self.galleryGrid = GalleryGrid(self.tab, self.captionSrc)
        self.tab.filelist.addListener(self.galleryGrid)
        self.tab.filelist.addDataListener(self.galleryGrid)

        self.galleryGrid.headersUpdated.connect(self.onHeadersUpdated)
        self.galleryGrid.reloadImages() # Slot onHeadersUpdated() needs access to cboFolders and scrollArea
        self.galleryGrid.reloaded.connect(self.scrollTop)
        self.galleryGrid.reloaded.connect(self.queueGridUpdate)
        self.galleryGrid.thumbnailLoaded.connect(self.queueGridUpdate)
        self.galleryGrid.fileChanged.connect(self.ensureVisible)
        self.scrollArea.setWidget(self.galleryGrid)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 0)
        layout.setColumnStretch(4, 0)
        layout.setColumnMinimumWidth(1, 20)
        layout.addWidget(self.cboFolders, 0, 0)
        layout.addWidget(QtWidgets.QLabel("Captions:"), 0, 2)
        layout.addLayout(self.captionSrc, 0, 3)
        layout.addWidget(btnReloadCaptions, 0, 4)
        layout.addWidget(self.scrollArea, 1, 0, 1, 5)
        self.setLayout(layout)


    @Slot()
    def onViewModeChanged(self, index: int):
        mode = self.cboViewMode.itemData(index)
        self.galleryGrid.setViewMode(mode)
        self.scrollToSelection()

    def updateStatusBar(self, numFolders):
        numFiles = self.galleryGrid.filelist.getNumFiles()
        self.statusBar.showMessage(f"{numFiles} Images in {numFolders} Folders")


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
    def onHeadersUpdated(self, headers: list):
        self.rowToHeader.clear()
        with QSignalBlocker(self.cboFolders):
            self.cboFolders.clear()
            for folder, row in headers:
                self.cboFolders.addItem(folder, row)
                self.rowToHeader.append(row)
        
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



class FastScrollArea(QtWidgets.QScrollArea):
    def __init__(self):
        super().__init__()

    def wheelEvent(self, event):
        scrollBar = self.verticalScrollBar()
        gallery = self.widget()

        scrollDown = event.angleDelta().y() < 0

        row = gallery.getRowForY(scrollBar.value(), scrollDown)
        row += 1 if scrollDown else -1
        y = gallery.getYforRow(row, scrollDown)
        if y >= 0:
            scrollBar.setValue(y)
        