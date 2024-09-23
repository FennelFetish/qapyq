import re, os
from batch.captionfile import CaptionFile


class TemplateParser:
    def __init__(self, imgPath):
        self.imgPath = imgPath
        self.captionFile = None

        self.stripAround = True
        self.stripMultiWhitespace = True

        self._pattern = r'{{([^}]+)}}'
        self._optionalPrefix = "?"
        self._captionPrefix = "captions."
        self._promptPrefix = "prompts."
        self._tagPrefix = "tags."

    
    def setup(self, imgPath, captionFile):
        self.imgPath = imgPath
        self.captionFile = captionFile


    def getCaptionFile(self) -> CaptionFile:
        if not self.captionFile:
            self.captionFile = CaptionFile(self.imgPath)
            self.captionFile.loadFromJson()
        return self.captionFile


    def parse(self, text):
        prompt = re.sub(self._pattern, self._replace, text)
        if self.stripAround:
            prompt = prompt.strip()
        if self.stripMultiWhitespace:
            prompt = re.sub(r' +', " ", prompt)
            prompt = re.sub(r'\n+', "\n", prompt)
        return prompt

    def _replace(self, match) -> str:
        varOrig: str = match.group(1)
        var = varOrig.strip()
        optional = False
        if var.startswith(self._optionalPrefix):
            var = var[len(self._optionalPrefix):].strip()
            optional = True

        value = self._getValue(var)
        if value == None:
            return "" if optional else "{{" + varOrig + "}}"
        return value

    def _getValue(self, var: str):
        if var.startswith(self._captionPrefix):
            name = var[len(self._captionPrefix):]
            return self.getCaptionFile().getCaption(name)

        elif var.startswith(self._promptPrefix):
            name = var[len(self._promptPrefix):]
            return self.getCaptionFile().getPrompt(name)

        elif var.startswith(self._tagPrefix):
            name = var[len(self._tagPrefix):]
            return self.getCaptionFile().getTags(name)

        elif var == "folder":
            return self._getFolderName()

        return None

    def _getFolderName(self):
        path = os.path.dirname(self.imgPath)
        return os.path.basename(path)


if __name__ == "__main__":
    parser = TemplateParser("/home/rem/Pictures/red-tree-with-eyes.jpeg")
    prompt = "This {{folder}} is a {{?bla}} inside a {{captions.caption_round3}}.\n{{tags}}"
    prompt = parser.parse(prompt)
    print(prompt)
