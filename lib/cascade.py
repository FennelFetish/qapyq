import os, enum
from typing import Iterator, Iterable
from itertools import chain
from .template_parser import TemplateVariableParser
from .captionfile import CaptionFile, FileTypeSelector


CASCADE_FOLDER_FILE = "qapyq_cascade.json"


class DfsState(enum.IntEnum):
    Unvisited = 0
    Visiting  = 1
    Done      = 2


class CascadeNode:
    __slots__ = ('key', 'keyType', 'keyName', 'state', 'template', 'inNodes', 'outNodes')

    def __init__(self, key: str, keyType: str = "", keyName: str = ""):
        self.key: str = key
        self.keyType: str = keyType
        self.keyName: str = keyName

        self.state = DfsState.Unvisited
        self.template: str | None = None

        self.inNodes: set[CascadeNode] = set()
        "Nodes with keys that exist in this node's template. Empty if no template is defined, or template doesn't use variables."

        self.outNodes: set[CascadeNode] = set()
        "Nodes with templates that contain variables referencing this node"

    @staticmethod
    def fromKey(key: str) -> 'CascadeNode':
        if key == FileTypeSelector.TYPE_TXT:
            return CascadeNode(key, key, "")

        try:
            keyType, keyName = key.split(".")
            if not keyType or not keyName:
                raise ValueError()

            return CascadeNode(key, keyType, keyName)

        except ValueError:
            raise ValueError(f"Invalid key: '{key}'") from None



class CycleError(ValueError):
    def __init__(self, path: list[CascadeNode]):
        self.path = path
        msg = " → ".join(node.key for node in path)
        super().__init__("Cycle in cascading updates: " + msg)



