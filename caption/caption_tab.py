from PySide6 import QtWidgets


class CaptionTab(QtWidgets.QWidget):
    def __init__(self, context):
        super().__init__()

        from .caption_container import CaptionContext
        self.ctx: CaptionContext = context


    def onTabEnabled(self):
        pass

    def onTabDisabled(self):
        pass
