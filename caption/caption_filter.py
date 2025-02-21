from typing import Iterable
import re
from .caption_preset import MutualExclusivity


class CaptionFilter:
    def __init__(self):
        pass

    def filterCaptions(self, captions: list[str]) -> list[str]:
        raise NotImplementedError("You must override this method in your subclass.")



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



class SortCaptionFilter(CaptionFilter):
    def __init__(self):
        super().__init__()
        self.captionOrder = dict()

    def setup(self, captionGroups: Iterable[list[str]], prefix, suffix, separator) -> None:
        self.captionOrder.clear()

        i = 0
        for group in captionGroups:
            for caption in group:
                self.captionOrder[caption] = i
                i += 1

        separator = separator.strip()
        prefixCaptions = [c.strip() for c in prefix.split(separator)]
        for i, c in enumerate(reversed(prefixCaptions)):
            self.captionOrder[c] = -1-i

        suffixCaptions = [c.strip() for c in suffix.split(separator)]
        for i, c in enumerate(suffixCaptions):
            self.captionOrder[c] = 100000+i

    def filterCaptions(self, captions: list[str]) -> list[str]:
        order = {c: self.captionOrder.get(c, 65536) for c in captions} # TODO: Extra dict not necessary?
        return sorted(captions, key=lambda c: order[c])



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



# Removes tags depending on their position in group
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



# TODO: Wildcard that matches all colors?
# TODO: Or make a more general combination filter not associated with groups, with regex patterns?s
# TODO: Maximum number of combined tags. Split into multiple if threshold reached.
class TagCombineFilter(CaptionFilter):
    # short hair, brown hair    -> short brown hair   short, brown -> group 0
    # messy hair, curly hair    -> messy curly hair   messy, curly -> group 1

    def __init__(self):
        self.groupMap: dict[str, int] = dict() # key: tag as-is / value: group index
        self._nextGroupIndex = 1

    def setup(self, captionGroups: Iterable[list[str]]) -> None:
        self.groupMap.clear()
        self._nextGroupIndex = 1
        for caps in captionGroups:
            self.registerCombinationGroup(caps)

    def registerCombinationGroup(self, captions: list[str]) -> None:
        # Create new group index for each different end-word.
        groupWords: dict[str, int] = dict()

        for cap in captions:
            cap = cap.strip()
            if not cap:
                continue

            groupWord = cap.rsplit(" ", 1)[-1]
            groupIndex = groupWords.get(groupWord)
            if groupIndex is None:
                groupIndex = self._nextGroupIndex
                groupWords[groupWord] = groupIndex
                self._nextGroupIndex += 1

            self.groupMap[cap] = groupIndex

    def filterCaptions(self, captions: list[str]) -> list[str]:
        newCaptions: list[str | list[str]] = list()
        groups: dict[int, list[str]] = dict()

        # Find groups
        for caption in captions:
            # TODO: Also match When all words in this caption are part of a group separately (for adding new words to existing combined captions)
            groupIndex = self.groupMap.get(caption)

            # Not registered for combination: Append unmodified string.
            if groupIndex is None:
                newCaptions.append(caption)
                continue

            group = groups.get(groupIndex)

            # First of group: Create and append list.
            if group is None:
                group = list()
                newCaptions.append(group)
                groups[groupIndex] = group

            group.append(caption)

        # Merge groups to string
        existingWords: set[str] = set()
        for i, caption in enumerate(newCaptions):
            if not isinstance(caption, list):
                continue

            # Extract last word
            lastWord = caption[0].rsplit(" ", 1)[-1].strip()
            combined = lastWord
            for tag in reversed(caption):
                # Remove last word from tag.
                # Prepend to 'combined' only if tag is not empty afterwards (when tag had multiple words).
                if tag := tag.rsplit(" ", 1)[:-1]:
                    tag = tag[0].strip()
                    combined = f"{tag} {combined}"

            # Remove duplicate words, keeping the last.
            # This allows combining tags with 2 or more "last words".
            existingWords.clear()
            existingWords.add(lastWord)

            words = combined.split(" ")
            combined = lastWord
            for word in reversed(words):
                if word in existingWords:
                    continue
                existingWords.add(word)
                combined = f"{word} {combined}"

            newCaptions[i] = combined

        # All lists replaced by strings
        return newCaptions



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
    def __init__(self):
        self.replacePairs: list[tuple[re.Pattern, str]] = list()

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
            text = pattern.sub(replacement, text)
        return text



