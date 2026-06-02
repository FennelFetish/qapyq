import os, enum
from typing import Iterator
from .template_parser import TemplateVariableParser
from .captionfile import CaptionFile, FileTypeSelector


CASCADE_FOLDER_FILE = "qapyq_cascade.json"


class DfsState(enum.IntEnum):
    Unvisited = 0
    Visiting  = 1
    Done      = 2


class CascadeNode:
    __slots__ = ('key', 'outKeys', 'state', 'template')

    def __init__(self, key: str):
        self.key: str = key
        self.outKeys: set[str] = set()
        self.state = DfsState.Unvisited
        self.template: str | None = None


class CycleError(ValueError):
    def __init__(self, path: list[CascadeNode]):
        self.path = path
        msg = " → ".join(node.key for node in path)
        super().__init__("Cycle in cascading updates: " + msg)



class CascadeGraph:
    def __init__(self, templates: dict[str, str]):
        self.nodes = self._buildGraph(templates)

    @classmethod
    def _buildGraph(cls, templates: dict[str, str]) -> dict[str, CascadeNode]:
        # Parse all templates with dummy caption file to list missing variables
        parser = TemplateVariableParser()
        parser.setup("/dummypath", CaptionFile(""))

        nodes = dict[str, CascadeNode]()
        for key, template in templates.items():
            if not cls.checkKey(key):
                continue

            keyNode = nodes.get(key)
            if keyNode is None:
                nodes[key] = keyNode = CascadeNode(key)
            keyNode.template = template

            parser.parse(template)
            for var in filter(cls.checkKey, parser.missingVars):
                varNode = nodes.get(var)
                if varNode is None:
                    nodes[var] = varNode = CascadeNode(var)

                varNode.outKeys.add(key)

        # print("=== Graph Nodes ===")
        # for k, v in nodes.items():
        #     print(f"{k} => {v.outKeys} - '{v.template}'")
        # print("===")
        return nodes

    @staticmethod
    def checkKey(key: str) -> bool:
        return key == FileTypeSelector.TYPE_TXT or key.startswith("tags.") or key.startswith("captions.")

    def resetState(self):
        for node in self.nodes.values():
            node.state = DfsState.Unvisited

    def topologicalSort(self, startNode: CascadeNode) -> tuple[list[CascadeNode], dict[str, list[str]]]:
        stack: list[tuple[CascadeNode, Iterator[str]]] = [(startNode, iter(startNode.outKeys))]
        order: list[CascadeNode] = []
        paths: dict[str, list[str]] = {}

        startNode.state = DfsState.Visiting
        while stack:
            node, neighbors = stack[-1]

            for neighKey in neighbors:
                neighNode = self.nodes[neighKey]

                if neighNode.state == DfsState.Visiting:
                    cyclePath = [n for n, _ in stack] + [neighNode]
                    raise CycleError(cyclePath)

                if neighNode.state == DfsState.Unvisited:
                    neighNode.state = DfsState.Visiting
                    stack.append((neighNode, iter(neighNode.outKeys)))
                    break

            # All neighbor nodes visited - loop completed without breaking
            else:
                paths[node.key] = [n.key for n, _ in stack]
                stack.pop()
                node.state = DfsState.Done
                order.append(node)

        order.reverse()
        return order, paths

    @classmethod
    def getFirstCycle(cls, templates: dict[str, str]) -> str:
        graph = CascadeGraph(templates)
        for startNode in graph.nodes.values():
            if startNode.state == DfsState.Unvisited:
                try:
                    graph.topologicalSort(startNode)
                except CycleError as ex:
                    return " ➜ ".join(node.key for node in ex.path)

        return ""



