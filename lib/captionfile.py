import json, os
from typing import Callable
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, Signal, QObject, QSignalBlocker
import lib.qtlib as qtlib
from config import Config

# Imported in FileTypeSelector.saveCaption()
# from .cascade import CascadeUpdate


class Keys:
    VERSION  = "version"
    CAPTIONS = "captions"
    PROMPTS  = "prompts"
    TAGS     = "tags"
    METRICS  = "metrics"
    CASCADE  = "cascade"



class CaptionFile:
    VERSION = "1.0"


    def __init__(self, file: str):
        '''
        Don't pass 'file' with extension already removed.
        If the filename has multiple dots, another part of the filename will be removed to append ".json".
        '''

        self.captions:  dict[str, str]      = dict()
        self.prompts:   dict[str, str]      = dict()
        self.tags:      dict[str, str]      = dict()
        self.metrics:   dict[str, float]    = dict()
        self.cascade:   dict[str, str]      = dict()

        self.jsonPath = os.path.splitext(file)[0] + ".json"


    def addCaption(self, name: str, caption: str):
        self.captions[name] = caption

    def getCaption(self, name: str) -> str | None:
        return self.captions.get(name)


    def addPrompt(self, name: str, prompt: str):
        self.prompts[name] = prompt

    def getPrompt(self, name: str) -> str | None:
        return self.prompts.get(name)


    def addTags(self, name: str, tags: str):
        self.tags[name] = tags

    def getTags(self, name: str) -> str | None:
        return self.tags.get(name)


    def addMetric(self, name: str, value: float):
        self.metrics[name] = value

    def getMetric(self, name: str) -> float | None:
        return self.metrics.get(name)


    def addCascade(self, name: str, template: str):
        self.cascade[name] = template

    def getCascade(self, name: str) -> str | None:
        return self.cascade.get(name)


    def jsonExists(self) -> bool:
        return os.path.exists(self.jsonPath)


    def loadFromJson(self) -> bool:
        if self.jsonExists():
            with open(self.jsonPath, 'r') as file:
                data = json.load(file)
            if Keys.VERSION not in data:
                return False
        else:
            return False

        self.captions = data.get(Keys.CAPTIONS, {})
        self.prompts  = data.get(Keys.PROMPTS, {})
        self.tags     = data.get(Keys.TAGS, {})
        self.metrics  = data.get(Keys.METRICS, {})
        self.cascade  = data.get(Keys.CASCADE, {})
        return True


    def updateToJson(self) -> bool:
        if self.jsonExists():
            with open(self.jsonPath, 'r') as file:
                data = json.load(file)
            if Keys.VERSION not in data:
                return False
        else:
            data = dict()

        data[Keys.VERSION] = CaptionFile.VERSION

        self._updateDict(data, self.captions, Keys.CAPTIONS)
        self._updateDict(data, self.prompts, Keys.PROMPTS)
        self._updateDict(data, self.tags, Keys.TAGS)
        self._updateDict(data, self.metrics, Keys.METRICS, self._predNotNone)
        self._updateDict(data, self.cascade, Keys.CASCADE)

        with open(self.jsonPath, 'w') as file:
            json.dump(data, file, indent=4)

        return True


    def saveToJson(self) -> None:
        data = dict()
        data[Keys.VERSION] = CaptionFile.VERSION

        if captions := self._deleteEmpty(self.captions):
            data[Keys.CAPTIONS] = captions

        if prompts := self._deleteEmpty(self.prompts):
            data[Keys.PROMPTS] = prompts

        if tags := self._deleteEmpty(self.tags):
            data[Keys.TAGS] = tags

        if metrics := self._deleteEmpty(self.metrics, self._predNotNone):
            data[Keys.METRICS] = metrics

        if cascade := self._deleteEmpty(self.cascade):
            data[Keys.CASCADE] = cascade

        with open(self.jsonPath, 'w') as file:
            json.dump(data, file, indent=4)


    @classmethod
    def _updateDict(cls, data: dict, addDict: dict, key: str, predKeep: Callable = bool):
        subDict: dict = data.get(key, {})
        subDict.update(addDict)
        if subDict := cls._deleteEmpty(subDict, predKeep):
            data[key] = subDict

    @staticmethod
    def _deleteEmpty(data: dict, predKeep: Callable = bool) -> dict:
        return {k: v for k, v in data.items() if predKeep(v)}

    @staticmethod
    def _predNotNone(val) -> bool:
        return (val is not None)



