from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
from .gallery_grid import GalleryGrid
import qtlib


# Contains directory tree toolbar

class Gallery(QtWidgets.QWidget):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.galleryGrid = None
        self.rowToHeader = dict()

        self.chkFollowSelection = QtWidgets.QCheckBox("Follow Selection")
        self.chkFollowSelection.setChecked(True)

        self.statusBar = QtWidgets.QStatusBar()
        self.statusBar.addPermanentWidget(self.chkFollowSelection)

        self._build()


    def _build(self):
        self.cboFolders = QtWidgets.QComboBox()
        self.cboFolders.currentIndexChanged.connect(self.onFolderSelected)
        qtlib.setMonospace(self.cboFolders)

        self.scrollArea = FastScrollArea()
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.verticalScrollBar().valueChanged.connect(self.updateComboboxFolder)

        self.galleryGrid = GalleryGrid(self.tab)
        self.tab.filelist.addListener(self.galleryGrid)
        self.tab.filelist.addDataListener(self.galleryGrid)

        self.galleryGrid.adjustGrid(self.width()-40) # Adjust grid before connecting slot onHeadersUpdated()
        self.galleryGrid.headersUpdated.connect(self.onHeadersUpdated)
        self.galleryGrid.reloadImages() # Slot onHeadersUpdated() needs access to cboFolders and scrollArea
        self.galleryGrid.reloaded.connect(self.scrollTop)
        self.galleryGrid.fileChanged.connect(self.ensureVisible)
        self.scrollArea.setWidget(self.galleryGrid)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.cboFolders)
        layout.addWidget(self.scrollArea)
        self.setLayout(layout)


    def updateStatusBar(self, numFolders):
        numFiles = self.galleryGrid.filelist.getNumFiles()
        self.statusBar.showMessage(f"{numFiles} Images in {numFolders} Folders")


    def resizeEvent(self, event):
        if self.galleryGrid:
            #self.gallery.setMaximumWidth(event.size().width())
            self.galleryGrid.adjustGrid(event.size().width()-40)
        #super().resizeEvent(event)

    @Slot()
    def onHeadersUpdated(self, headers: dict):
        try:
            self.rowToHeader.clear()
            self.cboFolders.blockSignals(True)
            self.cboFolders.clear()
            for i, (folder, row) in enumerate(headers.items()):
                self.cboFolders.addItem(folder, row)
                self.rowToHeader[row] = i
        finally:
            self.cboFolders.blockSignals(False)
        
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
        index = 0
        for headerRow, i in self.rowToHeader.items():
            if headerRow > row:
                break
            index = i
        
        try:
            self.cboFolders.blockSignals(True)
            self.cboFolders.setCurrentIndex(index)
        finally:
            self.cboFolders.blockSignals(False)

    @Slot()
    def scrollTop(self):
        self.scrollArea.verticalScrollBar().setValue(0)

    @Slot()
    def ensureVisible(self, widget, row):
        if self.chkFollowSelection.isChecked() and widget.visibleRegion().isEmpty():
            if (y := self.galleryGrid.getYforRow(row)) >= 0:
                self.scrollArea.verticalScrollBar().setValue(y)



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
        