from __future__ import annotations
import os, copy, time, traceback
from typing import NamedTuple
from abc import ABC, abstractmethod
from collections import defaultdict
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal, QRunnable, QObject, QThreadPool, QTimer, QSignalBlocker, QMutex, QMutexLocker
import numpy as np
import lib.qtlib as qtlib
from lib.filelist import FileList, DataKeys, naturalSort
from ui.tab import ImgTab
from config import Config
from infer.model_settings import ModelSettingsWindow
from infer.embedding import embedding_common as embed
from .gallery_grid import GalleryGrid


EMBED_FAILED = object()


class TextPrompt(NamedTuple):
    pos: str = ""
    neg: str = ""

    def __bool__(self):
        return bool(self.pos)

class ImagePrompt(dict[str, np.ndarray | None]):
    def setEmbeddings(self, filelist: FileList):
        for file in self.keys():
            self[file] = filelist.getData(file, DataKeys.Embedding)

    @staticmethod
    def fromList(files: list[str]) -> ImagePrompt:
        return ImagePrompt((f, None) for f in files)


class SortParams(NamedTuple):
    config: dict                        = {}
    prompt: TextPrompt | ImagePrompt    = TextPrompt()
    ascending: bool                     = False
    byFolder: bool                      = True

    def needsReload(self, currentParams: SortParams) -> bool:
        return self.config != currentParams.config



