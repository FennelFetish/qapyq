import os, enum
from typing import Iterator, Iterable, NamedTuple
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
        self.pathStr = " → ".join(node.key for node in path)
        super().__init__(f"Cycle in cascading updates ({self.pathStr})")



class CascadeGraph:
    def __init__(self, templates: dict[str, str]):
        self.nodes = self._buildGraph(templates)

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


    @staticmethod
    def topologicalSort(startNode: CascadeNode, excludeStartNode: bool = False) -> list[CascadeNode]:
        stack: list[tuple[CascadeNode, Iterator[CascadeNode]]] = [(startNode, iter(startNode.outNodes))]
        order: list[CascadeNode] = []

        startNode.state = DfsState.Visiting
        excludeNode = startNode if excludeStartNode else None

        while stack:
            node, neighbors = stack[-1]

            for neighNode in neighbors:
                if neighNode.state == DfsState.Visiting:
                    cyclePath = [n for n, _ in stack if n is not excludeNode]
                    cyclePath.append(neighNode)
                    raise CycleError(cyclePath)

                if neighNode.state == DfsState.Unvisited:
                    neighNode.state = DfsState.Visiting
                    stack.append((neighNode, iter(neighNode.outNodes)))
                    break

            # All neighbor nodes visited - loop completed without breaking
            else:
                if node is not excludeNode:
                    order.append(node)

                stack.pop()
                node.state = DfsState.Done

        order.reverse()
        return order

    @classmethod
    def topologicalSortMultiStart(cls, startNodes: Iterable[CascadeNode]) -> list[CascadeNode]:
        virtualRoot = CascadeNode("__virtual-cascade-root__")
        virtualRoot.outNodes.update(startNodes)
        return cls.topologicalSort(virtualRoot, True)


    def getFirstCycle(self) -> str:
        for startNode in self.nodes.values():
            if startNode.state == DfsState.Unvisited:
                try:
                    self.topologicalSort(startNode)
                except CycleError as ex:
                    return " ➜ ".join(node.key for node in ex.path)

        return ""



