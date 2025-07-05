from enum import Enum
from PySide6 import QtWidgets


class MultiEditSupport(Enum):
    Disabled       = 0
    PreferDisabled = 1
    Full           = 2



class CaptionTab(QtWidgets.QWidget):
    def __init__(self, context):
        super().__init__()

        from .caption_context import CaptionContext
        self.ctx: CaptionContext = context


    def getMultiEditSupport(self) -> MultiEditSupport:
        return MultiEditSupport.Full


    def onTabEnabled(self):
        pass

    def onTabDisabled(self):
        pass
