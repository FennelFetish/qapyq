import json
from enum import Enum


class MutualExclusivity(Enum):
    Disabled  = "disabled"
    KeepLast  = "last"
    KeepFirst = "first"
    Priority  = "priority"


class CaptionPreset:
    version = "1.0"

    def __init__(self):
        self.prefix = ""
        self.suffix = ""
        self.separator = ", "
        self.prefixSeparator = True
        self.suffixSeparator = True

        self.autoApplyRules : bool = False
        self.removeDuplicates : bool = True
        self.sortCaptions : bool = True

        self.groups: list[CaptionPresetGroup] = []
        self.searchReplace: list[tuple[str, str]] = []
        self.banned: list[str] = []

    def addGroup(self, name: str, color: str, exclusivity: MutualExclusivity, combineTags: bool, captions: list[str]):
        group = CaptionPresetGroup()
        group.name = name
        group.color = color
        group.exclusivity = exclusivity
        group.combineTags = combineTags
        group.captions.extend(captions)
        self.groups.append(group)

    def toDict(self):
        groupData = [g.toDict() for g in self.groups]
        return {
            "version": CaptionPreset.version,
            "prefix": self.prefix,
            "suffix": self.suffix,
            "separator": self.separator,
            "prefix_separator": self.prefixSeparator,
            "suffix_separator": self.suffixSeparator,
            "auto_apply_rules": self.autoApplyRules,
            "remove_duplicates": self.removeDuplicates,
            "sort_captions": self.sortCaptions,
            "groups": groupData,
            "search_replace": self.searchReplace,
            "banned": self.banned
        }

    def saveTo(self, path: str):
        data = self.toDict()
        with open(path, 'w') as file:
            json.dump(data, file, indent=4)

    def loadFrom(self, path: str):
        with open(path, 'r') as file:
            data: dict = json.load(file)

        self.prefix             = data.get("prefix", "")
        self.suffix             = data.get("suffix", "")
        self.separator          = data.get("separator", ", ")
        self.prefixSeparator    = data.get("prefix_separator", True)
        self.suffixSeparator    = data.get("suffix_separator", True)
        self.autoApplyRules     = data.get("auto_apply_rules", False)
        self.removeDuplicates   = data.get("remove_duplicates", True)
        self.sortCaptions       = data.get("sort_captions", True)
        self.searchReplace      = data.get("search_replace", [])
        self.banned             = data.get("banned", [])

        if "groups" in data:
            for group in data["groups"]:
                self.addGroup(
                    group.get("name", "Group"),
                    group.get("color", "#000"),
                    self.loadExclusivity(group),
                    group.get("combine_tags", False),
                    group.get("captions", [])
                )

    @staticmethod
    def loadExclusivity(group: dict) -> MutualExclusivity:
        exclusivity: str = group.get("exclusivity", MutualExclusivity.Disabled.value)

        # Try loading mutual exclusivity in old format
        if group.get("mutually_exclusive", False):
            exclusivity = MutualExclusivity.KeepLast.value

        try:
            return MutualExclusivity(exclusivity)
        except ValueError as ex:
            groupName = group.get("name", "Group")
            print(f"Error while loading captioning rules for group '{groupName}': {ex}")
            return MutualExclusivity.Disabled



class CaptionPresetGroup:
    def __init__(self):
        self.name: str = "Group"
        self.color: str = "#000"
        self.exclusivity: MutualExclusivity = MutualExclusivity.Disabled
        self.combineTags: bool = False
        self.captions: list[str] = []

    def toDict(self):
        return {
            "name": self.name,
            "color": self.color,
            "exclusivity": self.exclusivity.value,
            "combine_tags": self.combineTags,
            "captions": list(self.captions)
        }
