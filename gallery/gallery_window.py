from PySide6 import QtWidgets
from .gallery import Gallery
from aux_window import AuxiliaryWindow


# Contains directory tree toolbar


class GalleryWindow(AuxiliaryWindow):
    def __init__(self):
        super().__init__("Gallery")


    def setupContent(self, tab) -> object:
        gallery = Gallery(tab)
        gallery.filelist.addListener(gallery)
        gallery.updateImages()
        return gallery

    def teardownContent(self, gallery):
        gallery.filelist.removeListener(gallery)
