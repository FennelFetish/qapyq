import traceback
from PySide6 import QtWidgets
from PySide6.QtCore import Signal, Slot, QObject, QRunnable, QThreadPool
from infer.inference import Inference
from config import Config
import lib.qtlib as qtlib
from .caption_context import CaptionContext


class CaptionTokens(QtWidgets.QLabel):
    def __init__(self, ctx: CaptionContext):
        self._active = Config.captionCountTokens

        text = "..." if self._active else ""
        super().__init__(text)

        self.textField = ctx.text
        self.filelist = ctx.tab.filelist

        ctx.captionEdited.connect(self.onTextUpdated)


    @Slot()
    def setActive(self, active: bool):
        Config.captionCountTokens = active
        self._active = active
        if active:
            self.setText("...")
            self.onTextUpdated(self.textField.getCaption())
        else:
            self.setText("")
            self.textField.setVerticalLines(None)
            Inference().quitTokenizerProcess()


    @Slot()
    def onTextUpdated(self, text: str):
        if not self._active:
            return

        file = self.filelist.getCurrentFile()
        task = TokenizeTask(file, text)
        task.signals.done.connect(self._onDone)
        task.signals.fail.connect(self._onFail)

        QThreadPool.globalInstance().start(task)

    @Slot()
    def _onDone(self, file: str, count: int, borders: list[int]):
        if not self._active:
            return

        if file != self.filelist.getCurrentFile():
            text = ""
            borders = None
        else:
            text = f"{count} Tokens"

        self.setText(text)
        self.setStyleSheet("")
        self.textField.setVerticalLines(borders)

    @Slot()
    def _onFail(self, error: str):
        if self._active:
            self.setText("Tokenizer Error")
            self.setStyleSheet(f"color: {qtlib.COLOR_RED}")



class TokenizeTask(QRunnable):
    CONFIG = {
        "backend": "tokens",
        "model_path": "./res/tokenizer/clip-vit-large-patch14"
    }

    class Signals(QObject):
        done = Signal(str, int, list)
        fail = Signal(str)

    def __init__(self, file: str, text: str):
        super().__init__()
        self.setAutoDelete(True)
        self.signals = self.Signals()

        self.file = file
        self.text = text

    def run(self):
        try:
            proc = Inference().getTokenizerProcess()
            count, borders = proc.countTokensWithBorders(self.CONFIG, self.text)
            self.signals.done.emit(self.file, count, borders)
        except Exception as ex:
            traceback.print_exc()
            self.signals.fail.emit(str(ex))
