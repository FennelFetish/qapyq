from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from .gallery import Gallery
from aux_window import AuxiliaryWindow


# Contains directory tree toolbar

class GalleryWindow(AuxiliaryWindow):
    def __init__(self):
        super().__init__("Gallery")
        self.gallery = None

    def setupContent(self, tab) -> object:
        self.gallery = Gallery(tab)
        self.gallery.filelist.addListener(self.gallery)
        self.gallery.adjustGrid(self.width()-40)
        self.gallery.reloadImages()

        scrollArea = FastScrollArea()
        scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scrollArea.setWidgetResizable(True)
        scrollArea.setWidget(self.gallery)
        return scrollArea

    def teardownContent(self, scrollArea):
        self.gallery.filelist.removeListener(self.gallery)
        self.gallery = None

    def resizeEvent(self, event):
        if self.gallery:
            self.gallery.adjustGrid(event.size().width()-40)
        #super().resizeEvent(event)


class FastScrollArea(QtWidgets.QScrollArea):
    def __init__(self):
        super().__init__()

    def wheelEvent(self, event):
        scrollBar = self.verticalScrollBar()
        gallery = self.widget()

        scrollDown = event.angleDelta().y() < 0

        row = gallery.getRowForY(scrollBar.value(), scrollDown)
        row += 1 if scrollDown else -1
        y = gallery.getYforRow(row)
        if y >= 0:
            scrollBar.setValue(y)
        