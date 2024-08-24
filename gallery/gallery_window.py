from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
from .gallery import Gallery
from aux_window import AuxiliaryWindow
import qtlib


# Contains directory tree toolbar

class GalleryWindow(AuxiliaryWindow):
    def __init__(self):
        super().__init__("Gallery")
        self.gallery = None
        self.rowToHeader = dict()

    def setupContent(self, tab) -> object:
        self.cboFolders = QtWidgets.QComboBox()
        self.cboFolders.currentIndexChanged.connect(self.onFolderSelected)
        qtlib.setMonospace(self.cboFolders)

        self.scrollArea = FastScrollArea()
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.verticalScrollBar().valueChanged.connect(self.onScrolled)

        self.gallery = Gallery(tab)
        self.gallery.filelist.addListener(self.gallery)
        self.gallery.filelist.addDataListener(self.gallery)
        self.gallery.adjustGrid(self.width()-40) # Adjust grid before connecting slot onHeadersUpdated()
        self.gallery.headersUpdated.connect(self.onHeadersUpdated)
        self.gallery.reloadImages() # Slot onHeadersUpdated() needs access to cboFolders and scrollArea
        self.scrollArea.setWidget(self.gallery)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.cboFolders)
        layout.addWidget(self.scrollArea)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        return widget

    def teardownContent(self, content):
        self.gallery.filelist.removeListener(self.gallery)
        self.gallery.filelist.removeDataListener(self.gallery)
        self.gallery = None
        self.rowToHeader.clear()

    def resizeEvent(self, event):
        if self.gallery:
            self.gallery.adjustGrid(event.size().width()-40)
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
        self.onScrolled(self.scrollArea.verticalScrollBar().value())
    
    @Slot()
    def onFolderSelected(self, index):
        row = self.cboFolders.itemData(index)
        if row == None:
            return
        if row == 0:
            self.scrollArea.verticalScrollBar().setValue(0)
        else:
            y = self.gallery.getYforRow(row)
            self.scrollArea.verticalScrollBar().setValue(y)
    
    @Slot()
    def onScrolled(self, y):
        row = self.gallery.getRowForY(y, True)
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
        