class CascadeGraph:
    def __init__(self, templates: dict[str, str]):
        self.nodes = self._buildGraph(templates)
        self._virtualRoot: CascadeNode | None = None

    @classmethod
    def _buildGraph(cls, templates: dict[str, str]) -> dict[str, CascadeNode]:
        # Parse all templates with dummy caption file to list missing variables (= all caption/tag keys)
        parser = TemplateVariableParser()
        parser.setup("/dummypath", CaptionFile(""))

        nodes = dict[str, CascadeNode]()
        for key, template in templates.items():
            if not cls.checkKey(key):
                continue

            keyNode = nodes.get(key)
            if keyNode is None:
                nodes[key] = keyNode = CascadeNode.fromKey(key)
            keyNode.template = template

            parser.parse(template)
            for var in filter(cls.checkKey, parser.missingVars):
                varNode = nodes.get(var)
                if varNode is None:
                    nodes[var] = varNode = CascadeNode.fromKey(var)

                varNode.outNodes.add(keyNode)
                keyNode.inNodes.add(varNode)

        return nodes

    def printGraph(self):
        print("=== Graph Nodes ===")
        for k, node in self.nodes.items():
            print(f"{k}")
            for n in node.inNodes:
                print(f"  In:  {n.key}")
            for n in node.outNodes:
                print(f"  Out: {n.key}")
            if node.template is not None:
                print(f"  Template: '{node.template}'")
        print("===")

    @staticmethod
    def checkKey(key: str) -> bool:
        return key == FileTypeSelector.TYPE_TXT or key.startswith("tags.") or key.startswith("captions.")

    def resetState(self):
        for node in self.nodes.values():
            node.state = DfsState.Unvisited

    def topologicalSort(self, startNode: CascadeNode) -> tuple[list[CascadeNode], dict[str, list[str]]]:
        stack: list[tuple[CascadeNode, Iterator[CascadeNode]]] = [(startNode, iter(startNode.outNodes))]
        order: list[CascadeNode] = []
        paths: dict[str, list[str]] = {}

        startNode.state = DfsState.Visiting
        while stack:
            node, neighbors = stack[-1]

            for neighNode in neighbors:
                if neighNode.state == DfsState.Visiting:
                    cyclePath = [n for n, _ in stack] + [neighNode]
                    raise CycleError(cyclePath)

                if neighNode.state == DfsState.Unvisited:
                    neighNode.state = DfsState.Visiting
                    stack.append((neighNode, iter(neighNode.outNodes)))
                    break

            # All neighbor nodes visited - loop completed without breaking
            else:
                if node is not self._virtualRoot:
                    paths[node.key] = [n.key for n, _ in stack if n is not self._virtualRoot]
                    order.append(node)

                stack.pop()
                node.state = DfsState.Done

        order.reverse()
        return order, paths

    def topologicalSortMultiStart(self, startNodes: Iterable[CascadeNode]) -> tuple[list[CascadeNode], dict[str, list[str]]]:
        try:
            self._virtualRoot = CascadeNode("__virtual-cascade-root__")
            self._virtualRoot.outNodes.update(startNodes)
            return self.topologicalSort(self._virtualRoot)  # Resets state of virtual root to DfsState.Visiting
        finally:
            self._virtualRoot = None


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
        elif graph := self.graphCache.get(folder):
            graph.resetState()
            return graph
        else:
            # No cached folder graph (when CascadeUpdate.getJsonFiles() finds no writable folders)
            return CascadeGraph({})



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

        startNode = graph.nodes.get(key)
        if startNode is None:
            return

        # Collect upstream dependencies where values are missing but a template exists.
        # These templates are evaluated to fill values in downstream templates, but the value is not saved to disk.
        upstreamNodes = self._collectUpstreamNodes(startNode, captionFile)
        graph.resetState()

        try:
            nodeOrder, nodePaths = graph.topologicalSortMultiStart(chain((startNode,), upstreamNodes))
            nodeOrder.remove(startNode)
            del nodePaths[key]
        except CycleError as ex:
            print(f"Warning: {ex}")
            return

        if not nodeOrder:
            return

        self._printUpdates(imgPath, nodePaths)

        self.parser.setup(imgPath, captionFile)
        with self.parser.withTemporaryOverrides() as upstreamValues:
            for node in nodeOrder:
                assert node.template is not None
                text = self.parser.parse(node.template)

                # Immediately save or store in CaptionFile because downstream templates may depend on it
                if node in upstreamNodes:
                    upstreamValues[node.key] = text
                else:
                    self._storeText(captionFile, node, text)


    @classmethod
    def _collectUpstreamNodes(cls, node: CascadeNode, captionFile: CaptionFile) -> set[CascadeNode]:
        def visit(nodes: set[CascadeNode]):
            for node in nodes:
                if node.state == DfsState.Unvisited:
                    node.state = DfsState.Done
                    yield node

        node.state = DfsState.Done
        stack: list[Iterator[CascadeNode]] = [visit(node.outNodes)]

        # The collecting runs in two phases to ensure downstream nodes are not wrongly marked as upstream.
        # First collect all downstream nodes that are reachable from the start node and mark them as DfsState.Done through visit().
        downstreamNodes = list[CascadeNode]()
        while stack:
            if outNode := next(stack[-1], None):
                downstreamNodes.append(outNode)
                stack.append(visit(outNode.outNodes))
            else:
                stack.pop()

        # Collect upstream nodes for all gathered downstream nodes
        upstreamNodes = set[CascadeNode]()
        for downNode in downstreamNodes:
            stack = [visit(downNode.inNodes)]

            while stack:
                if inNode := next(stack[-1], None):
                    # Template exists, but missing value -> evaluate template
                    if (inNode.template is not None) and (not cls._getText(captionFile, inNode)):
                        upstreamNodes.add(inNode)
                        stack.append(visit(inNode.inNodes))
                else:
                    stack.pop()

        return upstreamNodes


    @staticmethod
    def _getText(captionFile: CaptionFile, node: CascadeNode) -> str | None:
        match node.keyType:
            case FileTypeSelector.TYPE_TXT:
                return FileTypeSelector.loadCaptionTxt(captionFile.jsonPath)
            case FileTypeSelector.TYPE_TAGS:
                return captionFile.getTags(node.keyName)
            case FileTypeSelector.TYPE_CAPTIONS:
                return captionFile.getCaption(node.keyName)
            case _:
                raise ValueError(f"Failed to get caption: Invalid key ({node.key})")

    @staticmethod
    def _storeText(captionFile: CaptionFile, node: CascadeNode, text: str):
        match node.keyType:
            case FileTypeSelector.TYPE_TXT:
                FileTypeSelector.saveCaptionTxt(captionFile.jsonPath, text)
            case FileTypeSelector.TYPE_TAGS:
                captionFile.addTags(node.keyName, text)
            case FileTypeSelector.TYPE_CAPTIONS:
                captionFile.addCaption(node.keyName, text)
            case _:
                raise ValueError(f"Failed to store caption: Invalid key ({node.key})")

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
        """
        Returns a list of (json path, folder name) for each writable parent folder of the given file,
        and one last entry for the file itself.
        """

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
