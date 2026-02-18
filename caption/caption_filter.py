import re
import numpy as np
from typing import Iterable
from typing_extensions import override
from abc import ABC, abstractmethod
from collections import defaultdict
from lib.template_parser import TemplateVariableParser
from .caption_preset import MutualExclusivity
from .caption_conditionals import ConditionalFilterRule
from .caption_highlight import MatcherNode


class CaptionFilter(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def filterCaptions(self, captions: list[str]) -> list[str]:
        ...



class DuplicateCaptionFilter(CaptionFilter):
    def __init__(self):
        super().__init__()

    def filterCaptions(self, captions: list[str]) -> list[str]:
        seen = set()
        return [c for c in captions if not (c in seen or seen.add(c))]



class BannedCaptionFilter(CaptionFilter):
    def __init__(self):
        super().__init__()
        self.bannedCaptions = set()

    def setup(self, bannedCaptions: list[str]) -> None:
        self.bannedCaptions.clear()
        self.bannedCaptions.update(bannedCaptions)

    def filterCaptions(self, captions: list[str]) -> list[str]:
        # TODO: Use matcher or regex
        return [c for c in captions if c not in self.bannedCaptions]



class WhitelistGroupsFilter(CaptionFilter):
    def __init__(self):
        self.matcherNode: MatcherNode[bool] = None

    def setup(self, captionGroups: Iterable[list[str]]) -> None:
        self.matcherNode = MatcherNode[bool]()
        for group in captionGroups:
            for caption in group:
                self.matcherNode.add(caption, True)

    def filterCaptions(self, captions: list[str]) -> list[str]:
        newCaptions: list[str] = list()
        validWords: set[str] = set()

        for cap in captions:
            words = [word for word in cap.split(" ") if word]
            validWords.clear()
            for matchWords in self.matcherNode.splitWords(words):
                validWords.update(matchWords)

            # Extra words in combined tags are not allowed:
            # When group-tags are subsets of other tags, there's no guarantee that extra words can safely be removed,
            # without introducing a new tag that is not present in the original caption.
            if validWords.issuperset(words):
                newCaptions.append(cap)

        return newCaptions



class SortCaptionFilter(CaptionFilter):
    class CaptionSortNode:
        def __init__(self, caption: str, index: int):
            self.caption = caption
            self.index = index
            self.compIndex = index
            self.words = [word for word in caption.split(" ") if word]
            self.uniqueWords = set(self.words)
            self.edges: list[SortCaptionFilter.CaptionSortNode] = None

        def edgeWeight(self, other: 'SortCaptionFilter.CaptionSortNode') -> float:
            'Symmetric: Same weight for A=>B and B=>A'
            # TODO: Fuzzy
            # Calculate Jaccard Index as similarity score
            numIntersect = len(self.uniqueWords & other.uniqueWords)
            numUnion     = len(self.uniqueWords) + len(other.uniqueWords) - numIntersect
            return numIntersect / numUnion

        def indexSortKey(self) -> int:
            return self.index


    ORDER_PREFIX_MAX = -1
    ORDER_SUFFIX_MIN = 1_000_000
    ORDER_NOTFOUND   = ORDER_SUFFIX_MIN - 1


    def __init__(self, sortNonGroup: bool):
        super().__init__()
        self.sortNonGroup = sortNonGroup

        self.captionOrder = dict[str, int]()
        self.matcherNode: MatcherNode[int] = None

    def setup(self, captionGroups: Iterable[list[str]], prefix: str, suffix: str, separator: str) -> None:
        self.captionOrder.clear()
        self.matcherNode = MatcherNode[int]()

        i = 1  # Only truthy values
        for group in captionGroups:
            for caption in group:
                self.matcherNode.add(caption, i)
                self.captionOrder[caption] = i
                i += 1

        sepStrip = separator.strip()
        prefixCaptions = [cap for c in prefix.split(sepStrip) if (cap := c.strip())]
        for i, cap in enumerate(reversed(prefixCaptions)):
            self.captionOrder[cap] = self.ORDER_PREFIX_MAX - i

        suffixCaptions = [cap for c in suffix.split(sepStrip) if (cap := c.strip())]
        for i, cap in enumerate(suffixCaptions):
            self.captionOrder[cap] = self.ORDER_SUFFIX_MIN + i


    def _sortKey(self, caption: str) -> int:
        if order := self.captionOrder.get(caption):
            return order

        # Handle sorting of combined tags
        captionWords = [word for word in caption.split(" ") if word]
        matchOrders = self.matcherNode.match(captionWords)
        numExtraWords = len(captionWords) - len(matchOrders)

        # For each two words with well-defined order, one extra word is tolerated.
        if matchOrders and numExtraWords <= len(matchOrders) // 2:
            return max(matchOrders.values())

        return self.ORDER_NOTFOUND


    def filterCaptions(self, captions: list[str]) -> list[str]:
        if not self.sortNonGroup:
            return sorted(captions, key=self._sortKey)

        captionKeys = [(cap, self._sortKey(cap)) for cap in captions]
        captionKeys.sort(key=lambda capKey: capKey[1])

        newCaptions = list[str]()
        suffixes = list[str]()

        # Build graph: Nodes=Captions, Edges=Shared words
        nodes = list[self.CaptionSortNode]()

        # Create nodes and word-to-nodes mapping
        wordNodes = defaultdict[str, set[self.CaptionSortNode]](set)
        for i, capKey in enumerate(captionKeys):
            if capKey[1] < self.ORDER_NOTFOUND:
                newCaptions.append(capKey[0])
                continue
            if capKey[1] > self.ORDER_NOTFOUND:
                suffixes.append(capKey[0])
                continue

            node = self.CaptionSortNode(capKey[0], i)
            nodes.append(node)

            for word in node.words:
                wordNodes[word].add(node)

        # Set node edges
        for node in nodes:
            edges = set[self.CaptionSortNode]()
            for word in node.words:
                edges.update(wordNodes[word])
            edges.discard(node)

            # Sort to make final order stable
            node.edges = sorted(edges, key=self.CaptionSortNode.indexSortKey)

        # Partition, sort, apply
        for comp in self._findSortedComponents(nodes):
            newCaptions.extend(n.caption for n in comp)

        newCaptions.extend(suffixes)
        return newCaptions


    def _findSortedComponents(self, nodes: list[CaptionSortNode]) -> list[list[CaptionSortNode]]:
        visited = set[self.CaptionSortNode]()
        components = list[list[self.CaptionSortNode]]()

        # Partition graph into connected components using DFS traversal
        for node in nodes:
            if node in visited:
                continue

            if not node.edges:
                visited.add(node)
                components.append([node])
                continue

            comp = list[self.CaptionSortNode]()

            stack = [node]
            while stack:
                n = stack.pop()
                if n in visited:
                    continue

                visited.add(n)
                comp.append(n)

                for edge in n.edges:
                    if edge not in visited:
                        stack.append(edge)

            comp = self._sortComponent(comp)
            components.append(comp)

        components.sort(key=lambda comp: min(n.index for n in comp))
        return components

    def _sortComponent(self, nodes: list[CaptionSortNode]) -> list[CaptionSortNode]:
        numNodes = len(nodes)
        if numNodes <= 2:
            nodes.sort(key=self.CaptionSortNode.indexSortKey)
            return nodes

        for i, node in enumerate(nodes):
            node.compIndex = i

        # Build adjacency matrix
        adj = np.zeros((numNodes, numNodes), dtype=np.float64)
        for node in nodes:
            for edge in node.edges:
                # Only process each edge once. Diagonal (self-references) are impossible.
                if node.compIndex > edge.compIndex:
                    weight = node.edgeWeight(edge)
                    adj[node.compIndex, edge.compIndex] = weight
                    adj[edge.compIndex, node.compIndex] = weight

        # Find node order and flatten graph using spectral seriation,
        # a heuristic approximation of the NP-hard linear arrangement problem.
        # The Fiedler vector partitions the graph into two parts with minimal cuts (direction of least connectivity),
        # and thus it represents a principal direction along which the nodes can be sorted.
        degree = np.diag(adj.sum(axis=0))       # Diagonal matrix with sum of edge weight
        laplace = degree - adj                  # Laplacian matrix (symmetric)
        vals, vecs = np.linalg.eigh(laplace)    # Eigendecomposition
        fiedler = vecs[:, 1]                    # Fiedler vector (eigenvector corresponding to the second smallest eigenvalue)

        nodesSorted = [nodes[int(i)] for i in np.argsort(fiedler, kind='stable')]

        # Sign of Fiedler is arbitrary: Make sort stable by reversing the order if node with smallest original index lies in the second half.
        # TODO: This breaks stable sorting for the rest. See 'test_3word_star_stable' unit test.
        minPos = nodesSorted.index(min(nodesSorted, key=self.CaptionSortNode.indexSortKey))
        if minPos > len(nodes) // 2:
            nodesSorted.reverse()

        return nodesSorted



# Removes tags depending on their position inside caption text
class MutuallyExclusiveFilter(CaptionFilter):
    def __init__(self, exclusivity: MutualExclusivity):
        self.groups: list[set[str]] = list()

        match exclusivity:
            case MutualExclusivity.KeepLast:
                self.enumerate = self.enumerateCaptionsReversed
            case MutualExclusivity.KeepFirst:
                self.enumerate = self.enumerateCaptions
            case _:
                raise ValueError("Invalid exclusivity mode")

    def setup(self, captionGroups: Iterable[list[str]]) -> None:
        self.groups.clear()
        self.groups.extend(set(caps) for caps in captionGroups)

    def filterCaptions(self, captions: list[str]) -> list[str]:
        enumerated = self.enumerate(captions)
        deleteIndices = set()

        for group in self.groups:
            exists = False
            for i, cap in enumerated:
                if cap in group:
                    if exists:
                        deleteIndices.add(i)
                    exists = True

        for i in sorted(deleteIndices, reverse=True):
            del captions[i]
        return captions

    @staticmethod
    def enumerateCaptionsReversed(captions: list[str]) -> list[tuple[int, str]]:
        return list(reversed( list(enumerate(captions)) ))

    @staticmethod
    def enumerateCaptions(captions: list[str]) -> list[tuple[int, str]]:
        return list(enumerate(captions))



# Removes tags depending on their position in group.
# Prioritizes tags that come later in the group.
class PriorityFilter():
    def __init__(self):
        self.groups: list[dict[str, int]] = list()

    def setup(self, captionGroups: Iterable[list[str]]) -> None:
        self.groups.clear()
        for group in captionGroups:
            self.groups.append({ cap: prio for prio, cap in enumerate(group) })

    def filterCaptions(self, captions: list[str]) -> list[str]:
        enumerated = list(enumerate(captions))
        allDeleteIndices: set[int] = set()
        deleteIndices: set[int] = set()

        for group in self.groups:
            deleteIndices.clear()
            keepIndex = -1
            maxPrio = -1

            for i, cap in enumerated:
                prio = group.get(cap)
                if prio is None:
                    continue

                deleteIndices.add(i)
                if prio > maxPrio:
                    maxPrio = prio
                    keepIndex = i

            deleteIndices.discard(keepIndex)
            allDeleteIndices.update(deleteIndices)

        for i in sorted(allDeleteIndices, reverse=True):
            del captions[i]
        return captions



class ConditionalsFilter(CaptionFilter):
    def __init__(self):
        self.rules = list[ConditionalFilterRule]()
        self.separator = ", "

    def setup(self, rules: Iterable[ConditionalFilterRule], separator: str) -> None:
        self.rules = list(rules)
        self.separator = separator

    def filterCaptions(self, captions: list[str]) -> list[str]:
        for rule in self.rules:
            if varParser := rule.evaluateExpression(captions):
                varParser.separator = self.separator
                for action in rule.actions:
                    captions = action(varParser, captions)

        return captions



# TODO: Or make a more general combination filter not associated with groups, with regex patterns?
# TODO: Maximum number of combined tags. Split into multiple if threshold reached.
class TagCombineFilter(CaptionFilter):
    # short hair, brown hair    -> short brown hair   short, brown -> group 0
    # messy hair, curly hair    -> messy curly hair   messy, curly -> group 1

    def __init__(self, sort: bool):
        self.groupMap = dict[str, int]() # key: tag as-is / value: group index
        self._nextGroupIndex = 1

        self.sort = sort
        self.tagOrder = dict[str, int]()
        self._nextOrder = 0

        self.matcherNode: MatcherNode[bool] = None

    def setup(self, captionGroups: Iterable[list[str]]) -> None:
        self.groupMap.clear()
        self._nextGroupIndex = 1
        self._nextOrder = 0
        self.matcherNode = MatcherNode[bool]()

        for caps in captionGroups:
            self.registerCombinationGroup(caps)

    def registerCombinationGroup(self, captions: list[str]) -> None:
        # Create new group index for each different end-word.
        groupWords: dict[str, int] = dict()

        for cap in (cap for c in captions if (cap := c.strip())):
            words = [word for word in cap.split(" ") if word]
            self.matcherNode.addWords(words, True)

            lastWord = words[-1]
            groupIndex = groupWords.get(lastWord)
            if groupIndex is None:
                groupWords[lastWord] = groupIndex = self._nextGroupIndex
                self._nextGroupIndex += 1
            self.groupMap[cap] = groupIndex

            self.tagOrder[cap] = self._nextOrder
            self._nextOrder += 1

    def _sortKey(self, tag: str) -> int:
        return self.tagOrder.get(tag, -1)

    def filterCaptions(self, captions: list[str]) -> list[str]:
        newCaptions = list[str | list[str]]()
        groups = dict[int, list[str]]()

        # Find groups
        # Splitting captions is a relatively easy way to allow combining tags with pre-existing combined tags.
        # Other tried methods failed with combining and sorting 3-word tags.
        # The current limitation here: When the combined tag contains another word that doesn't belong to the group,
        # like when it was manually edited, that tag is not split, because the order is undefined.
        for caption in self.matcherNode.splitAllPreserveExtra(captions):
            groupIndex = self.groupMap.get(caption)

            # Not registered for combination: Append unmodified string.
            if groupIndex is None:
                newCaptions.append(caption)
                continue

            group = groups.get(groupIndex)

            # First of group: Create and append list.
            if group is None:
                groups[groupIndex] = group = list[str]()
                newCaptions.append(group)

            group.append(caption)

        # Merge groups to string
        combinedWords = list[str]()
        existingWords = set[str]()
        for i, caption in enumerate(newCaptions):
            if not isinstance(caption, list):
                continue

            if self.sort and len(caption) > 1:
                caption.sort(key=self._sortKey)

            # Extract last word
            lastWord = caption[0].rsplit(" ", 1)[-1].strip()

            combinedWords.clear()
            existingWords.clear()
            existingWords.add(lastWord)

            # Remove duplicate words, keeping the last (by building in reversed order).
            # This allows combining tags with 2 or more "last words".
            for tag in reversed(caption):
                for word in reversed(tag.split(" ")[:-1]):
                    if word not in existingWords:
                        existingWords.add(word)
                        combinedWords.append(word)

            combinedWords.reverse()
            combinedWords.append(lastWord)
            newCaptions[i] = " ".join(combinedWords)

        # All lists replaced by strings
        return newCaptions



# TODO: This removes too many subsets. Create whitelist?
# Remove tags when all its words occur in another longer tag
# bamboo, forest, bamboo forest -> bamboo forest
# Also removes newly added duplicate tags when it were already combined with others in TagCombineFilter.
class SubsetFilter(CaptionFilter):
    def __init__(self):
        pass

    def filterCaptions(self, captions: list[str]) -> list[str]:
        captionWords: list[set[str]] = list()
        for cap in captions:
            words = (w.lower() for word in cap.split(" ") if (w := word.strip()))
            captionWords.append(set(words))

        newCaptions: list[str] = list()
        for i, cap in enumerate(captions):
            if not self._supersetExists(captionWords, i):
                newCaptions.append(cap)

        return newCaptions

    @staticmethod
    def _supersetExists(captionWords: list[set[str]], index: int) -> bool:
        for k in range(len(captionWords)):
            # Don't remove exact duplicates. It would remove all duplicates.
            if k != index and captionWords[k] != captionWords[index] and captionWords[k].issuperset(captionWords[index]):
                return True
        return False



class SearchReplaceFilter:
    class ReplacementParser(TemplateVariableParser):
        def __init__(self):
            super().__init__("") # Values from CaptionFile are unavailable
            self.matchGroups: dict[int, str] = dict()

        @override
        def _getImgProperties(self, var: str) -> str | None:
            try:
                val = self.matchGroups.get(int(var))
                if val is not None:
                    return val
            except ValueError:
                pass

            return super()._getImgProperties(var)

        def getReplacement(self, replacement: str, match: re.Match) -> str:
            self.matchGroups.clear()
            self.matchGroups.update(enumerate(match.groups()))
            return self.parse(replacement)


    def __init__(self):
        self.replacePairs: list[tuple[re.Pattern, str]] = list()
        self.varParser = self.ReplacementParser()

    def setup(self, searchReplacePairs: list[tuple[str, str]]) -> None:
        self.replacePairs.clear()
        for pattern, replace in searchReplacePairs:
            self.addReplacePair(pattern, replace)

    def addReplacePair(self, pattern: str, replace: str) -> None:
        try:
            self.replacePairs.append((re.compile(pattern), replace))
        except re.error as err:
            print(f"SearchReplaceFilter: Ignoring invalid regex pattern '{pattern}': {err}")

    def filterText(self, text: str) -> str:
        for pattern, replacement in self.replacePairs:
            text = pattern.sub(lambda match: self.varParser.getReplacement(replacement, match), text)
        return text



class PrefixSuffixFilter:
    def __init__(self):
        self.prefix = ""
        self.suffix = ""

        self.prefixWithSep = ""
        self.suffixWithSep = ""

    def setup(self, prefix: str, suffix: str, separator: str, prefixSep: bool, suffixSep: bool) -> None:
        self.prefix = prefix
        self.suffix = suffix

        self.prefixWithSep = prefix + separator if (prefixSep and prefix) else prefix
        self.suffixWithSep = separator + suffix if (suffixSep and suffix) else suffix

    def filterText(self, text: str) -> str:
        if not text.startswith(self.prefixWithSep):
            if not text:
                text = self.prefix
            elif text != self.prefix:
                text = self.prefixWithSep + text

        if not text.endswith(self.suffixWithSep):
            if not text:
                text = self.suffix
            elif text != self.suffix:
                text += self.suffixWithSep

        return text



class CaptionRulesSettings:
    def __init__(self):
        self.searchReplace: bool            = True
        self.ban: bool                      = True
        self.removeDuplicates: bool         = True
        self.removeMutuallyExclusive: bool  = True
        self.sort: bool                     = True
        self.combineTags: bool              = True
        self.conditionals: bool             = True
        self.prefixSuffix: bool             = True

    def getNumActiveRules(self) -> tuple[int, int]:
        rules = [
            self.searchReplace,
            self.ban,
            self.removeDuplicates,
            self.removeMutuallyExclusive,
            self.sort,
            self.combineTags,
            self.conditionals,
            self.prefixSuffix
        ]

        activeRules = list(filter(None, rules))
        return len(activeRules), len(rules)



class CaptionRulesProcessor:
    def __init__(self, separator: str, removeDup: bool, sortCaptions: bool, sortNonGroupCaptions: bool, whitelistGroups: bool):
        self.separator = separator
        self.removeDup = removeDup
        self.sortCaptions = sortCaptions
        self.whitelistGroups = whitelistGroups

        self.replaceFilter = SearchReplaceFilter()
        self.exclusiveFilterLast = MutuallyExclusiveFilter(MutualExclusivity.KeepLast)
        self.exclusiveFilterFirst = MutuallyExclusiveFilter(MutualExclusivity.KeepFirst)
        self.exclusiveFilterPriority = PriorityFilter()
        self.dupFilter = DuplicateCaptionFilter()
        self.banFilter = BannedCaptionFilter()
        self.whitelistFilter = WhitelistGroupsFilter()
        self.conditionalsFilter = ConditionalsFilter()
        self.sortFilter = SortCaptionFilter(sortNonGroupCaptions)
        self.combineFilter = TagCombineFilter(sortCaptions)
        self.subsetFilter = SubsetFilter()
        self.prefixSuffixFilter = PrefixSuffixFilter()


    def setPrefixSuffix(self, prefix: str, suffix: str, prefixSep: bool, suffixSep: bool):
        self.prefixSuffixFilter.setup(prefix, suffix, self.separator, prefixSep, suffixSep)

    def setSearchReplacePairs(self, pairs: list[tuple[str, str]]) -> None:
        self.replaceFilter.setup(pairs)

    def setBannedCaptions(self, bannedCaptions: list[str]) -> None:
        self.banFilter.setup(bannedCaptions)

    def setCaptionGroups(self, captionGroups: Iterable[ tuple[list[str], MutualExclusivity, bool] ]) -> None:
        'Takes iterable with tuples of `captions: list[str]`, `MutualExclusivity`, `combine: bool`'
        captionGroups = list(captionGroups)

        prefix = self.prefixSuffixFilter.prefix
        suffix = self.prefixSuffixFilter.suffix
        self.sortFilter.setup((group[0] for group in captionGroups), prefix, suffix, self.separator)

        if self.whitelistGroups:
            self.whitelistFilter.setup(group[0] for group in captionGroups)

        self.exclusiveFilterLast.setup(tags for tags, ex, _ in captionGroups if ex==MutualExclusivity.KeepLast)
        self.exclusiveFilterFirst.setup(tags for tags, ex, _ in captionGroups if ex==MutualExclusivity.KeepFirst)
        self.exclusiveFilterPriority.setup(tags for tags, ex, _ in captionGroups if ex==MutualExclusivity.Priority)

        self.combineFilter.setup(tags for tags, _, combine in captionGroups if combine)

    def setConditionalRules(self, rules: Iterable[ConditionalFilterRule]) -> None:
        self.conditionalsFilter.setup(rules, self.separator)


    def process(self, text: str, settings: CaptionRulesSettings = CaptionRulesSettings()) -> str:
        if settings.searchReplace:
            text = self.replaceFilter.filterText(text)

        captions = [c.strip() for c in text.split(self.separator.strip())]

        # In the original order, tags that come first have higher confidence score.

        # Sort before applying exclusive filter so the caption order defines priority (last one is kept)
        # --> No. NOTE: Sorting before the exclusive filter breaks replacement of tags when Auto Apply Rules and Mutually Exclusive are enabled.

        # Filter mutually exclusive captions before removing duplicates: This will keep the last inserted caption
        if settings.removeMutuallyExclusive:
            captions = self.exclusiveFilterLast.filterCaptions(captions)
            captions = self.exclusiveFilterFirst.filterCaptions(captions)
            captions = self.exclusiveFilterPriority.filterCaptions(captions)

        if settings.ban:
            if self.whitelistGroups:
                captions = self.whitelistFilter.filterCaptions(captions)
            else:
                captions = self.banFilter.filterCaptions(captions)

        if settings.conditionals:
            captions = self.conditionalsFilter.filterCaptions(captions)

        # Sort before combine filter so order inside group will define order of words inside combined tag
        if self.sortCaptions and settings.sort:
            captions = self.sortFilter.filterCaptions(captions)

        # Combine tags before removing subsets: When the same tag (or subsets of that tag's words) are in multiple groups,
        # the subset filter might remove them before they had the chance to combine with others.
        if settings.combineTags:
            captions = self.combineFilter.filterCaptions(captions)

        if self.removeDup and settings.removeDuplicates:
            # Remove subsets after banning, so no tags are wrongly merged and removed with banned tags.
            captions = self.subsetFilter.filterCaptions(captions)
            captions = self.dupFilter.filterCaptions(captions) # SubsetFilter won't remove exact duplicates

        # Strip and remove empty captions
        captions = (cap for c in captions if (cap := c.strip()))

        # If the caption already contains prefix or suffix as a tag in another place, and sorting is enabled,
        # that tag is sorted to front/back instead of prepending prefix/appending suffix.
        text = self.separator.join(captions)

        if settings.prefixSuffix:
            text = self.prefixSuffixFilter.filterText(text)

        return text
