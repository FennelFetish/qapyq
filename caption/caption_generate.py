import os, time, re, traceback, weakref
from typing import Iterable
from enum import Enum
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, Signal, QThreadPool, QRunnable, QObject, QMutex, QMutexLocker
from infer.inference import Inference
from infer.inference_proc import InferenceProcess
from infer.inference_settings import InferencePresetWidget, RemoteInferenceConfig
from infer.tag_settings import TagPresetWidget
from infer.prompt import PromptWidget
from infer.prompt_struct import Conversation, PromptUtil
from lib.template_parser import TemplateVariableParser
from lib.filelist import DataKeys
from lib import qtlib, util
from .caption_tab import CaptionTab, MultiEditSupport
from .caption_context import CaptionContext


CONTENT_CAPTION = "caption"
CONTENT_TAG     = "tags"


class ApplyMode(Enum):
    Append  = "append"
    Prepend = "prepend"
    Replace = "replace"


class CaptionGenerate(CaptionTab):
    def __init__(self, context):
        super().__init__(context)
        self._task: InferenceTask | None = None

        self._parser = CurrentVariableParser(context)
        self._hasCurrentVar = False
        self._hasRefinedVar = False

        self._build()

        self.ctx.controlUpdated.connect(self._onControlUpdated)
        self.ctx.captionEdited.connect(self._onCaptionEdited)

        self.ctx.tab.filelist.addSelectionListener(self)


    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnStretch(0, 1)

        row = 0
        self.promptWidget = PromptWidget("promptCaptionPresets", "promptCaptionDefault", self.ctx.tab.templateAutoCompleteSources, parser=self._parser)
        qtlib.setTextEditHeight(self.promptWidget.txtSystemPrompt, 3, "min")
        qtlib.setTextEditHeight(self.promptWidget.txtPrompts, 3, "min")
        qtlib.setTextEditHeight(self.promptWidget.txtPreview, 3, "min")
        self.promptWidget.txtPrompts.textChanged.connect(self._onPromptChanged)
        self.promptWidget.refreshPreviewClicked.connect(self._refreshPreview)
        layout.addWidget(self.promptWidget, row, 0, 1, 4)
        layout.setRowStretch(row, 1)

        row += 1
        self.inferSettings = InferencePresetWidget()
        layout.addWidget(self.inferSettings, row, 0, 1, 4)

        row += 1
        self.tagSettings = TagPresetWidget()
        layout.addWidget(self.tagSettings, row, 0, 1, 4)

        row += 1
        self.statusBar = qtlib.ColoredMessageStatusBar()
        self.statusBar.layout().setContentsMargins(0, 0, 8, 0)
        self.statusBar.setSizeGripEnabled(False)
        layout.addWidget(self.statusBar, row, 0)

        self.cboMode = QtWidgets.QComboBox()
        self.cboMode.addItem("Append", ApplyMode.Append)
        self.cboMode.addItem("Prepend", ApplyMode.Prepend)
        self.cboMode.addItem("Replace", ApplyMode.Replace)
        layout.addWidget(self.cboMode, row, 1)

        self.cboCapTag = QtWidgets.QComboBox()
        self.cboCapTag.addItem(CONTENT_CAPTION.title())
        self.cboCapTag.addItem(CONTENT_TAG.title())
        self.cboCapTag.addItem(f"{CONTENT_CAPTION}, {CONTENT_TAG}".title())
        self.cboCapTag.addItem(f"{CONTENT_TAG}, {CONTENT_CAPTION}".title())
        layout.addWidget(self.cboCapTag, row, 2)

        self.btnGenerate = QtWidgets.QPushButton("Generate")
        self.btnGenerate.setMinimumWidth(100)
        self.btnGenerate.clicked.connect(self.generate)
        layout.addWidget(self.btnGenerate, row, 3)
        self._updateGenerateButton()

        self.setLayout(layout)


    def getMultiEditSupport(self) -> MultiEditSupport:
        return MultiEditSupport.PreferDisabled

    def onFileChanged(self, currentFile: str):
        self._parser.setup(currentFile)
        self._onPromptChanged()

    def onFileSelectionChanged(self, selectedFiles: set[str]):
        if self._task is None:
            self._updateGenerateButton()

    @Slot()
    def _refreshPreview(self):
        self.onFileChanged(self.ctx.tab.filelist.getCurrentFile())

    @Slot()
    def _onControlUpdated(self):
        if self._hasRefinedVar:
            self.updatePreview()

    @Slot()
    def _onCaptionEdited(self):
        if self._hasCurrentVar or self._hasRefinedVar:
            self.updatePreview()

    @Slot()
    def _onPromptChanged(self):
        prompt = self.promptWidget.prompts
        self._hasCurrentVar = CurrentVariableParser.currentInPrompt(prompt)
        self._hasRefinedVar = CurrentVariableParser.refinedInPrompt(prompt)
        self.updatePreview()

    def updatePreview(self):
        if self._hasRefinedVar:
            self._parser.updateRefinedCaption(self.ctx.text.getCaption())

        hasVars = self.promptWidget.updatePreview()
        self.promptWidget.setPreviewVisible(hasVars)

    def _updateGenerateButton(self):
        text = "Generate"
        numSelected = len(self.ctx.tab.filelist.selectedFiles)
        if numSelected > 1:
            text += f" ({numSelected})"
        self.btnGenerate.setText(text)


    @Slot()
    def generate(self):
        if self._task:
            self._task.abort()
            self.statusBar.showMessage("Aborting ...")
            return

        filelist = self.ctx.tab.filelist
        currentFile = filelist.getCurrentFile()

        files = filelist.selection.sorted.copy()
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
        task.progress.connect(self.onProgress, Qt.ConnectionType.QueuedConnection)
        task.generated.connect(self.onGenerated, Qt.ConnectionType.QueuedConnection)
        task.done.connect(self.onDone, Qt.ConnectionType.QueuedConnection)
        task.fail.connect(self.onFail, Qt.ConnectionType.QueuedConnection)

        if CONTENT_CAPTION in content:
            self.onFileChanged(currentFile) # Update parser
            task.varParser = FrozenCurrentVariableParser(self.ctx, self.promptWidget.prompts, files)

            task.prompts = self.promptWidget.getParsedPrompts()
            task.systemPrompt = self.promptWidget.systemPrompt.strip()
            task.configs = self.inferSettings.getRemoteInferenceConfig()

        if CONTENT_TAG in content:
            task.tagConfig = self.tagSettings.getInferenceConfig()

        self._task = task
        QThreadPool.globalInstance().start(QRunnable.create(task))


    def _finishTask(self):
        self._updateGenerateButton()
        self._task = None

    @Slot(str)
    def onProgress(self, message: str):
        self.statusBar.showMessage(message)

    @Slot(int, int, float)
    def onDone(self, numDone: int, numTotal: int, timeMs: float):
        self._finishTask()

        timeStr = util.formatTime(timeMs) if timeMs > 2000.0 else f"{int(timeMs)} ms"

        if numTotal > 1:
            timePerFile = timeMs / numTotal
            statusMsg = f"Generated {numDone}/{numTotal} captions in {timeStr}"
            logMsg    = f"Generated {numDone}/{numTotal} captions in {timeMs:.02f} ms ({timePerFile:.02f} ms per file)"
        else:
            statusMsg = f"Generated caption in {timeStr}"
            logMsg    = f"Generated caption in {timeMs:.02f} ms"

        self.statusBar.showColoredMessage(statusMsg, True)
        print(logMsg)

    @Slot(int, int, str)
    def onFail(self, numDone: int, numTotal: int, errorMsg: str):
        self._finishTask()
        errorMsg = f"[{numDone}/{numTotal}] {errorMsg}"
        self.statusBar.showColoredMessage(errorMsg, False, 0)

    @Slot(str, str)
    def onGenerated(self, imgPath: str, generatedText: str):
        assert generatedText

        filelist = self.ctx.tab.filelist
        multiEditActive = self.ctx.container.multiEdit.active
        multiEditActive &= imgPath in filelist.selectedFiles
        if multiEditActive:
            self.ctx.container.multiEdit.clear()  # Save state

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

    def _getImgProperties(self, var: str, args) -> str | None:
        match var:
            case self.CURRENT_VAR_NAME:
                return self.ctx.text.getCaption()
            case self.REFINED_VAR_NAME:
                return self.refinedCaption

        return super()._getImgProperties(var, args)

    @classmethod
    def currentInPrompt(cls, prompt: str) -> bool:
        return cls.CURRENT_VAR_PATTERN.search(prompt) is not None

    @classmethod
    def refinedInPrompt(cls, prompt: str) -> bool:
        return cls.REFINED_VAR_PATTERN.search(prompt) is not None


