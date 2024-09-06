import re, os
from batch.captionfile import CaptionFile


class PromptTemplateParser:
    def __init__(self, imgPath):
        self.imgPath = imgPath
        self.captionFile = None

        self.stripAround = True
        self.stripMultiWhitespace = True

        self._pattern = r'{{([^}]+)}}'
        self._optionalPrefix = "?"
        self._captionPrefix = "caption."


    def parse(self, text):
        prompt = re.sub(self._pattern, self._replace, text)
        if self.stripAround:
            prompt = prompt.strip()
        if self.stripMultiWhitespace:
            prompt = re.sub(r' +', " ", prompt)
            prompt = re.sub(r'\n+', "\n", prompt)
        return prompt

    def _replace(self, match) -> str:
        varOrig = match.group(1)
        var = varOrig.strip()
        optional = False
        if var.startswith(self._optionalPrefix):
            var = var[len(self._optionalPrefix):].strip()
            optional = True

        value = self._getValue(var)
        if value == None:
            return "" if optional else "{{" + varOrig + "}}"
        return value

    def _getValue(self, var):
        if var.startswith(self._captionPrefix):
            name = var[len(self._captionPrefix):]
            return self._getCaption(name)
        elif var == "tags":
            return self._getTags()
        elif var == "folder":
            return self._getFolderName()

        return None


    def _getCaption(self, name):
        if not self.captionFile:
            self.captionFile = CaptionFile(self.imgPath)
            self.captionFile.loadFromJson()
        return self.captionFile.getCaption(name)

    def _getTags(self):
        if not self.captionFile:
            self.captionFile = CaptionFile(self.imgPath)
            self.captionFile.loadFromJson()
        return self.captionFile.tags

    def _getFolderName(self):
        path = os.path.dirname(self.imgPath)
        return os.path.basename(path)


if __name__ == "__main__":
    parser = PromptTemplateParser("/home/rem/Pictures/red-tree-with-eyes.jpeg")
    prompt = "This {{folder}} is a {{?bla}} inside a {{caption.caption_round3}}.\n{{tags}}"
    prompt = parser.parse(prompt)
    print(prompt)