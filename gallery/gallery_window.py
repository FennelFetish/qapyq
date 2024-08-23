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

        scrollArea = QtWidgets.QScrollArea()
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