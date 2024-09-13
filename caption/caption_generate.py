import os
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, Signal, QRunnable, QObject
import qtlib, util
from infer import Inference, InferenceSettingsWidget
from config import Config


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

        self.txtSysPrompt = QtWidgets.QTextEdit()
        self.txtSysPrompt.setText(Config.inferSystemPrompt)
        qtlib.setMonospace(self.txtSysPrompt)
        qtlib.setTextEditHeight(self.txtSysPrompt, 3)
        layout.addWidget(QtWidgets.QLabel("Sys Prompt:"), 0, 0, Qt.AlignTop)
        layout.addWidget(self.txtSysPrompt, 0, 1, 1, 5)
        
        self.txtPrompt = QtWidgets.QTextEdit()
        self.txtPrompt.setText(Config.inferPrompt)
        qtlib.setMonospace(self.txtPrompt)
        qtlib.setTextEditHeight(self.txtPrompt, 3)
        layout.addWidget(QtWidgets.QLabel("Prompt:"), 1, 0, Qt.AlignTop)
        layout.addWidget(self.txtPrompt, 1, 1, 1, 5)

        self.inferSettings = InferenceSettingsWidget()
        layout.addWidget(self.inferSettings, 2, 0, 1, 6)

        self.spinTagThreshold = QtWidgets.QDoubleSpinBox()
        self.spinTagThreshold.setRange(0.0, 1.0)
        self.spinTagThreshold.setSingleStep(0.05)
        self.spinTagThreshold.setValue(Config.inferTagThreshold)
        layout.addWidget(QtWidgets.QLabel("Tag Threshold:"), 3, 0, Qt.AlignTop)
        layout.addWidget(self.spinTagThreshold, 3, 1)

        self.cboMode = QtWidgets.QComboBox()
        self.cboMode.addItem("Append")
        self.cboMode.addItem("Prepend")
        self.cboMode.addItem("Replace")
        layout.addWidget(self.cboMode, 3, 3)

        self.cboCapTag = QtWidgets.QComboBox()
        self.cboCapTag.addItem("Caption")
        self.cboCapTag.addItem("Tags")
        self.cboCapTag.addItem("Caption, Tags")
        self.cboCapTag.addItem("Tags, Caption")
        layout.addWidget(self.cboCapTag, 3, 4)

        self.btnGenerate = QtWidgets.QPushButton("Generate")
        #self.btnGenerate.clicked.connect(lambda: self.generateCaption(txtPrompt.toPlainText(), txtSysPrompt.toPlainText(), inferSettings.toDict()))
        self.btnGenerate.clicked.connect(self.generate)
        layout.addWidget(self.btnGenerate, 3, 5)

        self.setLayout(layout)


    def generate(self):
        self.btnGenerate.setEnabled(False)

        file = self.ctx.tab.imgview.image.filepath
        content = self.cboCapTag.currentText().lower().split(", ")

        task = InferenceTask(file, content)
        task.tagThreshold = self.spinTagThreshold.value()
        task.signals.done.connect(self.onGenerated)
        task.signals.fail.connect(self.onFail)

        if "caption" in content:
            task.prompts = util.parsePrompts(self.txtPrompt.toPlainText())
            task.systemPrompt = self.txtSysPrompt.toPlainText()
            task.config = self.inferSettings.toDict()
        
        Inference().queueTask(task)

    @Slot()
    def onGenerated(self, imgPath, text):
        self.btnGenerate.setEnabled(True)

        if text and imgPath == self.ctx.tab.imgview.image.filepath:
            mode = self.cboMode.currentText()
            self.ctx.captionGenerated.emit(text, mode)

    def onFail(self):
        self.btnGenerate.setEnabled(True)



class InferenceTask(QRunnable):
    class Signals(QObject):
        done = Signal(str, str)
        fail = Signal()

    def __init__(self, imgPath, content: [str]):
        super().__init__()
        self.signals = InferenceTask.Signals()
        self.imgPath = imgPath
        self.content = content

        self.prompts      = None
        self.systemPrompt = None
        self.config       = None

        self.tagThreshold = None


    @Slot()
    def run(self):
        try:
            inferProc = Inference().proc
            inferProc.start()

            results = []

            for c in self.content:
                if c == "caption":
                    inferProc.setupCaption(self.config)
                    captions = inferProc.caption(self.imgPath, self.prompts, self.systemPrompt)
                    if captions != None:
                        parts = (cap for name, cap in captions.items())
                        results.append( os.linesep.join(parts) )
                    else:
                        self.signals.fail.emit()
                
                if c == "tags":
                    inferProc.setupTag(self.tagThreshold)
                    tags = inferProc.tag(self.imgPath)
                    if tags != None:
                        results.append(tags)
                    else:
                        self.signals.fail.emit()

            text = os.linesep.join(results)
            self.signals.done.emit(self.imgPath, text)
        except Exception as ex:
            print("Error during inference:")
            print(ex)
            self.signals.fail.emit()
