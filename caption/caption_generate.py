import os, re, traceback
from enum import Enum
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, Signal, QThreadPool, QRunnable, QObject, QSignalBlocker, QMutex, QMutexLocker
from infer.inference import Inference
from infer.inference_proc import InferenceProcess
from infer.inference_settings import InferencePresetWidget
from infer.tag_settings import TagPresetWidget
from infer.prompt import PromptWidget, PromptsHighlighter
from lib.template_parser import TemplateVariableParser, VariableHighlighter
from lib.filelist import DataKeys
import lib.qtlib as qtlib
from config import Config
from .caption_tab import CaptionTab
from .caption_context import CaptionContext


class ApplyMode(Enum):
    Append  = "append"
    Prepend = "prepend"
    Replace = "replace"


class CaptionGenerate(CaptionTab):
    def __init__(self, context):
        super().__init__(context)

        self._highlighter = VariableHighlighter()
        self._parser = CurrentVariableParser(context)

        self._hasCurrentVar = False
        self._hasRefinedVar = False

        self._task = None

        self._build()

        self.ctx.controlUpdated.connect(self._onControlUpdated)
        self.ctx.captionEdited.connect(self._onCaptionEdited)


    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)
        layout.setColumnStretch(3, 0)
        layout.setColumnStretch(4, 0)
        layout.setColumnStretch(5, 0)

        row = 0
        self.promptWidget = PromptWidget("promptCaptionPresets", "promptCaptionDefault")
        self.promptWidget.enableHighlighting()
        qtlib.setTextEditHeight(self.promptWidget.txtSystemPrompt, 3, "min")
        qtlib.setTextEditHeight(self.promptWidget.txtPrompts, 3, "min")
        self.promptWidget.lblPrompts.setText("Prompt(s) Template:")
        self.promptWidget.txtPrompts.textChanged.connect(self._onPromptChanged)
        self.promptWidget.layout().setRowStretch(1, 1)
        self.promptWidget.layout().setRowStretch(2, 1)
        layout.addWidget(self.promptWidget, row, 0, 1, 6)
        layout.setRowStretch(row, 2)

        row += 1
        self.lblPromptPreview = QtWidgets.QLabel("Prompt(s) Preview:")
        layout.addWidget(self.lblPromptPreview, row, 0, Qt.AlignmentFlag.AlignTop)

        self.txtPromptPreview = QtWidgets.QPlainTextEdit()
        self.txtPromptPreview.setReadOnly(True)
        qtlib.setMonospace(self.txtPromptPreview)
        qtlib.setTextEditHeight(self.txtPromptPreview, 3, "min")
        qtlib.setShowWhitespace(self.txtPromptPreview)
        layout.addWidget(self.txtPromptPreview, row, 1, 1, 5)
        layout.setRowStretch(row, 2)

        row += 1
        self.inferSettings = InferencePresetWidget()
        layout.addWidget(self.inferSettings, row, 0, 1, 6)

        row += 1
        self.tagSettings = TagPresetWidget()
        layout.addWidget(self.tagSettings, row, 0, 2, 2)

        self.cboMode = QtWidgets.QComboBox()
        self.cboMode.addItem("Append", ApplyMode.Append)
        self.cboMode.addItem("Prepend", ApplyMode.Prepend)
        self.cboMode.addItem("Replace", ApplyMode.Replace)
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


    def onFileChanged(self, currentFile: str):
        self._parser.setup(currentFile)
        self._onPromptChanged()

    @Slot()
    def _onControlUpdated(self):
        if self._hasRefinedVar:
            self.updatePreview(self.promptWidget.prompts)

    @Slot()
    def _onCaptionEdited(self, caption: str):
        if self._hasCurrentVar or self._hasRefinedVar:
            self.updatePreview(self.promptWidget.prompts)

    @Slot()
    def _onPromptChanged(self):
        prompt = self.promptWidget.prompts
        self._hasCurrentVar = CurrentVariableParser.currentInPrompt(prompt)
        self._hasRefinedVar = CurrentVariableParser.refinedInPrompt(prompt)
        self.updatePreview(prompt)


    def updatePreview(self, prompt: str):
        if self._hasRefinedVar:
            self._parser.updateRefinedCaption(self.ctx.text.getCaption())

        preview, varPositions = self._parser.parseWithPositions(prompt)
        self.txtPromptPreview.setPlainText(preview)

        with QSignalBlocker(self.promptWidget.txtPrompts):
            self._highlighter.highlight(self.promptWidget.txtPrompts, self.txtPromptPreview, varPositions)
            PromptsHighlighter.highlightPromptSeparators(self.promptWidget.txtPrompts)
            PromptsHighlighter.highlightPromptSeparators(self.txtPromptPreview)

        # Update visibility of preview
        previewVisible = len(varPositions) > 0
        self.lblPromptPreview.setVisible(previewVisible)
        self.txtPromptPreview.setVisible(previewVisible)
        self.layout().setRowStretch(1, 2 if previewVisible else 0)


    @Slot()
    def generate(self):
        if self._task:
            self._task.abort()
            return

        filelist = self.ctx.tab.filelist
        currentFile = filelist.getCurrentFile()

        files = list(filelist.selectedFiles)
        if not files:
            if currentFile:
                files.append(currentFile)
            else:
                QtWidgets.QMessageBox.information(self, "No Image Loaded", "Please load an image into the Main Window first.")
                return

        self.btnGenerate.setText("Abort")
        self.statusBar.showMessage("Starting ...")

        content = self.cboCapTag.currentText().lower().split(", ")

        task = InferenceTask(files, content)
        task.signals.progress.connect(self.onProgress)
        task.signals.done.connect(self.onGenerated)
        task.signals.fail.connect(self.onFail)

        if "caption" in content:
            self.onFileChanged(currentFile) # Update parser
            task.varParser = self._parser.freeze()

            task.prompts = self.promptWidget.getParsedPrompts()
            task.systemPrompt = self.promptWidget.systemPrompt.strip()
            task.config = self.inferSettings.getInferenceConfig()

        if "tags" in content:
            task.tagConfig = self.tagSettings.getInferenceConfig()

        self._task = task
        QThreadPool.globalInstance().start(task)


    def _finishTask(self):
        self.btnGenerate.setText("Generate")
        self._task = None

    @Slot()
    def onProgress(self, message):
        self.statusBar.showMessage(message)

    @Slot()
    def onFail(self, errorMsg: str):
        self._finishTask()
        self.statusBar.showColoredMessage(errorMsg, False, 0)

    @Slot()
    def onGenerated(self, fileResults: dict[str, str]):
        self._finishTask()

        if not fileResults:
            self.statusBar.showColoredMessage("Finished with empty result", False, 0)
            return

        self.statusBar.showColoredMessage("Done", True)

        filelist = self.ctx.tab.filelist
        multiEditActive = self.ctx.container.multiEdit.active
        multiEditActive &= not filelist.selectedFiles.isdisjoint(fileResults.keys())
        if multiEditActive:
            self.ctx.container.multiEdit.clear()  # Save state

        for imgPath, generatedText in fileResults.items():
            if not multiEditActive and imgPath == filelist.getCurrentFile():
                text = self._addToCaption(generatedText, self.ctx.text.getCaption())
                self.ctx.text.setCaption(text)
                self.ctx.needsRulesApplied.emit()
            else:
                existingText = filelist.getData(imgPath, DataKeys.Caption)
                if existingText is None:
                    existingText = self.ctx.container.srcSelector.loadCaption(imgPath)

                text = self._addToCaption(generatedText, existingText)
                filelist.setData(imgPath, DataKeys.Caption, text)
                filelist.setData(imgPath, DataKeys.CaptionState, DataKeys.IconStates.Changed)

        if multiEditActive:
            self.ctx.container.onFileSelectionChanged(filelist.selectedFiles)  # Reload


    def _addToCaption(self, generatedText: str, existingText: str | None) -> str:
        if not existingText:
            return generatedText

        match self.cboMode.currentData():
            case ApplyMode.Append:  return f"{existingText}{os.linesep}{generatedText}"
            case ApplyMode.Prepend: return f"{generatedText}{os.linesep}{existingText}"
            case ApplyMode.Replace: return generatedText
            case _:
                raise ValueError("Invalid mode")