class FileTypeSelector(QtWidgets.QHBoxLayout):
    TYPE_TXT = "text"
    TYPE_TAGS = "tags"
    TYPE_CAPTIONS = "captions"

    CAPTION_FILE_EXT = ".txt"

    fileTypeUpdated = Signal()


    def __init__(self, showTxtType=True, defaultValue=""):
        super().__init__()

        self.cboType = QtWidgets.QComboBox()
        if showTxtType:
            self.cboType.addItem(".txt File", self.TYPE_TXT)
        self.cboType.addItem(".json Tags:", self.TYPE_TAGS)
        self.cboType.addItem(".json Caption:", self.TYPE_CAPTIONS)
        self.cboType.currentIndexChanged.connect(self._onTypeChanged)
        self.addWidget(self.cboType)

        self.cboKey = CaptionKeyComboBox(self.cboType.currentData(), defaultValue)
        self.cboKey.setMinimumWidth(200)
        self.cboKey.currentTextChanged.connect(self._onEdited)
        qtlib.setMonospace(self.cboKey)
        self.addWidget(self.cboKey, stretch=1)

        self._onTypeChanged(self.cboType.currentIndex())

    @Slot(int)
    def _onTypeChanged(self, index: int):
        keyType = self.cboType.itemData(index)
        self.cboKey.setKeyType(keyType)

        self.fileTypeUpdated.emit()

    @Slot(str)
    def _onEdited(self, text: str):
        self.fileTypeUpdated.emit()


    @property
    def type(self) -> str:
        return self.cboType.currentData()

    @type.setter
    def type(self, type: str):
        index = self.cboType.findData(type)
        index = max(index, 0)
        self.cboType.setCurrentIndex(index)

    def setFixedType(self, type: str):
        self.type = type
        self.cboType.hide()


    @property
    def name(self) -> str:
        return self.cboKey.currentText()

    @name.setter
    def name(self, name: str) -> None:
        self.cboKey.setEditText(name)


    def setTextFieldFixedWidth(self, width: int):
        self.cboKey.setFixedWidth(width)

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self.cboType.setEnabled(enabled)
        self.cboKey.setEnabled(enabled)


    def loadCaption(self, imgPath: str) -> str | None:
        if self.type == self.TYPE_TXT:
            return self.loadCaptionTxt(imgPath)
        else:
            return self.loadCaptionJson(self.type, self.name, imgPath)

    @staticmethod
    def loadCaptionTxt(imgPath: str) -> str | None:
        path = os.path.splitext(imgPath)[0] + FileTypeSelector.CAPTION_FILE_EXT
        if os.path.exists(path):
            with open(path, 'r') as file:
                return file.read()
        return None

    @staticmethod
    def loadCaptionJson(keyType: str, key: str, imgPath: str) -> str | None:
        captionFile = CaptionFile(imgPath)
        if not captionFile.loadFromJson():
            return None

        if keyType == FileTypeSelector.TYPE_CAPTIONS:
            return captionFile.getCaption(key)
        else:
            return captionFile.getTags(key)

    def createLoadFunc(self) -> Callable[[str], str | None]:
        if self.type == self.TYPE_TXT:
            return self.loadCaptionTxt
        return JsonCaptionLoadFunctor(self.type, self.name)


    def saveCaption(self, imgPath: str, text: str, cascade: bool = False) -> bool:
        if not imgPath:
            print(f"Failed to save caption to file: Path is empty")
            return False

        if self.type == FileTypeSelector.TYPE_TXT:
            # No cascading updates
            self.saveCaptionTxt(imgPath, text)
            return True

        keyType = self.type
        keyName = self.name

        captionFile = CaptionFile(imgPath)
        if captionFile.jsonExists() and not captionFile.loadFromJson():
            print(f"Failed to save caption to file: {captionFile.jsonPath} [{keyType}.{keyName}] (couldn't load file for updating)")
            return False

        if keyType == FileTypeSelector.TYPE_CAPTIONS:
            captionFile.addCaption(keyName, text)
        else:
            captionFile.addTags(keyName, text)

        if cascade:
            from .cascade import CascadeUpdate
            CascadeUpdate().saveCascade(imgPath, captionFile, keyType, keyName)

        captionFile.saveToJson()
        print(f"Saved caption to file: {captionFile.jsonPath} [{keyType}.{keyName}]")
        return True

    @classmethod
    def saveCaptionTxt(cls, imgPath: str, text: str) -> None:
        path = os.path.splitext(imgPath)[0] + cls.CAPTION_FILE_EXT
        with open(path, 'w') as file:
            file.write(text)
        print("Saved caption to file:", path)



# Pickleable
class JsonCaptionLoadFunctor:
    def __init__(self, keyType: str, key: str):
        self.key = key

        if keyType == FileTypeSelector.TYPE_CAPTIONS:
            self.getCaptionFunc = CaptionFile.getCaption
        else:
            self.getCaptionFunc = CaptionFile.getTags

    def __call__(self, imgPath: str) -> str | None:
        captionFile = CaptionFile(imgPath)
        if captionFile.loadFromJson():
            return self.getCaptionFunc(captionFile, self.key)
        return None



