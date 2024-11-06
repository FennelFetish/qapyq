import json
import os
from typing import Dict


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
