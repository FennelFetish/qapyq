import os, traceback
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, Signal, QRunnable, QObject
from infer import Inference, InferencePresetWidget, TagPresetWidget, PromptWidget
import qtlib


class CaptionGenerate(QtWidgets.QWidget):
    def __init__(self, context):
        super().__init__()
        self.ctx = context

        self._build()


    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)
        layout.setColumnStretch(3, 0)
        layout.setColumnStretch(4, 0)
        layout.setColumnStretch(5, 0)

        row = 0
        self.promptWidget = PromptWidget("promptCaptionPresets", "promptCaptionDefault")
        qtlib.setTextEditHeight(self.promptWidget.txtSystemPrompt, 3)
        qtlib.setTextEditHeight(self.promptWidget.txtPrompts, 3)
        layout.addWidget(self.promptWidget, row, 0, 1, 6)

        row += 1
        self.inferSettings = InferencePresetWidget()
        layout.addWidget(self.inferSettings, row, 0, 1, 6)

        row += 1
        self.tagSettings = TagPresetWidget()
        layout.addWidget(self.tagSettings, row, 0, 2, 2)

        #row += 1
        self.cboMode = QtWidgets.QComboBox()
        self.cboMode.addItem("Append")
        self.cboMode.addItem("Prepend")
        self.cboMode.addItem("Replace")
        layout.addWidget(self.cboMode, row, 3)

        self.cboCapTag = QtWidgets.QComboBox()
        self.cboCapTag.addItem("Caption")
        self.cboCapTag.addItem("Tags")
        self.cboCapTag.addItem("Caption, Tags")
        self.cboCapTag.addItem("Tags, Caption")
        layout.addWidget(self.cboCapTag, row, 4)

        self.btnGenerate = QtWidgets.QPushButton("Generate")
        self.btnGenerate.clicked.connect(self.generate)
        layout.addWidget(self.btnGenerate, row, 5)

        row += 1
        self.statusBar = qtlib.ColoredMessageStatusBar()
        self.statusBar.layout().setContentsMargins(50, 0, 8, 0)
        self.statusBar.setSizeGripEnabled(False)
        layout.addWidget(self.statusBar, row, 2, 1, 4)

        self.setLayout(layout)


    def generate(self):
        self.btnGenerate.setEnabled(False)
        self.statusBar.showMessage("Starting ...")

        file = self.ctx.tab.imgview.image.filepath
        content = self.cboCapTag.currentText().lower().split(", ")

        task = InferenceTask(file, content)
        task.signals.progress.connect(self.onProgress)
        task.signals.done.connect(self.onGenerated)
        task.signals.fail.connect(self.onFail)

        if "caption" in content:
            task.prompts = self.promptWidget.getParsedPrompts()
            task.systemPrompt = self.promptWidget.systemPrompt
            task.config = self.inferSettings.getInferenceConfig()

        if "tags" in content:
            task.tagConfig = self.tagSettings.getInferenceConfig()
        
        Inference().queueTask(task)

    @Slot()
    def onProgress(self, message):
        self.statusBar.showMessage(message)

    @Slot()
    def onGenerated(self, imgPath, text):
        self.btnGenerate.setEnabled(True)

        if imgPath == self.ctx.tab.imgview.image.filepath:
            if text:
                mode = self.cboMode.currentText()
                self.ctx.captionGenerated.emit(text, mode)
                self.statusBar.showColoredMessage("Done", True)
            else:
                self.statusBar.showColoredMessage("Finished with empty result", False, 0)

    @Slot()
    def onFail(self, errorMsg):
        self.btnGenerate.setEnabled(True)
        self.statusBar.showColoredMessage(errorMsg, False, 0)



class InferenceTask(QRunnable):
    class Signals(QObject):
        progress = Signal(str)
        done = Signal(str, str)
        fail = Signal(str)

    def __init__(self, imgPath, content: [str]):
        super().__init__()
        self.signals = InferenceTask.Signals()
        self.imgPath = imgPath
        self.content = content

        self.prompts      = None
        self.systemPrompt = None
        self.config       = None
        self.tagConfig    = None


    @Slot()
    def run(self):
        try:
            inferProc = Inference().proc
            inferProc.start()

            results = []
            for c in self.content:
                if c == "caption":
                    results.append( self.runCaption(inferProc) )
                elif c == "tags":
                    results.append( self.runTags(inferProc) )

            text = os.linesep.join(results)
            self.signals.done.emit(self.imgPath, text)
        except Exception as ex:
            errorMsg = f"Error during inference: {str(ex)}"
            print(errorMsg)
            traceback.print_exc()
            self.signals.fail.emit(errorMsg)

    def runCaption(self, inferProc) -> str:
        self.signals.progress.emit("Loading caption model ...")
        if not inferProc.setupCaption(self.config):
            raise RuntimeError("Couldn't load caption model")

        self.signals.progress.emit("Generating caption ...")
        captions = inferProc.caption(self.imgPath, self.prompts, self.systemPrompt)
        parts = (cap for name, cap in captions.items())
        return os.linesep.join(parts)

    def runTags(self, inferProc) -> str:
        self.signals.progress.emit("Loading tag model ...")
        if not inferProc.setupTag(self.tagConfig):
            raise RuntimeError("Couldn't load tag model")
        
        self.signals.progress.emit("Generating tags ...")
        return inferProc.tag(self.imgPath)