class PrefixSuffixFilter:
    def __init__(self):
        self.prefix = ""
        self.suffix = ""

    def setup(self, prefix, suffix) -> None:
        self.prefix = prefix
        self.suffix = suffix

    def filterText(self, text: str) -> str:
        if not text.startswith(self.prefix):
            text = self.prefix + text
        if not text.endswith(self.suffix):
            text += self.suffix
        return text



class CaptionRulesProcessor:
    def __init__(self):
        self.prefix = ""
        self.suffix = ""
        self.separator = ", "
        self.removeDup = True
        self.sortCaptions = True

        self.replaceFilter = SearchReplaceFilter()
        self.exclusiveFilterLast = MutuallyExclusiveFilter(MutualExclusivity.KeepLast)
        self.exclusiveFilterFirst = MutuallyExclusiveFilter(MutualExclusivity.KeepFirst)
        self.exclusiveFilterPriority = PriorityFilter()
        self.dupFilter = DuplicateCaptionFilter()
        self.banFilter = BannedCaptionFilter()
        self.sortFilter = SortCaptionFilter()
        self.combineFilter = TagCombineFilter()
        self.subsetFilter = SubsetFilter()
        self.prefixSuffixFilter = PrefixSuffixFilter()


    def setup(self, prefix: str, suffix: str, separator: str, removeDup: bool, sortCaptions: bool) -> None:
        self.prefix = prefix
        self.suffix = suffix
        self.separator = separator
        self.removeDup = removeDup
        self.sortCaptions = sortCaptions

        self.prefixSuffixFilter.setup(prefix, suffix)

    def setSearchReplacePairs(self, pairs: list[tuple[str, str]]) -> None:
        self.replaceFilter.setup(pairs)

    def setBannedCaptions(self, bannedCaptions: list[str]) -> None:
        self.banFilter.setup(bannedCaptions)

    def setCaptionGroups(self, captionGroups: Iterable[ tuple[list[str], MutualExclusivity, bool] ]) -> None:
        'Takes iterable with tuples of `captions: list[str]`, `MutualExclusivity`, `combine: bool`'
        captionGroups = list(captionGroups)

        allGroups = (group[0] for group in captionGroups)
        self.sortFilter.setup(allGroups, self.prefix, self.suffix, self.separator)

        self.exclusiveFilterLast.setup(tags for tags, ex, _ in captionGroups if ex==MutualExclusivity.KeepLast)
        self.exclusiveFilterFirst.setup(tags for tags, ex, _ in captionGroups if ex==MutualExclusivity.KeepFirst)
        self.exclusiveFilterPriority.setup(tags for tags, ex, _ in captionGroups if ex==MutualExclusivity.Priority)

        self.combineFilter.setup(tags for tags, _, combine in captionGroups if combine)


    def process(self, text: str) -> str:
        text = self.replaceFilter.filterText(text)
        captions = [c.strip() for c in text.split(self.separator.strip())]

        # In the original order, tags that come first have higher confidence score.

        # Sort before applying exclusive filter so the caption order defines priority (last one is kept)
        # --> No. NOTE: Sorting before the exclusive filter breaks replacement of tags when Auto Apply Rules and Mutually Exclusive are enabled.

        # Filter mutually exclusive captions before removing duplicates: This will keep the last inserted caption
        captions = self.exclusiveFilterLast.filterCaptions(captions)
        captions = self.exclusiveFilterFirst.filterCaptions(captions)
        captions = self.exclusiveFilterPriority.filterCaptions(captions)

        captions = self.banFilter.filterCaptions(captions)

        if self.removeDup:
            # Remove subsets after banning, so no tags are wrongly merged and removed with banned tags.
            captions = self.subsetFilter.filterCaptions(captions)
            captions = self.dupFilter.filterCaptions(captions) # SubsetFilter won't remove exact duplicates

        # Sort before combine filter so order inside group will define order of words inside combined tag
        if self.sortCaptions:
            captions = self.sortFilter.filterCaptions(captions)

        captions = self.combineFilter.filterCaptions(captions)

        # Strip and remove empty captions
        captions = (cap for c in captions if (cap := c.strip()))

        text = self.separator.join(captions)
        text = self.prefixSuffixFilter.filterText(text)
        return text
