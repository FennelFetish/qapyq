import re, os
from typing import Tuple, List
from PySide6 import QtWidgets, QtGui
from .captionfile import CaptionFile
from . import qtlib


class TemplateVariableParser:
    def __init__(self, imgPath: str = None):
        self.imgPath: str = imgPath
        self.captionFile: CaptionFile | None = None

        self.stripAround = True
        self.stripMultiWhitespace = True

        self._patternVars = re.compile( r'{{([^}]+)}}' )
        self._patternMultiSpace = re.compile( r'(?m) {2,}|\n{2,}' )

        self._keepVarPrefix = "!"
        self._captionPrefix = "captions."
        self._promptPrefix = "prompts."
        self._tagPrefix = "tags."

        self.missingVars = list()

    
    def setup(self, imgPath: str, captionFile: CaptionFile | None = None):
        self.imgPath = imgPath
        self.captionFile = captionFile


    def getCaptionFile(self) -> CaptionFile:
        if not self.captionFile:
            self.captionFile = CaptionFile(self.imgPath)
            self.captionFile.loadFromJson()
        return self.captionFile


    def parse(self, text: str) -> str:
        self.missingVars.clear()
        #text = text.replace('\r\n', '\n') # FIXME: Required on windows? Messes with positions
        text = self._patternVars.sub(self._replace, text)
        if self.stripAround:
            text = text.strip()
        if self.stripMultiWhitespace:
            text = self._patternMultiSpace.sub(self._replaceSpace, text)
        return text

    def _replace(self, match: re.Match) -> str:
        return self._getValue(match.group(1))

    def _replaceSpace(self, match: re.Match) -> str:
        return match.group(0)[0]


    def parseWithPositions(self, text: str) -> Tuple[str, List[List[int]]]:
        parts: list[str] = list()
        positions: list = list()
        start = 0
        promptLen = 0

        self.missingVars.clear()
        #text = text.replace('\r\n', '\n') # FIXME: Required on windows? Messes with positions
        for match in self._patternVars.finditer(text):
            value = self._getValue(match.group(1))
            lenValue = len(value)

            textBetweenVars = text[start:match.start()]
            lenBetweenVars = match.start() - start
            
            positions.append([
                match.start(), match.end(),
                promptLen+lenBetweenVars, promptLen+lenBetweenVars+lenValue
            ])

            promptLen += lenBetweenVars + lenValue
            parts.append(textBetweenVars)
            parts.append(value)
            start = match.end()

        parts.append(text[start:])
        prompt = "".join(parts)

        if self.stripAround:
            prompt = self._stripAround(prompt, positions)
        if self.stripMultiWhitespace:
            prompt = self._stripMultiWhitespace(prompt, positions)

        return prompt, positions

    def _stripAround(self, text: str, positions: list) -> str:
        # Strip left
        lenOrig = len(text)
        text = text.lstrip()
        lenStripL = len(text)
        if lSpaces := lenOrig - lenStripL:
            for pos in positions:
                pos[2] = max(pos[2]-lSpaces, 0)
                pos[3] = max(pos[3]-lSpaces, 0)

        # Strip right
        text = text.rstrip()
        lenStripR = len(text)
        if lenStripL - lenStripR:
            for pos in positions:
                pos[2] = min(pos[2], lenStripR)
                pos[3] = min(pos[3], lenStripR)

        return text

    def _stripMultiWhitespace(self, text: str, positions: list) -> str:
        parts: list[str] = list()
        start = 0
        totalShift = 0 # Account for removed characters

        for match in self._patternMultiSpace.finditer(text):
            matchStart = match.start()+1 # Keep one whitespace character
            matchEnd = match.end()
            matchLen = matchEnd - matchStart
            
            for pos in positions:
                # Removed characters before start: Shift start and end
                if (shiftStart := min(pos[2]-matchStart+totalShift, matchLen)) > 0:
                    pos[2] -= shiftStart
                    pos[3] -= shiftStart
                # Removed characters between start and end: Shift only end
                elif (shiftEnd := min(pos[3]-matchStart+totalShift, matchLen)) > 0:
                    pos[3] -= shiftEnd
            
            totalShift += matchLen
            parts.append(text[start:matchStart])
            start = matchEnd

        parts.append(text[start:])
        return "".join(parts)


    def _getValue(self, var: str) -> str:
        varOrig = var
        var = var.strip()
        
        optional = True
        if var.startswith(self._keepVarPrefix):
            var = var[len(self._keepVarPrefix):].strip()
            optional = False

        value = None
        if var.startswith(self._captionPrefix):
            name = var[len(self._captionPrefix):]
            value =  self.getCaptionFile().getCaption(name)

        elif var.startswith(self._promptPrefix):
            name = var[len(self._promptPrefix):]
            value =  self.getCaptionFile().getPrompt(name)

        elif var.startswith(self._tagPrefix):
            name = var[len(self._tagPrefix):]
            value =  self.getCaptionFile().getTags(name)

        elif var == "text":
            value = self._readTextFile()

        else:
            value = self._getImgProperties(var)

        if value:
            return value
        else:
            self.missingVars.append(var)
            return "" if optional else "{{" + varOrig + "}}"

    def _readTextFile(self) -> str | None:
        textPath = os.path.splitext(self.imgPath)[0] + ".txt"
        if os.path.exists(textPath):
            with open(textPath, 'r') as file:
                return file.read()
        return None

    def _getImgProperties(self, var: str) -> str | None:
        match var:
            case "path":
                return os.path.splitext(self.imgPath)[0]
            case "path.ext":
                return self.imgPath

            case "name":
                return os.path.splitext(os.path.basename(self.imgPath))[0]
            case "name.ext":
                return os.path.basename(self.imgPath)

            case "folder":
                path = os.path.dirname(self.imgPath)
                return os.path.basename(path)
        
        if var.startswith("folder-"):
            try:
                up = int( var[len("folder-"):] )
                path = os.path.dirname(self.imgPath)
                for _ in range(up):
                    path = os.path.dirname(path)
                return os.path.basename(path)
            except ValueError:
                return None

        return None