class CurrentVariableParser(TemplateVariableParser):
    CURRENT_VAR_NAME = "current"
    CURRENT_VAR_PATTERN = re.compile(r'{{.*current.*}}')

    REFINED_VAR_NAME  = "refined"
    REFINED_VAR_PATTERN = re.compile(r'{{.*refined.*}}')


    def __init__(self, context: CaptionContext, imgPath: str = None):
        super().__init__(imgPath)
        self.ctx = context
        self.currentCaption = ""
        self.refinedCaption = ""

        self.stripAround = False
        self.stripMultiWhitespace = False

    def updateRefinedCaption(self, caption: str):
        self.refinedCaption = self.ctx.rulesProcessor().process(caption)

    def _getImgProperties(self, var: str) -> str | None:
        match var:
            case self.CURRENT_VAR_NAME:
                return self.currentCaption or self.ctx.text.getCaption()
            case self.REFINED_VAR_NAME:
                return self.refinedCaption

        return super()._getImgProperties(var)

    @classmethod
    def currentInPrompt(cls, prompt: str) -> bool:
        return cls.CURRENT_VAR_PATTERN.search(prompt) is not None

    @classmethod
    def refinedInPrompt(cls, prompt: str) -> bool:
        return cls.REFINED_VAR_PATTERN.search(prompt) is not None

    def freeze(self):
        varParser = CurrentVariableParser(None)
        varParser.currentCaption = self.ctx.text.getCaption()
        varParser.refinedCaption = self.refinedCaption
        return varParser



