from PySide6 import QtWidgets
from aux_window import AuxiliaryWindow
from .caption import CaptionContainer



class CaptionWindow(AuxiliaryWindow):
    def __init__(self):
        super().__init__("Caption")


    def setupContent(self, tab) -> object:
        caption = CaptionContainer(tab)
        tab.filelist.addListener(caption)
        caption.onFileChanged( tab.filelist.getCurrentFile() )
        return caption

    def teardownContent(self, caption):
        caption.tab.filelist.removeListener(caption)