class GallerySortControl(QtWidgets.QWidget):
    CONFIG_ATTR = "inferEmbeddingPresets"
    BUTTON_TEXT = "Sort" #"⇅"

    DISABLED_PARAMS = SortParams()

    def __init__(self, tab: ImgTab, galleryGrid: GalleryGrid):
        super().__init__()
        self.tab = tab
        self.galleryGrid = galleryGrid

        self._sorted = False
        self._paramsCurrent: SortParams = self.DISABLED_PARAMS
        self._paramsRequested: SortParams = self.DISABLED_PARAMS

        self._taskEmbed: EmbedImagesTask | None = None
        self._taskSort: UpdateSortTask | None = None

        # This button is not in this widget, but added to status bar
        self.btnSort = qtlib.ToggleButton(self.BUTTON_TEXT)
        self.btnSort.setToolTip("Toggle semantic sorting by prompt similarity")
        self.btnSort.setFixedWidth(80)
        self.btnSort.toggled.connect(self._onSortToggled)

        self.setVisible(False)
        self._build()

        tab.filelist.addListener(self)


    def _build(self):
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(4, 1, 2, 0)
        layout.setSpacing(3)

        self.cboModelPreset = qtlib.MenuComboBox()
        self.cboModelPreset.setPlaceholderText("Embedding Model")
        self.cboModelPreset.setMaximumWidth(200)
        self.cboModelPreset.currentTextChanged.connect(self._onPresetChanged)
        layout.addWidget(self.cboModelPreset)

        selectedPreset = Config.inferSelectedPresets.get(self.CONFIG_ATTR)
        self.reloadPresetList(selectedPreset)
        ModelSettingsWindow.signals.presetListUpdated.connect(self._onPresetListChanged)

        layout.addSpacing(5)

        self.btnAscending = qtlib.ToggleButton("∇")
        self.btnAscending.setToolTip("Toggle ascending order")
        self.btnAscending.setFixedWidth(20)
        self.btnAscending.toggled.connect(self._onDirectionChanged)
        layout.addWidget(self.btnAscending)

        self.txtPrompt = QtWidgets.QLineEdit()
        self.txtPrompt.setPlaceholderText("Positive Prompt")
        qtlib.setMonospace(self.txtPrompt)
        self.txtPrompt.setMinimumWidth(200)
        self.txtPrompt.editingFinished.connect(self.updateSortByText)
        layout.addWidget(self.txtPrompt, 3)

        self.txtNegPrompt = QtWidgets.QLineEdit()
        self.txtNegPrompt.setPlaceholderText("Negative Prompt")
        qtlib.setMonospace(self.txtNegPrompt)
        self.txtNegPrompt.setMinimumWidth(200)
        self.txtNegPrompt.editingFinished.connect(self.updateSortByText)
        layout.addWidget(self.txtNegPrompt, 2)

        self.chkByFolder = QtWidgets.QCheckBox("By Folders")
        self.chkByFolder.setChecked(True)
        self.chkByFolder.toggled.connect(self.updateSort)
        layout.addWidget(self.chkByFolder)

        self.setLayout(layout)

        palette = self.txtPrompt.palette()
        self._textColorNormal = palette.color(QtGui.QPalette.ColorGroup.Normal, QtGui.QPalette.ColorRole.Text)
        self._textColorMuted  = palette.color(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Text)


    def _setTextPromptMuted(self, muted: bool):
        color = self._textColorMuted if muted else self._textColorNormal
        palette = self.txtPrompt.palette()
        palette.setColor(QtGui.QPalette.ColorRole.Text, color)

        self.txtPrompt.setPalette(palette)
        self.txtNegPrompt.setPalette(palette)


    @Slot()
    def _showModelSettings(self):
        ModelSettingsWindow.openInstance(self, self.CONFIG_ATTR, self.cboModelPreset.currentText())

    def reloadPresetList(self, selectName: str | None = None):
        self.cboModelPreset.clear()

        presets: dict = getattr(Config, self.CONFIG_ATTR)
        for name in sorted(presets.keys()):
            self.cboModelPreset.addItem(name)

        self.cboModelPreset.addSeparator()
        actOpenModelSettings = self.cboModelPreset.addMenuAction("Model Settings...")
        actOpenModelSettings.triggered.connect(self._showModelSettings)

        if selectName:
            index = self.cboModelPreset.findText(selectName)
        elif self.cboModelPreset.count() > 0:
            index = 0
        else:
            index = -1

        self.cboModelPreset.setCurrentIndex(index)

    @Slot()
    def _onPresetListChanged(self, attr):
        if attr == self.CONFIG_ATTR:
            currentName = self.cboModelPreset.currentText()
            with QSignalBlocker(self.cboModelPreset):
                self.reloadPresetList(currentName)

    @Slot()
    def _onPresetChanged(self, name: str):
        Config.inferSelectedPresets[self.CONFIG_ATTR] = name


    @Slot()
    def _adjustControlHeight(self):
        h = self.txtPrompt.height()
        if h > 10:
            self.cboModelPreset.setFixedHeight(h)
            self.btnAscending.setFixedHeight(h)

    @Slot()
    def _onSortToggled(self, enabled: bool):
        self.setVisible(enabled)
        if enabled:
            # Force controls to the same height after layouting
            QTimer.singleShot(0, self._adjustControlHeight)

            self.txtPrompt.setFocus()
            self.updateSort()
        else:
            if self._taskEmbed:
                self._taskEmbed.abort()

            self.resetSort(self.DISABLED_PARAMS)
            filelist = self.tab.filelist
            for file in filelist.getFiles():
                filelist.removeData(file, DataKeys.Embedding, False)

    @Slot()
    def _onDirectionChanged(self, ascending: bool):
        text = "∆" if ascending else "∇"
        self.btnAscending.setText(text)
        self.updateSort()


    def onFileChanged(self, currentFile: str):
        pass

    def onFileListChanged(self, currentFile: str):
        # Disable sort when FileList cleared the order
        if not self.tab.filelist.order:
            # Reset params to avoid double-load through resetSort() and GalleryGrid's onFileListChanged()
            self._paramsCurrent = self.DISABLED_PARAMS
            self._paramsRequested = self.DISABLED_PARAMS

            self.btnSort.setChecked(False)


    def resetSort(self, params: SortParams):
        if self._paramsCurrent != params:
            self._paramsCurrent = params
            self._paramsRequested = params

            self.tab.filelist.clearOrder()
            self.galleryGrid.reloadImages(folders=params.byFolder)

    @Slot()
    def updateSortByText(self):
        prompt = TextPrompt(self.txtPrompt.text().strip(), self.txtNegPrompt.text().strip())
        self.setRequestedParams(prompt)
        self._setTextPromptMuted(False)
        self.applySort()

    def updateSortByImage(self, files: list[str]):
        prompt = ImagePrompt.fromList(files)
        self.setRequestedParams(prompt)
        self._setTextPromptMuted(True)

        if self.btnSort.isChecked():
            self.applySort()
        else:
            self.btnSort.setChecked(True)

    @Slot()
    def updateSort(self):
        if self._paramsRequested.prompt:
            self.setRequestedParams(self._paramsRequested.prompt)
            self.applySort()
        else:
            # TODO: Remember last prompt (image prompt)?
            self.updateSortByText()

    def setRequestedParams(self, prompt: TextPrompt | ImagePrompt):
        preset = self.cboModelPreset.currentText().strip()
        config = Config.inferEmbeddingPresets.get(preset)

        if config is None:
            print("Sort failed: No embedding model configured")
            self._paramsRequested = SortParams(byFolder=self.chkByFolder.isChecked())
        else:
            self._paramsRequested = SortParams(
                config      = copy.deepcopy(config),
                prompt      = prompt,
                ascending   = self.btnAscending.isChecked(),
                byFolder    = self.chkByFolder.isChecked()
            )

    @Slot()
    def applySort(self):
        if self._taskEmbed or self._taskSort:
            return

        params = self._paramsRequested
        if not params.prompt:
            self.resetSort(SortParams(byFolder=params.byFolder))
            return

        filelist = self.tab.filelist
        filesNoEmbedding = list[str]()
        fileEmbeddings = list[tuple[int, str, np.ndarray]]()

        # Reload all image embeddings if config was changed
        if params.needsReload(self._paramsCurrent):
            filesNoEmbedding = filelist.getFiles().copy()
        else:
            for i, file in enumerate(filelist.getFiles()):
                embedding = filelist.getData(file, DataKeys.Embedding)
                if embedding is None:
                    filesNoEmbedding.append(file)
                # Stop populating fileEmbeddings after first miss
                elif not filesNoEmbedding:
                    fileEmbeddings.append((i, file, embedding))

        if filesNoEmbedding:
            self._taskEmbed = EmbedImagesTask(params.config, filesNoEmbedding)
            self._taskEmbed.signals.fileDone.connect(self._onFileEmbedDone, Qt.ConnectionType.QueuedConnection)
            self._taskEmbed.signals.finished.connect(self._onEmbeddingsDone, Qt.ConnectionType.QueuedConnection)

            self.btnSort.setText(f"{self.BUTTON_TEXT} (0%)")
            QThreadPool.globalInstance().start(self._taskEmbed)

        # No missing embeddings. All files contained.
        elif fileEmbeddings:
            if isinstance(params.prompt, ImagePrompt):
                params.prompt.setEmbeddings(filelist)

            assert len(fileEmbeddings) == filelist.getNumFiles()
            self._taskSort = UpdateSortTask(params, fileEmbeddings)
            self._taskSort.signals.done.connect(self._onSortDone, Qt.ConnectionType.QueuedConnection)
            self._taskSort.signals.fail.connect(self._onSortFail, Qt.ConnectionType.QueuedConnection)

            self.btnSort.setText(f"Sorting...")
            QThreadPool.globalInstance().start(self._taskSort)


    @Slot()
    def _onFileEmbedDone(self, file: str, embedding: object, currentFile: int, totalFiles: int):
        self.tab.filelist.setData(file, DataKeys.Embedding, embedding, False)

        progress = round((currentFile / totalFiles) * 100)
        self.btnSort.setText(f"{self.BUTTON_TEXT} ({progress}%)")

    @Slot()
    def _onEmbeddingsDone(self, config: dict, success: bool):
        self.btnSort.setText(self.BUTTON_TEXT)
        self._taskEmbed = None

        if success and self.btnSort.isChecked():
            self._paramsCurrent = SortParams(config=config)
            QTimer.singleShot(0, self.updateSort)


    @Slot()
    def _onSortDone(self, mapFilePos: list[int], mapPosFile: list[int], params: SortParams):
        self.btnSort.setText(self.BUTTON_TEXT)
        self._taskSort = None

        if self.btnSort.isChecked() and len(mapFilePos):
            if params == self._paramsRequested:
                self._paramsCurrent = params

                self.tab.filelist.setOrder(mapFilePos, mapPosFile, params.byFolder)
                self.galleryGrid.reloadImages()
            else:
                self.updateSort()

    @Slot()
    def _onSortFail(self):
        self.btnSort.setText(self.BUTTON_TEXT)
        self._taskSort = None