class VariableHighlighter:
    def __init__(self):
        self.formats = qtlib.ColorCharFormats()

    def highlight(self, source: QtWidgets.QPlainTextEdit, target: QtWidgets.QPlainTextEdit, positions, disabled=False) -> None:
        sourceCursor = source.textCursor()
        sourceCursor.setPosition(0)

        targetCursor = target.textCursor()
        targetCursor.setPosition(0)
        
        defaultFormat = self.formats.defaultFormat
        varIndex = 0
        for srcStart, srcEnd, targetStart, targetEnd in positions:
            format = self.formats.getFormat(varIndex)
            varIndex += 1

            if disabled:
                format = qtlib.toDisabledFormat(format)
            
            # Source (Variables)
            qtlib.setBoldFormat(format)
            sourceCursor.setPosition(srcStart, QtGui.QTextCursor.KeepAnchor)
            sourceCursor.setCharFormat(defaultFormat)

            sourceCursor.setPosition(srcStart)
            sourceCursor.setPosition(srcEnd, QtGui.QTextCursor.KeepAnchor)
            sourceCursor.setCharFormat(format)
            sourceCursor.setPosition(srcEnd)

            # Target (Replacement)
            qtlib.setBoldFormat(format, False)
            targetCursor.setPosition(targetStart, QtGui.QTextCursor.KeepAnchor)
            targetCursor.setCharFormat(defaultFormat)

            targetCursor.setPosition(targetStart)
            targetCursor.setPosition(targetEnd, QtGui.QTextCursor.KeepAnchor)
            targetCursor.setCharFormat(format)
            targetCursor.setPosition(targetEnd)
            
        sourceCursor.movePosition(QtGui.QTextCursor.End, QtGui.QTextCursor.KeepAnchor)
        sourceCursor.setCharFormat(defaultFormat)

        targetCursor.movePosition(QtGui.QTextCursor.End, QtGui.QTextCursor.KeepAnchor)
        targetCursor.setCharFormat(defaultFormat)




if __name__ == "__main__":
    parser = TemplateVariableParser("/home/rem/Pictures/red-tree-with-eyes.jpeg")
    parser.stripAround = True
    parser.stripMultiWhitespace = True

    input = "    {{folder}} is a {{!bla}} inside    a {{!boo}}.\nCaption:    {{nothing}}     {{captions.caption_round3}}.\n\n\nTags:            {{tags.tags}}     "
    output = parser.parse(input)
    print(f"'{output}'\n")

    output, positions = parser.parseWithPositions(input)
    print(f"'{output}'")

    print("\nPositions:")
    for varStart, varEnd, outStart, outEnd in positions:
        print(f"'{input[varStart:varEnd]}' => '{output[outStart:outEnd]}'")
