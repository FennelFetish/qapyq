import json, os
from typing import Dict
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, Signal, QObject, QSignalBlocker
import lib.qtlib as qtlib
from config import Config


class Keys:
    VERSION  = "version"
    CAPTIONS = "captions"
    PROMPTS  = "prompts"
    TAGS     = "tags"


class CaptionFile:
    VERSION = "1.0"


    def __init__(self, file):
        '''
        Don't pass 'file' with extension already removed.
        If the filename has multiple dots, another part of the filename will be removed to append ".json".
        '''

        self.captions: Dict[str, str] = dict()
        self.prompts: Dict[str, str] = dict()
        self.tags: Dict[str, str] = dict()

        path, ext = os.path.splitext(file)
        self.jsonPath = f"{path}.json"


    def addCaption(self, name: str, caption: str):
        self.captions[name] = caption

    def getCaption(self, name: str):
        return self.captions.get(name, None)


    def addPrompt(self, name: str, prompt: str):
        self.prompts[name] = prompt

    def getPrompt(self, name: str):
        return self.prompts.get(name, None)


    def addTags(self, name: str, tags: str):
        self.tags[name] = tags

    def getTags(self, name: str):
        return self.tags.get(name, None)


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

        captions = data.get(Keys.CAPTIONS, {})
        captions.update(self.captions)
        if captions := self._deleteEmpty(captions):
            data[Keys.CAPTIONS] = captions

        prompts = data.get(Keys.PROMPTS, {})
        prompts.update(self.prompts)
        if prompts := self._deleteEmpty(prompts):
            data[Keys.PROMPTS] = prompts

        tags = data.get(Keys.TAGS, {})
        tags.update(self.tags)
        if tags := self._deleteEmpty(tags):
            data[Keys.TAGS] = tags

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

        with open(self.jsonPath, 'w') as file:
            json.dump(data, file, indent=4)


    @staticmethod
    def _deleteEmpty(data: dict) -> dict:
        return {k: v for k, v in data.items() if v}



class FileTypeSelector(QtWidgets.QHBoxLayout):
    TYPE_TXT = "txt"
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
        self.cboKey.setMinimumWidth(140)
        self.cboKey.currentTextChanged.connect(self._onEdited)
        qtlib.setMonospace(self.cboKey)
        self.addWidget(self.cboKey)

        self._onTypeChanged(self.cboType.currentIndex())

    @Slot()
    def _onTypeChanged(self, index):
        keyType = self.cboType.itemData(index)
        self.cboKey.setKeyType(keyType)

        self.fileTypeUpdated.emit()

    @Slot()
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

        captionFile = CaptionFile(imgPath)
        if not captionFile.loadFromJson():
            return None

        if self.type == FileTypeSelector.TYPE_CAPTIONS:
            return captionFile.getCaption(self.name)
        else:
            return captionFile.getTags(self.name)

    @classmethod
    def loadCaptionTxt(cls, imgPath: str) -> str | None:
        path = os.path.splitext(imgPath)[0] + cls.CAPTION_FILE_EXT
        if os.path.exists(path):
            with open(path, 'r') as file:
                return file.read()
        return None


    def saveCaption(self, imgPath: str, text: str) -> bool:
        if not imgPath:
            print(f"Failed to save caption to file: Path is empty")
            return False

        if self.type == FileTypeSelector.TYPE_TXT:
            self.saveCaptionTxt(imgPath, text)
            return True

        captionFile = CaptionFile(imgPath)
        type = self.type
        name = self.name

        if type == FileTypeSelector.TYPE_CAPTIONS:
            captionFile.addCaption(name, text)
        else:
            captionFile.addTags(name, text)

        if captionFile.updateToJson():
            print(f"Saved caption to file: {captionFile.jsonPath} [{type}.{name}]")
            return True
        else:
            print(f"Failed to save caption to file: {captionFile.jsonPath} [{type}.{name}]")
            return False

    def saveCaptionTxt(self, imgPath: str, text: str) -> None:
        path = os.path.splitext(imgPath)[0] + self.CAPTION_FILE_EXT
        with open(path, 'w') as file:
            file.write(text)
        print("Saved caption to file:", path)


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

    @Slot()
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