class EmbedImagesTask(QRunnable):
    CACHED = "CACHED"

    class Signals(QObject):
        fileDone = Signal(str, object, int, int)
        finished = Signal(dict, bool)

    def __init__(self, config: dict, files: list[str]):
        super().__init__()
        self.setAutoDelete(True)
        self.signals = self.Signals()

        self.config = copy.deepcopy(config)
        self.files  = files

        self.aborted = False
        self._mutex = QMutex()


    def isAborted(self) -> bool:
        with QMutexLocker(self._mutex):
            return self.aborted

    def abort(self):
        with QMutexLocker(self._mutex):
            self.aborted = True


    def loadFromCache(self, cache: EmbeddingCache) -> int:
        numFromCache = 0
        t = time.monotonic_ns()

        for i, file in enumerate(self.files):
            embedding = cache.load(file)
            if embedding is not None:
                numFromCache += 1
                self.files[i] = self.CACHED
                self.signals.fileDone.emit(file, embedding, 0, 1)

        if numFromCache > 0:
            t = (time.monotonic_ns() - t) / 1000000
            print(f"Loaded {numFromCache}/{len(self.files)} embeddings from cache in {t:.2f} ms")

        return numFromCache


    def createEmbeddings(self, cache: EmbeddingCache, numFromCache: int):
        from infer.inference import Inference
        from infer.inference_proc import InferenceProcess

        t = 0
        def prepareCb():
            nonlocal t
            t = time.monotonic_ns()

        def prepare(proc: InferenceProcess):
            proc.setupEmbedding(self.config)

        def check(file: str, proc: InferenceProcess):
            return None if file is self.CACHED else lambda: proc.embedImage(file)

        numFiles = len(self.files) - numFromCache
        numLoaded = 0

        with Inference().createSession() as session:
            session.prepare(prepare, prepareCb)

            for fileNr, (file, results, exception) in enumerate(session.queueFiles(self.files, check)):
                try:
                    if exception:
                        raise exception

                    if results:
                        data = results[0]["embedding"]
                        embedding = np.frombuffer(data, dtype=np.float32)
                        cache.store(file, embedding)
                        numLoaded += 1
                    else:
                        raise ValueError("Empty result")

                except Exception as ex:
                    print(f"Failed to load embedding: {ex} ({type(ex).__name__})")
                    embedding = EMBED_FAILED

                self.signals.fileDone.emit(file, embedding, fileNr, numFiles)

                if self.isAborted():
                    break

        t = (time.monotonic_ns() - t) / 1000000
        tPerFile = t / numFiles
        print(f"Created {numLoaded}/{numFiles} embeddings in {t:.2f} ms ({tPerFile:.2f} ms per file)")


    def run(self):
        sampleCfg: dict = self.config[Config.INFER_PRESET_SAMPLECFG_KEY]
        processing = sampleCfg.get(embed.CONFIG_KEY_PROCESSING)
        aggregate  = sampleCfg.get(embed.CONFIG_KEY_AGGREGATE)
        if processing and aggregate:
            print(f"Loading image embeddings with '{processing}' strategy (aggregate: {aggregate})")

        success = False
        try:
            with EmbeddingCache(self.config) as cache:
                numFromCache = self.loadFromCache(cache)
                if numFromCache < len(self.files):
                    self.createEmbeddings(cache, numFromCache)

            success = True
        finally:
            self.signals.finished.emit(self.config, success)