class InferenceTask(QRunnable):
    CONTENT_CAPTION = "caption"
    CONTENT_TAG = "tags"

    MULTIPROC_MIN_FILES_TAG = 16
    MULTIPROC_MIN_FILES_CAPTION = 2

    class Signals(QObject):
        progress = Signal(str)
        done = Signal(dict)
        fail = Signal(str)

    def __init__(self, files: list[str], content: list[str]):
        super().__init__()
        self.setAutoDelete(False)
        self.signals = InferenceTask.Signals()

        self.files = files
        self.content = content

        self.varParser: CurrentVariableParser = None
        self.prompts: list[dict[str, str]] = None
        self.systemPrompt: str = None
        self.config: dict      = None
        self.tagConfig: dict   = None

        self._mutex = QMutex()
        self._aborted = False

        self.session = None


    def abort(self):
        self.signals.progress.emit("Aborting ...")
        with QMutexLocker(self._mutex):
            self._aborted = True
            if self.session:
                self.session.abort()

    def isAborted(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._aborted


    def getMaxProcs(self) -> int:
        if self.CONTENT_CAPTION in self.content:
            if len(self.files) >= self.MULTIPROC_MIN_FILES_CAPTION:
                return -1
        elif self.CONTENT_TAG in self.content:
            if len(self.files) >= self.MULTIPROC_MIN_FILES_TAG:
                return -1
        return 1


    @Slot()
    def run(self):
        try:
            contentText = " and ".join(self.content)
            progressText = f"Generating {contentText} ({{}}/{len(self.files)}) ..."

            maxProcs = self.getMaxProcs()
            with Inference().createSession(maxProcs) as session:
                with QMutexLocker(self._mutex):
                    self.session = session

                self.signals.progress.emit(f"Loading {contentText} model ...")
                session.prepare(self.prepare, lambda: self.signals.progress.emit(progressText.format(0)))

                fileResults = dict()
                for fileNr, (file, results, exception) in enumerate(session.queueFiles(self.files, self.check), 1):
                    if exception:
                        raise exception

                    if self.isAborted():
                        self.signals.fail.emit("Aborted")
                        return

                    self.signals.progress.emit(progressText.format(fileNr))

                    allResults = []
                    for res in results:
                        if tags := res.get("tags"):
                            allResults.append(tags)
                        elif captions := res.get("captions"):
                            allResults.extend(cap for name, cap in captions.items() if not name.startswith('?'))

                    fileResults[file] = os.linesep.join(allResults)

                self.signals.done.emit(fileResults)

        except Exception as ex:
            traceback.print_exc()
            self.signals.fail.emit(str(ex))
        finally:
            with QMutexLocker(self._mutex):
                self.session = None


    def prepare(self, proc: InferenceProcess):
        for c in self.content:
            if c == self.CONTENT_CAPTION:
                proc.setupCaption(self.config)
            elif c == self.CONTENT_TAG:
                proc.setupTag(self.tagConfig)

    def check(self, file: str, proc: InferenceProcess):
        def queue():
            for c in self.content:
                if c == self.CONTENT_CAPTION:
                    prompts = self.parsePrompts(file)
                    proc.caption(file, prompts, self.systemPrompt)
                elif c == self.CONTENT_TAG:
                    proc.tag(file)
        return queue

    def parsePrompts(self, imgFile: str) -> list:
        # TODO: It should take the current/refined for each file
        self.varParser.setup(imgFile)

        prompts = list()
        missingVars = set()
        for conv in self.prompts:
            prompts.append( {name: self.varParser.parse(prompt) for name, prompt in conv.items()} )
            missingVars.update(self.varParser.missingVars)

        if missingVars:
            print(f"WARNING: '{imgFile}' is missing values for variables: {', '.join(missingVars)}")

        return prompts
