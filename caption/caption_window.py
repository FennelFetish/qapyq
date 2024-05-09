from PySide6 import QtWidgets
from aux_window import AuxiliaryWindow
from .caption import Caption



class CaptionWindow(AuxiliaryWindow):
    def __init__(self):
        super().__init__("Caption")


    def setupContent(self, tab) -> object:
        caption = Caption(tab)
        tab.filelist.addListener(caption)
        return caption

    def teardownContent(self, caption):
        caption.tab.filelist.removeListener(caption)
