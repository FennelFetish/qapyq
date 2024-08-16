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
    def __init__(self, captionGroups: list[list[str]], prefix="", suffix=""):
        super().__init__()
        self.captionOrder = {}

        i = 0
        for group in captionGroups:
            for caption in group:
                self.captionOrder[caption] = i
                i += 1
        
        self.captionOrder[prefix] = -1
        self.captionOrder[suffix] = 99999

    def filterCaptions(self, captions: list[str]) -> list[str]:
        order = {c: self.captionOrder.get(c, 65536) for c in captions}
        return sorted(captions, key=lambda c: order[c])


class PrefixSuffixFilter(CaptionFilter):
    def __init__(self, prefix, suffix):
        super().__init__()
        self.prefix = prefix
        self.suffix = suffix

    def filterCaptions(self, captions: list[str]) -> list[str]:
        lastIndex = len(captions) - 1
        if lastIndex < 0:
            return captions

        if not captions[0].startswith(self.prefix):
            captions[0] = self.prefix + captions[0]
        if not captions[lastIndex].endswith(self.suffix):
            captions[lastIndex] += self.suffix

        return captions
