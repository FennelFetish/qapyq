import json


class CaptionPreset:
    version = "1.0"

    def __init__(self):
        self.prefix = ""
        self.suffix = ""
        self.separator = ", "

        self.autoApplyRules : bool = False
        self.removeDuplicates : bool = True

        self.groups = []
        self.banned = []

    def addGroup(self, name, mutuallyExclusive, captions):
        group = CaptionPresetGroup()
        group.name = name
        group.mutuallyExclusive = mutuallyExclusive
        group.captions.extend(captions)
        self.groups.append(group)

    def toDict(self):
        groupData = [g.toDict() for g in self.groups]
        return {
            "version": CaptionPreset.version,
            "prefix": self.prefix,
            "suffix": self.suffix,
            "separator": self.separator,
            "autoApplyRules": self.autoApplyRules,
            "removeDuplicates": self.removeDuplicates,
            "groups": groupData,
            "banned": self.banned
        }

    def saveTo(self, path):
        data = self.toDict()
        with open(path, 'w') as file:
            json.dump(data, file, indent=4)

    def loadFrom(self, path):
        with open(path, 'r') as file:
            data = json.load(file)
        
        self.prefix             = data.get("prefix", "")
        self.suffix             = data.get("suffix", "")
        self.separator          = data.get("separator", ", ")
        self.autoApplyRules     = data.get("autoApplyRules", False)
        self.removeDuplicates   = data.get("removeDuplicates", True)
        self.banned             = data.get("banned", [])

        if "groups" in data:
            for group in data["groups"]:
                self.addGroup(group["name"], group["mutuallyExclusive"], group["captions"])



class CaptionPresetGroup:
    def __init__(self):
        self.name = "Group"
        self.mutuallyExclusive : bool = False
        self.captions = []
    
    def toDict(self):
        captionData = [c for c in self.captions]
        return {
            "name": self.name,
            "mutuallyExclusive": self.mutuallyExclusive,
            "captions": captionData
        }