class UpdateSortTask(QRunnable):
    PROMPT_SEP = "|"

    class Signals(QObject):
        done = Signal(list, list, tuple)
        fail = Signal()

    def __init__(self, params: SortParams, fileEmbeddings: list[tuple[int, str, np.ndarray]]):
        super().__init__()
        self.setAutoDelete(True)

        self.signals = self.Signals()
        self.config = copy.deepcopy(params.config) # Modified
        self.params = params
        self.fileEmbeddings = fileEmbeddings


    def loadPromptTemplates(self):
        sampleCfg: dict = self.config[Config.INFER_PRESET_SAMPLECFG_KEY]
        promptTemplate = sampleCfg.pop(embed.CONFIG_KEY_PROMPT_TEMPLATE_FILE)

        path = os.path.join(Config.pathEmbeddingTemplates, f"{promptTemplate}.txt")
        path = os.path.abspath(path)
        with open(path, "r") as file:
            lines = file.readlines()

        sampleCfg[embed.CONFIG_KEY_PROMPT_TEMPLATES] = [
            line for l in lines
            if (line := l.strip()) and (not line.startswith("#")) and ("{}" in line)
        ]

    def buildTextPrompt(self, prompt: TextPrompt) -> tuple[np.ndarray, np.ndarray | None]:
        from infer.inference import Inference, InferenceProcess

        self.loadPromptTemplates()
        def prepare(proc: InferenceProcess):
            proc.setupEmbedding(self.config)

        def embedTextPrompt(proc: InferenceProcess, text: str) -> np.ndarray:
            prompts = [prompt for p in text.split(self.PROMPT_SEP) if (prompt := p.strip())]
            embeddings = []
            for prompt in prompts:
                data = proc.embedText(prompt)
                embeddings.append(np.frombuffer(data, dtype=np.float32))

            #combined = np.max(embeddings, axis=0)
            combined = np.sum(embeddings, axis=0)
            combined /= np.linalg.vector_norm(combined, axis=-1)
            return combined

        with Inference().createSession(1) as session:
            session.prepare(prepare)
            proc = session.getFreeProc().proc

            posPromptEmbedding = embedTextPrompt(proc, prompt.pos)
            negPromptEmbedding = embedTextPrompt(proc, prompt.neg) if prompt.neg else None
            return posPromptEmbedding, negPromptEmbedding


    def buildImagePrompt(self, prompt: ImagePrompt) -> tuple[np.ndarray, None]:
        embeddings = list(prompt.values())
        #combined = np.max(embeddings, axis=0)
        combined = np.sum(embeddings, axis=0)
        combined /= np.linalg.vector_norm(combined, axis=-1)
        return combined, None


    def run(self):
        try:
            if isinstance(self.params.prompt, TextPrompt):
                posPromptEmbedding, negPromptEmbedding = self.buildTextPrompt(self.params.prompt)
            else:
                posPromptEmbedding, negPromptEmbedding = self.buildImagePrompt(self.params.prompt)

            calcScore = OffsetSimilarityScore(posPromptEmbedding, negPromptEmbedding)
            direction = 1.0 if self.params.ascending else -1.0
            fileOrder = list[tuple[int, str, float]]()

            for idx, file, imgEmbedding in self.fileEmbeddings:
                if imgEmbedding is EMBED_FAILED:
                    order = -direction * 1000000
                else:
                    order = float(calcScore(imgEmbedding)) * direction
                fileOrder.append((idx, file, order))

            key = self.sortKeyByFolder if self.params.byFolder else self.sortKey
            fileOrder.sort(key=key)

            # Create two-way index mapping
            mapFilePos = [0] * len(fileOrder) # file index -> pos
            mapPosFile = [0] * len(fileOrder) # pos        -> file index
            for i, (idx, file, _) in enumerate(fileOrder):
                mapFilePos[idx] = i
                mapPosFile[i] = idx

            self.signals.done.emit(mapFilePos, mapPosFile, self.params)

        except:
            traceback.print_exc()
            self.signals.fail.emit()


    @staticmethod
    @naturalSort
    def sortKeyByFolder(fileScore: tuple[int, str, float]):
        return os.path.dirname(fileScore[1]), fileScore[2]

    @staticmethod
    def sortKey(fileScore: tuple[int, str, float]):
        return fileScore[2]



