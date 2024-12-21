import json, os
from typing import Dict
from PySide6 import QtWidgets
from PySide6.QtCore import Slot, Signal
import lib.qtlib as qtlib


class Keys:
    VERSION  = "version"
    CAPTIONS = "captions"
    PROMPTS  = "prompts"
    TAGS     = "tags"


class CaptionFile:
    VERSION = "1.0"


    def __init__(self, file):
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
        if captions:
            data[Keys.CAPTIONS] = captions

        prompts = data.get(Keys.PROMPTS, {})
        prompts.update(self.prompts)
        if prompts:
            data[Keys.PROMPTS] = prompts

        tags = data.get(Keys.TAGS, {})
        tags.update(self.tags)
        if tags:
            data[Keys.TAGS] = tags
        
        with open(self.jsonPath, 'w') as file:
            json.dump(data, file, indent=4)
        
        return True


    def saveToJson(self) -> None:
        data = dict()
        data[Keys.VERSION] = CaptionFile.VERSION

        if self.captions:
            data[Keys.CAPTIONS] = self.captions

        if self.prompts:
            data[Keys.PROMPTS] = self.prompts
        
        if self.tags:
            data[Keys.TAGS] = self.tags

        with open(self.jsonPath, 'w') as file:
            json.dump(data, file, indent=4)



class FileTypeSelector(QtWidgets.QHBoxLayout):
    TYPE_TXT = "txt"
    TYPE_TAGS = "tags"
    TYPE_CAPTIONS = "captions"

    CAPTION_FILE_EXT = ".txt"

    fileTypeUpdated = Signal()


    def __init__(self):
        super().__init__()

        self.cboType = QtWidgets.QComboBox()
        self.cboType.addItem(".txt File", self.TYPE_TXT)
        self.cboType.addItem(".json Tags:", self.TYPE_TAGS)
        self.cboType.addItem(".json Caption:", self.TYPE_CAPTIONS)
        self.cboType.currentIndexChanged.connect(self._onTypeChanged)
        self.addWidget(self.cboType)

        self.txtName = QtWidgets.QLineEdit("tags")
        self.txtName.editingFinished.connect(self._onEdited)
        qtlib.setMonospace(self.txtName)
        self.addWidget(self.txtName)

        self._onTypeChanged(self.cboType.currentIndex())
    
    @Slot()
    def _onTypeChanged(self, index):
        nameEnabled = self.cboType.itemData(index) != self.TYPE_TXT
        self.txtName.setEnabled(nameEnabled)

        self.fileTypeUpdated.emit()

    @Slot()
    def _onEdited(self):
        if not self.name:
            if self.type == self.TYPE_TAGS:
                self.txtName.setText("tags")
            else:
                self.txtName.setText("caption")
        
        self.fileTypeUpdated.emit()


    @property
    def type(self) -> str:
        return self.cboType.currentData()

    @property
    def name(self) -> str:
        return self.txtName.text()
    

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
    
    def loadCaptionTxt(self, imgPath: str) -> str | None:
        path = os.path.splitext(imgPath)[0] + self.CAPTION_FILE_EXT
        if os.path.exists(path):
            with open(path, 'r') as file:
                return file.read()
        return None


    def saveCaption(self, imgPath: str, text: str) -> bool:
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