class FrozenCurrentVariableParser(TemplateVariableParser):
    def __init__(self, context: CaptionContext, prompt: str, imgPaths: Iterable[str]):
        super().__init__()
        self.stripAround = False
        self.stripMultiWhitespace = False
        self.currentCaptions = dict[str, str | None]()

        needsRefined = CurrentVariableParser.refinedInPrompt(prompt)
        if needsRefined or CurrentVariableParser.currentInPrompt(prompt):
            filelist = context.tab.filelist
            srcSelector = context.container.srcSelector

            for file in imgPaths:
                caption = filelist.getData(file, DataKeys.Caption)
                if caption is None:
                    caption = srcSelector.loadCaption(file)
                self.currentCaptions[file] = caption

        self.rulesProcessor = context.createRulesProcessor() if needsRefined else None

    def _getImgProperties(self, var: str, args) -> str | None:
        match var:
            case CurrentVariableParser.CURRENT_VAR_NAME:
                return self.currentCaptions.get(self.imgPath)
            case CurrentVariableParser.REFINED_VAR_NAME:
                if caption := self.currentCaptions.get(self.imgPath):
                    return self.rulesProcessor.process(caption)
                return None

        return super()._getImgProperties(var, args)



class InferenceTask(QObject):
    MULTIPROC_MIN_FILES_TAG = 16
    MULTIPROC_MIN_FILES_CAPTION = 2

    progress = Signal(str)          # message
    generated = Signal(str, str)    # file, text
    done = Signal(int, int, float)  # num done, num total, time [ms]
    fail = Signal(int, int, str)    # num done, num total, message

    def __init__(self, files: list[str], content: list[str]):
        super().__init__()

        self.files = files
        self.content = content

        self.varParser: FrozenCurrentVariableParser = None
        self.prompts: list[Conversation] = []
        self.systemPrompt: str = None
        self.configs: RemoteInferenceConfig = None
        self.tagConfig: dict = None

        self._mutex = QMutex()
        self._aborted = False

        self.weakSession = None


    def abort(self):
        with QMutexLocker(self._mutex):
            self._aborted = True
            if (self.weakSession is not None) and (session := self.weakSession()):
                session.abort()

    def isAborted(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._aborted


    def getMaxProcs(self) -> int:
        if CONTENT_CAPTION in self.content:
            if len(self.files) >= self.MULTIPROC_MIN_FILES_CAPTION:
                return -1
        elif CONTENT_TAG in self.content:
            if len(self.files) >= self.MULTIPROC_MIN_FILES_TAG:
                return -1
        return 1


    def __call__(self):
        res: dict
        tags: list[str]
        captions: dict[str, str]

        numResults = 0

        try:
            contentText = " and ".join(self.content)
            progressText = f"Generating {contentText} ({{}}/{len(self.files)}) ..."

            hiddenPromptNames = set(info.name for info in PromptUtil.filter(self.prompts, lambda info: info.hidden))

            maxProcs = self.getMaxProcs()
            with Inference().createSession(maxProcs) as session:
                with QMutexLocker(self._mutex):
                    self.weakSession = weakref.ref(session)

                self.progress.emit(f"Loading {contentText} model ...")
                session.prepare(self.prepare, lambda: self.progress.emit(progressText.format(0)))

                tStart = time.monotonic_ns()

                for fileNr, (file, results, exception) in enumerate(session.queueFiles(self.files, self.check), 1):
                    if exception:
                        raise exception

                    if self.isAborted():
                        self.fail.emit(numResults, len(self.files), f"Aborted")
                        return

                    self.progress.emit(progressText.format(fileNr))

                    allResults = []
                    for res in results:
                        if tags := res.get("tags"):
                            allResults.append(tags)
                        elif captions := res.get("captions"):
                            allResults.extend(cap for name, cap in captions.items() if name not in hiddenPromptNames)

                    if allResults:
                        if text := os.linesep.join(allResults):
                            self.generated.emit(file, text)
                            numResults += 1
                        else:
                            print(f"WARNING: Empty caption generated for '{file}'")
                    else:
                        print(f"WARNING: No caption generated for '{file}'")

            if numResults > 0:
                tMs = (time.monotonic_ns() - tStart) / 1_000_000
                self.done.emit(numResults, len(self.files), tMs)
            else:
                self.fail.emit(numResults, len(self.files), "No captions generated")

        except Exception as ex:
            traceback.print_exc()
            self.fail.emit(numResults, len(self.files), str(ex))


    def prepare(self, proc: InferenceProcess):
        for c in self.content:
            if c == CONTENT_CAPTION:
                proc.setupCaption(self.configs.getHostConfig(proc.procCfg.hostName))
            elif c == CONTENT_TAG:
                proc.setupTag(self.tagConfig)

    def check(self, file: str, proc: InferenceProcess):
        def queue():
            for c in self.content:
                if c == CONTENT_CAPTION:
                    prompts = PromptUtil.parsePrompts(self.varParser, file, None, self.prompts)
                    proc.caption(file, prompts, self.systemPrompt)
                elif c == CONTENT_TAG:
                    proc.tag(file)
        return queue
