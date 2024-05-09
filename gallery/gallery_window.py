from PySide6 import QtWidgets
from .gallery import Gallery
from aux_window import AuxiliaryWindow


# Contains directory tree toolbar


class GalleryWindow(AuxiliaryWindow):
    def __init__(self):
        super().__init__("Gallery")
        self.tab = None

    def setTab(self, tab):
        if tab is self.tab:
            return
        self.tab = tab
        
        gallery = self.takeCentralWidget()
        if gallery:
            gallery.filelist.removeListener(gallery)
        
        if tab:
            gallery = Gallery(tab)
            gallery.filelist.addListener(gallery)
            self.setCentralWidget(gallery)
            gallery.updateImages()

    
    def closeEvent(self, event):
        gallery = self.takeCentralWidget()
        self.tab.filelist.removeListener(gallery)
        self.tab = None
        super().closeEvent(event)