class SimilarityScore(ABC):
    def __init__(self, posEmbedding: np.ndarray, negEmbedding: np.ndarray | None):
        self.pos = posEmbedding
        self.neg = negEmbedding

        self._func = self.scorePos if negEmbedding is None else self.scorePosNeg

    def __call__(self, imgEmbedding: np.ndarray) -> float:
        return self._func(imgEmbedding)

    def scorePos(self, imgEmbedding) -> float:
        return imgEmbedding @ self.pos

    @abstractmethod
    def scorePosNeg(self, imgEmbedding) -> float:
        ...


class CosineSimilarityScore(SimilarityScore):
    def __init__(self, posEmbedding, negEmbedding):
        super().__init__(posEmbedding, negEmbedding)
        if self.neg is not None:
            self.pos = self.pos - self.neg
            self.pos /= np.linalg.vector_norm(self.pos)

    scorePosNeg = SimilarityScore.scorePos


class OffsetSimilarityScore(SimilarityScore):
    def __init__(self, posEmbedding, negEmbedding):
        super().__init__(posEmbedding, negEmbedding)
        if self.neg is not None:
            self.pos = self.pos - self.neg

    def scorePosNeg(self, imgEmbedding) -> float:
        return (imgEmbedding - self.neg) @ self.pos


class DifferenceScore(SimilarityScore):
    def __init__(self, posEmbedding, negEmbedding):
        super().__init__(posEmbedding, negEmbedding)

    def scorePosNeg(self, imgEmbedding) -> float:
        posScore = imgEmbedding @ self.pos
        negScore = imgEmbedding @ self.neg
        return posScore - negScore