class CascadeGraphCache:
    def __init__(self):
        self.graphCache: dict[str, CascadeGraph] = {}       # Folder => Graph
        self.templateCache: dict[str, dict[str, str]] = {}  # Folder => Accumulated templates

    def addEntry(self, folderPath: str, templates: dict[str, str]):
        templates = templates.copy()
        self.templateCache[folderPath] = templates
        self.graphCache[folderPath] = CascadeGraph(templates)

    def getGraph(self, imgPath: str) -> CascadeGraph:
        folder = os.path.dirname(imgPath)
        templates = self.templateCache.get(folder)

        # Create cache entries for all parent folders
        if templates is None:
            templates = {}

            for path, _ in CascadeUpdate.getJsonFiles(imgPath)[:-1]:  # Only folders
                folderPath = os.path.dirname(path)

                folderTemplates = self.templateCache.get(folderPath)
                if folderTemplates is not None:
                    templates.update(folderTemplates)
                else:
                    captionFile = CaptionFile(path)
                    if captionFile.loadFromJson():
                        templates.update(captionFile.cascade)
                    self.addEntry(folderPath, templates)

        # Add file templates
        path = os.path.splitext(imgPath)[0] + ".json"
        captionFile = CaptionFile(path)

        if captionFile.loadFromJson() and captionFile.cascade:
            return CascadeGraph(templates | captionFile.cascade)  # Copy templates
        elif graph := self.graphCache.get(folder):
            graph.resetState()
            return graph
        else:
            # No cached folder graph (when CascadeUpdate.getJsonFiles() returns no folders)
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
        upstreamNodes, missingNodes = self._collectUpstreamNodes(startNode, captionFile)
        graph.resetState()

        try:
            nodeOrder = graph.topologicalSortMultiStart(chain((startNode,), upstreamNodes))
            nodeOrder.remove(startNode)
        except CycleError as ex:
            print(f"Warning: Failed to cascade updates due to reference cycle ({ex.pathStr})")
            return

        if not nodeOrder:
            return

        self._printUpdates(imgPath, startNode, nodeOrder, upstreamNodes, missingNodes)

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
    def _collectUpstreamNodes(cls, node: CascadeNode, captionFile: CaptionFile) -> tuple[set[CascadeNode], set[CascadeNode]]:
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
        missingNodes = set[CascadeNode]()
        for downNode in downstreamNodes:
            stack = [visit(downNode.inNodes)]

            while stack:
                if inNode := next(stack[-1], None):
                    if not cls._hasText(captionFile, inNode):
                        if inNode.template is None:
                            missingNodes.add(inNode)
                        else:
                            # Missing value, but upstream template exists -> evaluate template
                            upstreamNodes.add(inNode)
                            stack.append(visit(inNode.inNodes))
                else:
                    stack.pop()

        return upstreamNodes, missingNodes


    @staticmethod
    def _hasText(captionFile: CaptionFile, node: CascadeNode) -> bool:
        match node.keyType:
            case FileTypeSelector.TYPE_TXT:
                try:
                    txtPath = os.path.splitext(captionFile.jsonPath)[0] + FileTypeSelector.CAPTION_FILE_EXT
                    return os.path.getsize(txtPath) > 0
                except FileNotFoundError:
                    return False

            case FileTypeSelector.TYPE_TAGS:
                return bool(captionFile.getTags(node.keyName))
            case FileTypeSelector.TYPE_CAPTIONS:
                return bool(captionFile.getCaption(node.keyName))
            case _:
                raise ValueError(f"Failed to get value: Invalid key ({node.key})")

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
                raise ValueError(f"Failed to store value: Invalid key ({node.key})")


    @staticmethod
    def _printUpdates(imgPath: str, startNode: CascadeNode, order: list[CascadeNode], upstreamNodes: set[CascadeNode], missingNodes: set[CascadeNode]):
        # Find longest paths with dynamic programming: For each node, extend the longest incoming path.
        # Follows topological order, so all inNodes of a node are already processed.
        longestPaths: dict[CascadeNode, list[CascadeNode]] = {}
        downstreamNodes = (n for n in order if n not in upstreamNodes)
        for node in downstreamNodes:
            longest = max(
                (candidate for inNode in node.inNodes if (candidate := longestPaths.get(inNode))),
                key=len, default=None
            )

            longest = longest.copy() if longest is not None else []
            longest.append(node)
            longestPaths[node] = longest

        print(f"Cascading updates for: {imgPath}")

        if upstreamNodes:
            upstreamKeys = ", ".join(n.key for n in upstreamNodes)
            print(f"  Evaluate upstream templates for missing keys: {upstreamKeys}")

        seenNodes = set[CascadeNode]()
        for pathNodes in sorted(longestPaths.values(), key=len, reverse=True):
            if not seenNodes.issuperset(pathNodes):  # Only print lines with unseen nodes
                seenNodes.update(pathNodes)
                path = " → ".join(n.key for n in pathNodes)
                print(f"  {startNode.key} → {path}")

        if missingNodes:
            missingKeys = ", ".join(n.key for n in missingNodes)
            print(f"  Warning: Missing keys without template: {missingKeys}")


    class JsonFileInfo(NamedTuple):
        jsonPath: str
        name: str

    @classmethod
    def getJsonFiles(cls, imgFile: str) -> list[JsonFileInfo]:
        """
        Returns a list of (json path, folder name) for each parent folder of the given file,
        and one last entry for the file itself.
        """

        items = list[cls.JsonFileInfo]()
        if not imgFile:
            return items

        jsonPath = os.path.splitext(imgFile)[0] + ".json"
        path, filename = os.path.split(jsonPath)
        items.append(cls.JsonFileInfo(jsonPath, filename))

        while True:
            jsonPath = os.path.join(path, CASCADE_FOLDER_FILE)
            path, folder = os.path.split(path)

            if folder:
                items.append(cls.JsonFileInfo(jsonPath, folder))
            else:
                break

        items.reverse()
        return items

    @staticmethod
    def _accumulateTemplates(imgPath: str) -> dict[str, str]:
        templates = {}
        for path, _ in CascadeUpdate.getJsonFiles(imgPath):
            captionFile = CaptionFile(path)
            if captionFile.loadFromJson():
                templates.update(captionFile.cascade)

        return templates
