import re, os, random
from typing import Tuple, List, Callable
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

        self.missingVars = set()


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
        var = var.lstrip()

        optional = True
        if var.startswith(self._keepVarPrefix):
            var = var[len(self._keepVarPrefix):].lstrip()
            optional = False

        var, *funcs = var.split("#")
        var = var.strip()

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
            for func in funcs:
                value = self._applyFunction(value, func) # Don't strip func (avoid changing arguments with spaces)
            return value

        self.missingVars.add(var)
        return "" if optional else "{{" + varOrig + "}}"


    def _readTextFile(self) -> str | None:
        textPath = os.path.splitext(self.imgPath)[0] + ".txt"
        if os.path.exists(textPath):
            try:
                with open(textPath, 'r') as file:
                    return file.read()
            except OSError:
                print(f"WARNING: Couldn't read file for {{text}} variable: {textPath}")

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

        if var.startswith("folder"):
            try:
                path = os.path.dirname(self.imgPath)
                rest = var[len("folder"):]
                if not rest:
                    return os.path.basename(path)

                if rest.startswith("-"):
                    up = int( rest[1:] )
                    for _ in range(up):
                        path = os.path.dirname(path)
                    return os.path.basename(path)

                if rest.startswith(":"):
                    basePath = rest[1:]
                    path = os.path.relpath(path, basePath)
                    # Don't allow moving up.
                    if f"..{os.sep}" in path:
                        return os.path.dirname(self.imgPath).lstrip("/\\")
                    return os.path.normpath(path)
            except ValueError:
                return None

        return None


    @staticmethod
    def _getFuncArg(args: list[str], index: int, default):
        if len(args) > index and args[index]:
            return args[index]
        return default

    @classmethod
    def _getFuncArgInt(cls, args: list[str], index: int, default: int):
        try:
            return int( cls._getFuncArg(args, index, default) )
        except ValueError:
            return default

    def _applyFunction(self, value: str, func: str) -> str:
        func, *args = func.split(":")
        func = func.strip()

        match func:
            case "lower":
                return value.lower()
            case "upper":
                return value.upper()
            case "strip":
                return value.strip()
            case "oneline":
                return value.replace("\n", "").replace("\r", "")

            case "replace":
                if len(args) > 1 and args[0]:
                    count = self._getFuncArgInt(args, 2, -1)
                    return value.replace(args[0], args[1], count)

            # TODO: Second layer of highlighting for loaded variables? (underline)
            case "replacevar":
                if len(args) > 1 and args[0]:
                    val2 = self._getValue(args[1])
                    count = self._getFuncArgInt(args, 2, -1)
                    return value.replace(args[0], val2, count)

            # TODO: replacerand  (replace with one of randomly selected)

            case "reverse":
                sep = self._getFuncArg(args, 0, ", ")
                return self._funcSplitProcess(value, sep, list[str].reverse)

            case "shuffle":
                sep = self._getFuncArg(args, 0, ", ")
                return self._funcSplitProcess(value, sep, self._funcShuffle)

            case "shufflekeep":
                keep = self._getFuncArgInt(args, 0, 1)
                sep = self._getFuncArg(args, 1, ", ")
                return self._funcSplitProcess(value, sep, self._funcShuffle, keep)

            case "first":
                count = self._getFuncArgInt(args, 0, 1)
                sep = self._getFuncArg(args, 1, ", ")
                return self._funcSplitProcess(value, sep, lambda elements: elements[:count])

            case "join":
                if not args:
                    return value

                key = args[0].strip()
                sep = self._getFuncArg(args, 1, ", ")
                val2 = self._getValue(key)
                return sep.join(val for v in (value, val2) if (val := v.strip()))

            case "nosubsets":
                if len(args) > 0 and args[0]:
                    val2 = self._getValue(args[0])
                    sep = self._getFuncArg(args, 1, ", ")
                    sepsOther = self._getFuncArg(args, 2, ",.:;")
                    return self._funcSplitProcess(value, sep, self._createFuncRemoveSubsets(val2, sepsOther))

        return value

    def _funcSplitProcess(self, value: str, sep: str, processFunc: Callable[[list[str]], list[str] | None], *processArgs):
        sepStrip = sep.strip() or sep
        endsWithSepStrip = value.endswith(sepStrip)

        elements = [ele for e in value.split(sepStrip) if (ele := e.strip())]
        result = processFunc(elements, *processArgs)
        if result is None:
            result = elements

        value = sep.join(result)
        if endsWithSepStrip:
            value += sepStrip
        return value

    def _funcShuffle(self, elements: list[str], keep=0) -> list[str]:
        keepElements = elements[:keep]
        shuffleElements = elements[keep:]

        random.shuffle(shuffleElements)
        keepElements.extend(shuffleElements)
        return keepElements

    def _createFuncRemoveSubsets(self, otherValue: str, otherSeps: str):
        sep = otherSeps[0]
        otherValue = otherValue.translate(str.maketrans({
            sepChar: sep for sepChar in otherSeps[1:]
        }))

        otherEleWords = [
            {word.lower() for w in ele.split(" ") if (word := w.strip())}
            for e in otherValue.split(sep) if (ele := e.strip())
        ]

        def funcRemoveSubsets(elements: list[str]):
            newElements = list[str]()
            for ele in elements:
                words = [word.lower() for w in ele.split(" ") if (word := w.strip())]
                if not any(otherWords.issuperset(words) for otherWords in otherEleWords):
                    newElements.append(ele)
            return newElements

        return funcRemoveSubsets



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
            sourceCursor.setPosition(srcStart, QtGui.QTextCursor.MoveMode.KeepAnchor)
            sourceCursor.setCharFormat(defaultFormat)

            sourceCursor.setPosition(srcStart)
            sourceCursor.setPosition(srcEnd, QtGui.QTextCursor.MoveMode.KeepAnchor)
            sourceCursor.setCharFormat(format)
            sourceCursor.setPosition(srcEnd)

            # Target (Replacement)
            qtlib.setBoldFormat(format, False)
            targetCursor.setPosition(targetStart, QtGui.QTextCursor.MoveMode.KeepAnchor)
            targetCursor.setCharFormat(defaultFormat)

            targetCursor.setPosition(targetStart)
            targetCursor.setPosition(targetEnd, QtGui.QTextCursor.MoveMode.KeepAnchor)
            targetCursor.setCharFormat(format)
            targetCursor.setPosition(targetEnd)

        sourceCursor.movePosition(QtGui.QTextCursor.MoveOperation.End, QtGui.QTextCursor.MoveMode.KeepAnchor)
        sourceCursor.setCharFormat(defaultFormat)

        targetCursor.movePosition(QtGui.QTextCursor.MoveOperation.End, QtGui.QTextCursor.MoveMode.KeepAnchor)
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
