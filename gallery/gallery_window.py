from PySide6 import QtWidgets
from .gallery import Gallery

# Gallery content tied to active tab

# Contains directory tree toolbar


class GalleryWindow(QtWidgets.QMainWindow):
    def __init__(self, mainWindow):
        super().__init__()
        self.mainWindow = mainWindow
        self.tab = None

        self.setWindowTitle("Gallery")

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
        self.mainWindow.onGalleryClosed()