class EmbeddingCache:
    def __init__(self, config: dict):
        self.cachePath = self._getCachePath(config)

        self.embeddings: dict[str, dict[str, np.ndarray]] = defaultdict(dict)
        self.changedFolders: set[str] = set()

        import hashlib
        self.hashFunc = hashlib.md5

    @staticmethod
    def _getCachePath(config: dict) -> str:
        modelPath = os.path.normcase(os.path.realpath(config["model_path"]))
        if not os.path.isdir(modelPath):
            modelPath = os.path.dirname(modelPath)
        cacheDir = os.path.basename(modelPath)

        sampleCfg: dict = config[Config.INFER_PRESET_SAMPLECFG_KEY]
        processing = sampleCfg.get(embed.CONFIG_KEY_PROCESSING)
        aggregate  = sampleCfg.get(embed.CONFIG_KEY_AGGREGATE)

        if processing and aggregate:
            cacheDir = "_".join((
                cacheDir,
                embed.PROCESSING[processing].cacheSuffix,
                embed.AGGREGATE[aggregate].cacheSuffix
            ))

        return os.path.join(Config.pathEmbeddingCache, cacheDir)


    def __enter__(self):
        return self

    def __exit__(self, excType, excVal, excTraceback):
        os.makedirs(self.cachePath, exist_ok=True)
        for folder in self.changedFolders:
            folderDict = self.embeddings[folder]
            cacheFile = self.getCacheFile(folder)
            cacheFileNoPrefix = cacheFile.removeprefix(f".{os.sep}")
            print(f"Update embedding cache: {cacheFileNoPrefix} ({len(folderDict)} entries)")
            np.save(cacheFile, folderDict)
        return False


    def getCacheFile(self, folder: str) -> str:
        return os.path.join(self.cachePath, f"{folder}.npy")

    def getKeys(self, path: str) -> tuple[str, str]:
        folder, file = os.path.split(os.path.normcase(os.path.realpath(path)))
        hash = self.hashFunc(folder.encode("utf-8"), usedforsecurity=False)
        folderKey = hash.hexdigest()

        # Use full path for fileKey, so when folder hashes collide, same filenames aren't mapped to the same hash.
        hash.update(b"\x00")
        hash.update(file.encode("utf-8"))
        fileKey = hash.hexdigest()
        return folderKey, fileKey


    def load(self, file: str) -> np.ndarray | None:
        folderKey, fileKey = self.getKeys(file)
        folderDict = self.embeddings.get(folderKey)
        if folderDict is None:
            cacheFile = self.getCacheFile(folderKey)
            if not os.path.exists(cacheFile):
                return None

            folderDict = np.load(cacheFile, allow_pickle=True).item()
            self.embeddings[folderKey] = folderDict

        return folderDict.get(fileKey)

    def store(self, file: str, embedding: np.ndarray):
        folderKey, fileKey = self.getKeys(file)
        folderDict = self.embeddings[folderKey]
        if fileKey not in folderDict:
            folderDict[fileKey] = embedding
            self.changedFolders.add(folderKey)
