import os
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
import qtlib, util
from infer import InferenceSettingsWidget
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
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 1)

        txtSysPrompt = QtWidgets.QTextEdit()
        txtSysPrompt.setText(Config.inferSystemPrompt)
        qtlib.setMonospace(txtSysPrompt)
        qtlib.setTextEditHeight(txtSysPrompt, 3)
        layout.addWidget(QtWidgets.QLabel("Sys Prompt:"), 0, 0, Qt.AlignTop)
        layout.addWidget(txtSysPrompt, 0, 1, 1, 3)
        
        txtPrompt = QtWidgets.QTextEdit()
        txtPrompt.setText(Config.inferPrompt)
        qtlib.setMonospace(txtPrompt)
        qtlib.setTextEditHeight(txtPrompt, 3)
        layout.addWidget(QtWidgets.QLabel("Prompt:"), 1, 0, Qt.AlignTop)
        layout.addWidget(txtPrompt, 1, 1, 1, 3)

        inferSettings = InferenceSettingsWidget()
        layout.addWidget(inferSettings, 2, 0, 1, 4)

        spinTagThreshold = QtWidgets.QDoubleSpinBox()
        spinTagThreshold.setRange(0.0, 1.0)
        spinTagThreshold.setSingleStep(0.05)
        spinTagThreshold.setValue(Config.inferTagThreshold)
        layout.addWidget(QtWidgets.QLabel("Tag Threshold:"), 3, 0, Qt.AlignTop)
        layout.addWidget(spinTagThreshold, 3, 1, 1, 3)

        self.btnGenerateCap = QtWidgets.QPushButton("Append Caption")
        self.btnGenerateCap.clicked.connect(lambda: self.generateCaption(txtPrompt.toPlainText(), txtSysPrompt.toPlainText(), inferSettings.toDict()))
        layout.addWidget(self.btnGenerateCap, 4, 0, 1, 2)

        self.btnGenerateTags = QtWidgets.QPushButton("Append Tags")
        self.btnGenerateTags.clicked.connect(lambda: self.generateTags(spinTagThreshold.value()))
        layout.addWidget(self.btnGenerateTags, 4, 2, 1, 2)

        self.setLayout(layout)


    def generateCaption(self, prompt, sysPrompt, config={}):
        self.btnGenerateCap.setEnabled(False)
        self.btnGenerateTags.setEnabled(False)

        file = self.ctx.tab.imgview.image.filepath
        prompts = util.parsePrompts(prompt)

        from infer import Inference
        failHandler = lambda: self.onCaptionGenerated(None, None)
        Inference().captionAsync(self.onCaptionGenerated, failHandler, file, prompts, sysPrompt, config)

    @Slot()
    def onCaptionGenerated(self, imgPath, captions: dict):
        self.btnGenerateCap.setEnabled(True)
        self.btnGenerateTags.setEnabled(True)

        if captions and imgPath == self.ctx.tab.imgview.image.filepath:
            parts = (cap for name, cap in captions.items())
            text = os.linesep.join(parts)
            self.ctx.captionGenerated.emit(text)


    def generateTags(self, threshold):
        self.btnGenerateCap.setEnabled(False)
        self.btnGenerateTags.setEnabled(False)

        file = self.ctx.tab.imgview.image.filepath

        from infer import Inference
        failHandler = lambda: self.onTagsGenerated(None, None)
        Inference().tagAsync(self.onTagsGenerated, failHandler, file, threshold)

    @Slot()
    def onTagsGenerated(self, imgPath, tags: str):
        self.btnGenerateCap.setEnabled(True)
        self.btnGenerateTags.setEnabled(True)

        if tags and imgPath == self.ctx.tab.imgview.image.filepath:
            self.ctx.captionGenerated.emit(tags)
