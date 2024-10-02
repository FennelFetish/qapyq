from typing import Generator, List

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
        # TODO: Use matcher
        return [c for c in captions if c not in self.bannedCaptions]



class SortCaptionFilter(CaptionFilter):
    def __init__(self):
        super().__init__()
        self.captionOrder = dict()

    def setup(self, captionGroups: Generator[List[str], None, None], prefix, suffix, separator) -> None:
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



class MutuallyExclusiveFilter(CaptionFilter):
    def __init__(self):
        self.groups: list[set] = list()

    def setup(self, captionGroups: Generator[List[str], None, None]) -> None:
        self.groups.clear()
        self.groups.extend(set(caps) for caps in captionGroups)

    def filterCaptions(self, captions: list[str]) -> list[str]:
        enumerated = list(enumerate(captions))
        deleteIndices = set()

        for group in self.groups:
            exists = False
            for i, cap in reversed(enumerated):
                if cap in group:
                    if exists:
                        deleteIndices.add(i)
                    exists = True
        
        for i in sorted(deleteIndices, reverse=True):
            del captions[i]
        return captions



class PrefixSuffixFilter(CaptionFilter):
    def __init__(self):
        super().__init__()
        self.prefix = ""
        self.suffix = ""

    def setup(self, prefix, suffix) -> None:
        self.prefix = prefix
        self.suffix = suffix

    def filterCaptions(self, text: str) -> str:
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

        self.exclusiveFilter = MutuallyExclusiveFilter()
        self.dupFilter = DuplicateCaptionFilter()
        self.banFilter = BannedCaptionFilter()
        self.sortFilter = SortCaptionFilter()
        self.prefixSuffixFilter = PrefixSuffixFilter()


    def setup(self, prefix: str, suffix: str, separator: str, removeDup: bool) -> None:
        self.prefix = prefix
        self.suffix = suffix
        self.separator = separator
        self.removeDup = removeDup

        self.prefixSuffixFilter.setup(prefix, suffix)

    def setBannedCaptions(self, bannedCaptions: list[str]) -> None:
        self.banFilter.setup(bannedCaptions)

    def setCaptionGroups(self, allCaptionGroups: Generator[List[str], None, None], exclusiveCaptionGroups: Generator[List[str], None, None]) -> None:
        self.exclusiveFilter.setup(exclusiveCaptionGroups)
        self.sortFilter.setup(allCaptionGroups, self.prefix, self.suffix, self.separator)


    def process(self, text: str) -> str:
        captions = [c.strip() for c in text.split(self.separator.strip())]

        # Filter mutually exclusive captions before removing duplicates: This will keep the last inserted caption
        captions = self.exclusiveFilter.filterCaptions(captions)

        if self.removeDup:
            captions = self.dupFilter.filterCaptions(captions)

        captions = self.banFilter.filterCaptions(captions)
        captions = self.sortFilter.filterCaptions(captions)

        text = self.separator.join(captions)
        text = self.prefixSuffixFilter.filterCaptions(text)
        return text