class CaptionKeyComboBox(qtlib.MenuComboBox):
    def __init__(self, initialType: str, defaultValue=""):
        super().__init__("Keys")
        self.setEditable(True)

        self.currentType = initialType
        self.selectedKeys = {
            FileTypeSelector.TYPE_TXT: "",
            FileTypeSelector.TYPE_TAGS: defaultValue or Config.keysTagsDefault,
            FileTypeSelector.TYPE_CAPTIONS: defaultValue or Config.keysCaptionDefault
        }
        self.setKeyType(initialType)

        self.currentTextChanged.connect(self._onTextChanged)
        KeySettingsWindow.signals.keysUpdated.connect(self.reloadKeys)

    @Slot()
    def reloadKeys(self):
        match self.currentType:
            case FileTypeSelector.TYPE_TXT:      keys = []
            case FileTypeSelector.TYPE_TAGS:     keys = Config.keysTags
            case FileTypeSelector.TYPE_CAPTIONS: keys = Config.keysCaption
            case _:
                raise ValueError("Invalid key type")

        with QSignalBlocker(self):
            currentText = self.currentText()
            self.clear()
            for key in keys:
                self.addItem(key)

            self.addSeparator()
            actSetup = self.addMenuAction("Setup Keys...")
            actSetup.triggered.connect(self._openKeySetting)

            self.setEditText(currentText)

    @Slot()
    def _openKeySetting(self):
        win = KeySettingsWindow(self)
        if win.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.reloadKeys()

    def setKeyType(self, keyType: str):
        self.currentType = keyType
        self.reloadKeys()
        self.setEditText(self.selectedKeys[keyType])
        self.setEnabled(keyType != FileTypeSelector.TYPE_TXT)

    @Slot(str)
    def _onTextChanged(self, text: str):
        self.selectedKeys[self.currentType] = text



class KeySettingsSignals(QObject):
    keysUpdated = Signal()


class KeySettingsWindow(QtWidgets.QDialog):
    signals = KeySettingsSignals()

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self._build()

        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowTitle("Setup Favorite .json Keys")
        self.resize(600, 400)

    def _build(self):
        groupTags, self.txtTagKeys, self.txtTagDefault = self._buildKeys("Tags", Config.keysTags, Config.keysTagsDefault)
        groupCaptions, self.txtCaptionKeys, self.txtCaptionDefault = self._buildKeys("Captions", Config.keysCaption, Config.keysCaptionDefault)

        layout = QtWidgets.QGridLayout(self)

        row = 0
        layout.setRowStretch(row, 1)
        layout.addWidget(groupTags, row, 0)
        layout.addWidget(groupCaptions, row, 1)

        row += 1
        btnCancel = QtWidgets.QPushButton("Cancel")
        btnCancel.clicked.connect(self.reject)
        layout.addWidget(btnCancel, row, 0)

        btnApply = QtWidgets.QPushButton("Apply")
        btnApply.clicked.connect(self._saveKeys)
        btnApply.clicked.connect(self.accept)
        layout.addWidget(btnApply, row, 1)

        self.setLayout(layout)

    def _buildKeys(self, title: str, keys: list[str], default: str):
        layout = QtWidgets.QGridLayout()

        txtKeys = QtWidgets.QPlainTextEdit()
        txtKeys.setPlainText("\n".join(keys) + "\n")
        qtlib.setMonospace(txtKeys)
        qtlib.setShowWhitespace(txtKeys)
        layout.addWidget(txtKeys, 0, 0, 1, 2)

        layout.addWidget(QtWidgets.QLabel("Default:"), 1, 0)

        txtDefault = QtWidgets.QLineEdit(default)
        qtlib.setMonospace(txtDefault)
        layout.addWidget(txtDefault, 1, 1)

        group = QtWidgets.QGroupBox(f"{title} (one key per line)")
        group.setLayout(layout)
        return group, txtKeys, txtDefault

    @Slot()
    def _saveKeys(self):
        defaultTag = self.txtTagDefault.text().strip()
        Config.keysTagsDefault = defaultTag or "tags"
        Config.keysTags = self._makeKeyList(self.txtTagKeys.toPlainText(), defaultTag, "tags")

        defaultCaption = self.txtCaptionDefault.text().strip()
        Config.keysCaptionDefault = defaultCaption or "caption"
        Config.keysCaption = self._makeKeyList(self.txtCaptionKeys.toPlainText(), defaultCaption, "caption")

        self.signals.keysUpdated.emit()

    def _makeKeyList(self, text: str, default: str, defaultIfEmpty: str) -> list[str]:
        lines = [line for l in text.splitlines() if (line := l.strip())]
        if lines:
            return lines
        if default:
            return [default]
        return [defaultIfEmpty]
