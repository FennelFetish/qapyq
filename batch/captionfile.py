import json
import os


class CaptionFile:
    version = "1.0"


    def __init__(self, imgPath):
        self.captions = dict()
        self.tags = ""

        path, ext = os.path.splitext(imgPath)
        self.jsonPath = f"{path}.json"


    def addCaption(self, name, caption):
        self.captions[name] = caption

    
    def loadFromJson(self):
        with open(self.jsonPath, 'r') as file:
            data = json.load(file)

        self.captions = data.get("captions", {})
        self.tags     = data.get("tags", "")


    def saveToJson(self):
        data = dict()
        data["version"]  = CaptionFile.version
        data["captions"] = self.captions
        data["tags"]     = self.tags

        with open(self.jsonPath, 'w') as file:
            json.dump(data, file, indent=4)

    
    def updateToJson(self):
        if os.path.exists(self.jsonPath):
            with open(self.jsonPath, 'r') as file:
                data = json.load(file)
        else:
            data = dict()
        
        captions = data.get("captions", {})
        captions.update(self.captions)
        data["version"]  = CaptionFile.version
        data["captions"] = captions

        if self.tags:
            data["tags"] = self.tags
        
        with open(self.jsonPath, 'w') as file:
            json.dump(data, file, indent=4)
