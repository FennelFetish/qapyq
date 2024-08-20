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
    def __init__(self, bannedCaptions: list[str]):
        super().__init__()
        self.bannedCaptions = set(bannedCaptions)

    def filterCaptions(self, captions: list[str]) -> list[str]:
        # TODO: Use matcher
        return [c for c in captions if c not in self.bannedCaptions]



class SortCaptionFilter(CaptionFilter):
    def __init__(self, captionGroups: list[list[str]], prefix, suffix, separator):
        super().__init__()
        self.captionOrder = {}

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
        order = {c: self.captionOrder.get(c, 65536) for c in captions}
        return sorted(captions, key=lambda c: order[c])


class PrefixSuffixFilter(CaptionFilter):
    def __init__(self, prefix, suffix, separator):
        super().__init__()
        self.prefix = prefix
        self.suffix = suffix
        self.separator = separator

    def filterCaptions(self, captions: list[str]) -> list[str]:
        text = self.separator.join(captions)

        if not text.startswith(self.prefix):
            text = self.prefix + text
        if not text.endswith(self.suffix):
            text += self.suffix

        return [ c.strip() for c in text.split(self.separator.strip()) ]


class MutuallyExclusiveFilter(CaptionFilter):
    def __init__(self, captionGroups: list[list[str]]):
        self.groups = [set(caps) for caps in captionGroups]

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