class CascadeGraphCache:
    def __init__(self):
        self.graphCache: dict[str, CascadeGraph] = {}       # Folder => Graph
        self.templateCache: dict[str, dict[str, str]] = {}  # Folder => Accumulated templates

    def getGraph(self, imgPath: str) -> CascadeGraph:
        folder = os.path.dirname(imgPath)
        templates = self.templateCache.get(folder)

        # Create cache entries for all parent folders
        if templates is None:
            templates = {}

            jsonFiles, _ = CascadeUpdate.getJsonFiles(imgPath)
            for path in jsonFiles[:-1]:
                folderPath = os.path.dirname(path)

                folderTemplates = self.templateCache.get(folderPath)
                if folderTemplates is not None:
                    templates.update(folderTemplates)
                else:
                    captionFile = CaptionFile(path)
                    if captionFile.loadFromJson():
                        templates.update(captionFile.cascade)

                    folderTemplates = templates.copy()
                    self.templateCache[folderPath] = folderTemplates
                    self.graphCache[folderPath] = CascadeGraph(folderTemplates)

        # Add file templates
        path = os.path.splitext(imgPath)[0] + ".json"
        captionFile = CaptionFile(path)
        if captionFile.loadFromJson() and captionFile.cascade:
            templates.update(captionFile.cascade)
            return CascadeGraph(templates)
        else:
            graph = self.graphCache[folder]
            graph.resetState()
            return graph



class CascadeUpdate:
    def __init__(self):
        self.parser = TemplateVariableParser()
        self._cache: CascadeGraphCache | None = None

    def enableCache(self):
        self._cache = CascadeGraphCache()


    def saveCascade(self, imgPath: str, captionFile: CaptionFile, keyType: str, keyName: str):
        key = f"{keyType}.{keyName}"
        if not keyType or not keyName:
            raise ValueError(f"Invalid key: '{key}'")

        if self._cache:
            graph = self._cache.getGraph(imgPath)
        else:
            templates = self._accumulateTemplates(imgPath)
            graph = CascadeGraph(templates)

        if key not in graph.nodes:
            return

        try:
            startNode = graph.nodes[key]
            nodeOrder, nodePaths = graph.topologicalSort(startNode)
            nodeOrder.remove(startNode)
            del nodePaths[key]
        except CycleError as ex:
            print(f"Warning: {ex}")
            return

        self._printUpdates(imgPath, nodePaths)

        self.parser.setup(imgPath, captionFile)
        for node in nodeOrder:
            assert node.template is not None
            text = self.parser.parse(node.template)

            # Immediately save or store in CaptionFile because downstream templates may depend on it
            if node.key == FileTypeSelector.TYPE_TXT:
                FileTypeSelector.saveCaptionTxt(imgPath, text)
            else:
                self._storeText(captionFile, node.key, text)

    @staticmethod
    def _storeText(captionFile: CaptionFile, key: str, text: str):
        try:
            keyType, keyName = key.split(".")
        except ValueError:
            raise ValueError(f"Invalid key: '{key}'") from None

        match keyType:
            case FileTypeSelector.TYPE_TAGS:
                captionFile.addTags(keyName, text)
            case FileTypeSelector.TYPE_CAPTIONS:
                captionFile.addCaption(keyName, text)
            case _:
                raise ValueError(f"Invalid key type: '{keyType}'")

    @staticmethod
    def _printUpdates(imgPath: str, nodePaths: dict[str, list[str]]):
        print(f"Cascading updates for: {imgPath}")

        seenKeys = set[str]()
        for pathKeys in sorted(nodePaths.values(), key=len, reverse=True):
            if not seenKeys.issuperset(pathKeys):
                seenKeys.update(pathKeys)
                nodePath = " → ".join(key for key in pathKeys)
                print(f"  {nodePath}")


    @staticmethod
    def getJsonFiles(imgFile: str) -> tuple[list[str], list[str]]:
        jsonFiles = list[str]()
        names = list[str]()
        if not imgFile:
            return jsonFiles, names

        jsonPath = os.path.splitext(imgFile)[0] + ".json"
        path, filename = os.path.split(jsonPath)
        jsonFiles.append(jsonPath)
        names.append(filename)

        while True:
            jsonPath = os.path.join(path, CASCADE_FOLDER_FILE)
            writable = os.access(path, os.W_OK)

            path, folder = os.path.split(path)

            if folder:
                if writable:
                    jsonFiles.append(jsonPath)
                    names.append(folder)
            else:
                break

        jsonFiles.reverse()
        names.reverse()
        return jsonFiles, names

    @staticmethod
    def _accumulateTemplates(imgPath: str) -> dict[str, str]:
        jsonFiles, _ = CascadeUpdate.getJsonFiles(imgPath)
        templates = {}

        for path in jsonFiles:
            captionFile = CaptionFile(path)
            if captionFile.loadFromJson():
                templates.update(captionFile.cascade)

        return templates
