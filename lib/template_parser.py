import re, os, random
from typing import Tuple, List, Callable, NamedTuple, TYPE_CHECKING
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from PySide6 import QtWidgets, QtGui
from config import Config
from .captionfile import CaptionFile
from .colorlib import ColorCharFormats

if TYPE_CHECKING:
    from caption.caption_filter import CaptionRulesProcessor


class TemplateVariableParser:
    PATTERN_VARS        = re.compile( r'{{((?:[^}\\]|\\.)*?)}}' )  # Matches '{{...}}' and allows escaping '\}'
    PATTERN_MULTI_SPACE = re.compile( r'(?m) {2,}|\n{2,}' )

    PREFIX_KEEP_VAR     = "!"
    PREFIX_CAPTION      = "captions."
    PREFIX_PROMPT       = "prompts."
    PREFIX_TAG          = "tags."


    def __init__(self, imgPath: str = None):
        self.imgPath: str = imgPath
        self.captionFile: CaptionFile | None = None

        self.stripAround = True
        self.stripMultiWhitespace = True

        self._tempOverrides: dict[str, str] = dict()

        self.missingVars = set()
        self.storedVars: dict[str, str] = dict()


    def setup(self, imgPath: str, captionFile: CaptionFile | None = None):
        self.imgPath = imgPath
        self.captionFile = captionFile


    def getCaptionFile(self) -> CaptionFile:
        if not self.captionFile:
            self.captionFile = CaptionFile(self.imgPath)
            self.captionFile.loadFromJson()
        return self.captionFile


    @contextmanager
    def withTemporaryOverrides(self):
        try:
            yield self._tempOverrides
        finally:
            self._tempOverrides = {}


    def parse(self, text: str) -> str:
        self.missingVars.clear()

        try:
            #text = text.replace('\r\n', '\n') # FIXME: Required on windows? Messes with positions
            text = self.PATTERN_VARS.sub(self._replace, text)

            if self.stripAround:
                text = text.strip()
            if self.stripMultiWhitespace:
                text = self.PATTERN_MULTI_SPACE.sub(self._replaceSpace, text)

            return text

        finally:
            self.storedVars.clear()

    def _replace(self, match: re.Match) -> str:
        return self._getValue(match.group(1))

    @staticmethod
    def _replaceSpace(match: re.Match) -> str:
        return match.group(0)[0]


    def parseWithPositions(self, text: str) -> Tuple[str, List[List[int]]]:
        parts: list[str] = list()
        positions: list = list()
        start = 0
        promptLen = 0

        self.missingVars.clear()

        try:
            #text = text.replace('\r\n', '\n') # FIXME: Required on windows? Messes with positions
            for match in self.PATTERN_VARS.finditer(text):
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

        finally:
            self.storedVars.clear()

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

        for match in self.PATTERN_MULTI_SPACE.finditer(text):
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
        try:
            expr = ExpressionParser.parse(var)
            return self._evalExpression(expr)
        except ValueError as ex:
            print(f"Template parser error: {ex}")
            return ""

    def _evalSubExpression(self, sub: 'Sub') -> str:
        return sub.literal if sub.expr is None else self._evalExpression(sub.expr)

    def _evalExpression(self, expr: 'Expr') -> str:
        var = self._evalSubExpression(expr.name).strip()
        args = [self._evalSubExpression(arg) for arg in expr.args]

        optional = True
        if var.startswith(self.PREFIX_KEEP_VAR):
            var = var[len(self.PREFIX_KEEP_VAR):].lstrip()
            optional = False

        value = self._tempOverrides.get(var)
        if value is None:
            if var.startswith(self.PREFIX_TAG):
                name = var[len(self.PREFIX_TAG):].lstrip()
                value = self.getCaptionFile().getTags(name)

            elif var.startswith(self.PREFIX_CAPTION):
                name = var[len(self.PREFIX_CAPTION):].lstrip()
                value = self.getCaptionFile().getCaption(name)

            elif var.startswith(self.PREFIX_PROMPT):
                name = var[len(self.PREFIX_PROMPT):].lstrip()
                value = self.getCaptionFile().getPrompt(name)

            elif var == "text":
                value = self._readTextFile()

            else:
                value = self._getImgProperties(var, args)
                if value is None:
                    value = self._getMoreValues(var, args)

            if not value:
                self.missingVars.add(var)
                value = ""

        for func in expr.funcs:
            value = self._applyFunction(value, func) # Don't strip func (avoid changing arguments with spaces)

        if value or optional:
            return value
        return "".join(("{{", str(expr), "}}"))


    def _readTextFile(self) -> str | None:
        textPath = os.path.splitext(self.imgPath)[0] + ".txt"
        if os.path.exists(textPath):
            try:
                with open(textPath, 'r') as file:
                    return file.read()
            except OSError:
                print(f"WARNING: Couldn't read file for {{text}} variable: {textPath}")

        return None


    def _getImgProperties(self, var: str, args: list[str]) -> str | None:
        match var:
            case "path":
                return os.path.splitext(self.imgPath)[0]
            case "path.ext":
                return self.imgPath

            case "name":
                return os.path.splitext(os.path.basename(self.imgPath))[0]
            case "name.ext":
                return os.path.basename(self.imgPath)

            case "ext":
                return os.path.splitext(self.imgPath)[1].lstrip(".")

        if var.startswith("folder"):
            try:
                path = os.path.dirname(self.imgPath)
                rest = var[len("folder"):]
                if not rest:
                    if basePath := ":".join(args):
                        return self.makeRelPath(path, basePath)
                    else:
                        return os.path.basename(path)

                if rest.startswith("-"):
                    up = int( rest[1:] )
                    for _ in range(up):
                        path = os.path.dirname(path)
                    return os.path.basename(path)

            except ValueError:
                return None

        return None


    def _getMoreValues(self, var: str, args: list[str]) -> str | None:
        match var:
            case "date":
                return datetime.now().strftime('%Y%m%d')
            case "time":
                return datetime.now().strftime('%H%M%S')

            case "load":
                if args:
                    return self.storedVars.get(args[0].strip(), "")

            case "static":
                if args:
                    return args[0]

            case "coinflip":
                valTrue  = self._getFuncArg(args, 0, "1")
                valFalse = self._getFuncArg(args, 1, "0")
                chance   = self._getFuncArgInt(args, 2, 2)
                return valTrue if random.random() < 1/chance else valFalse

        return None


    @staticmethod
    def _matchNameGetArgs(var: str, expectedName: str) -> list[str] | None:
        if not var.startswith(expectedName):
            return None

        name, *args = var.split(":")
        if len(name.strip()) == len(expectedName):
            return args or [""]
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


    def _applyFunction(self, value: str, func: 'Func') -> str:
        funcName = self._evalSubExpression(func.name).strip()
        args = [self._evalSubExpression(arg) for arg in func.args]

        match funcName:
            # String functions

            case "store":
                if var := self._getFuncArg(args, 0, "").strip():
                    self.storedVars[var] = value
                    return ""

            case "lower":
                return value.lower()
            case "upper":
                return value.upper()
            case "capitalize":
                return value.capitalize()
            case "strip":
                return value.strip()
            case "oneline":
                return value.replace("\n", "").replace("\r", "")

            case "default":
                return value if (value or not args) else args[0]
            case "defaultvar":
                return value if (value or not args) else self._getValue(args[0])

            case "replace":
                if len(args) > 1 and args[0]:
                    count = self._getFuncArgInt(args, 2, -1)
                    return value.replace(args[0], args[1], count)

            case "replacevar":
                if len(args) > 1 and args[0]:
                    val2 = self._getValue(args[1])
                    count = self._getFuncArgInt(args, 2, -1)
                    return value.replace(args[0], val2, count)

            # TODO: replacerand  (replace with one of randomly selected)

            case "join":
                if len(args) > 0 and args[0]:
                    key = args[0].strip()
                    sep = self._getFuncArg(args, 1, ", ")
                    val2 = self._getValue(key)
                    return sep.join(val for v in (value, val2) if (val := v.strip()))

            case "append":
                if val2 := self._getFuncArg(args, 0, ""):
                    sep = self._getFuncArg(args, 1, ", ")
                    return sep.join(val for v in (value, val2) if (val := v.strip()))

            case "prepend":
                if val2 := self._getFuncArg(args, 0, ""):
                    sep = self._getFuncArg(args, 1, ", ")
                    return sep.join(val for v in (val2, value) if (val := v.strip()))

            case "noprefix":
                for prefix in self._getFuncArg(args, 0, "A ,a ,An ,an ,The ,the ").split(","):
                    value = value.removeprefix(prefix)
                return value

            # List functions

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

            case "drop":
                count = max(1, self._getFuncArgInt(args, 0, 1))
                sep = self._getFuncArg(args, 1, ", ")
                return self._funcSplitProcess(value, sep, lambda elements: elements[:-count])

            # Set operations on tags

            case "nodup":
                sep = self._getFuncArg(args, 0, ", ")
                return self._funcSplitProcess(value, sep, self._funcRemoveDuplicates)

            case "nosubsets":
                if len(args) > 0 and args[0]:
                    val2 = self._getValue(args[0])
                    sep = self._getFuncArg(args, 1, ", ")
                    sepsOther = self._getFuncArg(args, 2, ",.:;")
                    sepsWord = self._getFuncArg(args, 3, " -")
                    return self._funcSplitProcess(value, sep, self._createFuncRemoveSubsets(val2, sepsOther, sepsWord))

            case "add":
                if len(args) > 0 and args[0]:
                    sep = self._getFuncArg(args, 1, ", ")
                    return self._funcSplitProcess(value, sep, self._createFuncAdd(args[0], sep.strip()))

            case "addvar":
                if len(args) > 0 and args[0]:
                    val2 = self._getValue(args[0])
                    sep = self._getFuncArg(args, 1, ", ")
                    sepsOther = self._getFuncArg(args, 2, ",.:;")
                    return self._funcSplitProcess(value, sep, self._createFuncAdd(val2, sepsOther))

            case "subtract":
                if len(args) > 0 and args[0]:
                    sep = self._getFuncArg(args, 1, ", ")
                    return self._funcSplitProcess(value, sep, self._createFuncSubtract(args[0], sep.strip()))

            case "subtractvar":
                if len(args) > 0 and args[0]:
                    val2 = self._getValue(args[0])
                    sep = self._getFuncArg(args, 1, ", ")
                    sepsOther = self._getFuncArg(args, 2, ",.:;")
                    return self._funcSplitProcess(value, sep, self._createFuncSubtract(val2, sepsOther))

            # Conditions
            case "ifcontains":
                if search := self._getFuncArg(args, 0, ""):
                    argIndex = 1 if (search in value) else 2
                    return self._getFuncArg(args, argIndex, "")

            # Rules
            case "rules":
                # Re-join args that were previously split by ":" to reconstruct Windows paths (C:\).
                if path := ":".join(args):
                    if rulesProcessor := TemplateRulesProcessor.getProcessor(path):
                        return rulesProcessor.process(value)

            # TODO: Function for limiting text to max token count

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

    def _funcRemoveDuplicates(self, elements: list[str]) -> list[str]:
        seen = set[str]()
        return [e for e in elements if not (e in seen or seen.add(e))]

    def _createFuncRemoveSubsets(self, otherValue: str, otherSeps: str, wordSeps: str):
        sep = otherSeps[0]
        otherValue = otherValue.translate(str.maketrans({
            sepChar: sep for sepChar in otherSeps[1:]
        }))

        wordSep = wordSeps[0]
        wordSepTrans = str.maketrans({
            sepChar: wordSep for sepChar in wordSeps[1:]
        })

        otherEleWords = [
            {word.lower() for w in ele.translate(wordSepTrans).split(wordSep) if (word := w.strip())}
            for e in otherValue.split(sep) if (ele := e.strip())
        ]

        def funcRemoveSubsets(elements: list[str]):
            newElements = list[str]()
            for ele in elements:
                words = [word.lower() for w in ele.translate(wordSepTrans).split(wordSep) if (word := w.strip())]
                if not any(otherWords.issuperset(words) for otherWords in otherEleWords):
                    newElements.append(ele)
            return newElements

        return funcRemoveSubsets

    def _createFuncAdd(self, otherValue: str, otherSeps: str):
        sep = otherSeps[0]
        otherValue = otherValue.translate(str.maketrans({
            sepChar: sep for sepChar in otherSeps[1:]
        }))

        otherElements: list = [ele for e in otherValue.split(sep) if (ele := e.strip())]

        def funcAdd(elements: list[str]):
            seen = set(elements)
            elements += [ele for ele in otherElements if not (ele in seen or seen.add(ele))]
            return elements

        return funcAdd

    def _createFuncSubtract(self, otherValue: str, otherSeps: str):
        sep = otherSeps[0]
        otherValue = otherValue.translate(str.maketrans({
            sepChar: sep for sepChar in otherSeps[1:]
        }))

        otherElements: set = {ele for e in otherValue.split(sep) if (ele := e.strip())}

        def funcSubtract(elements: list[str]):
            return [ele for ele in elements if ele not in otherElements]

        return funcSubtract


    # === Utility Functions ===

    @staticmethod
    def makeRelPath(path: str, basePath: str) -> str:
        '''
        Creates the normalized relative path from `basePath` to `path`.\n
        Returns `path` without leading slashes when the relative path had `..` components.
        '''

        relativePath = os.path.relpath(path, basePath)

        # Don't allow moving up.
        if ".." in relativePath.split(os.sep):
            return path.lstrip("/\\")

        return os.path.normpath(relativePath)


    @staticmethod
    def splitPathByVars(pathTemplate: str) -> tuple[str, str]:
        '''
        Splits the path into components without and with variables.\n
        Returns `(head, tail)` where `head` is the part without variables.
        '''

        varIndex = pathTemplate.find("{{")
        if varIndex < 0:
            return pathTemplate, ""

        sepIndex = pathTemplate.rfind(os.sep, 0, varIndex) + 1
        return pathTemplate[:sepIndex], pathTemplate[sepIndex:]



class Sub(NamedTuple):
    expr: 'Expr | None' = None
    literal: str = ""

    def __str__(self) -> str:
        return f"[{self.expr}]" if self.expr else self.literal

    def print(self, level: int):
        indent = "  " * level
        if self.expr:
            print(f"{indent}sub expr:")
            self.expr.print(level + 1)
        else:
            print(f"{indent}sub literal: '{self.literal}'")

class Func(NamedTuple):
    name: Sub
    args: list[Sub]

    def __str__(self) -> str:
        return "#" + ":".join(str(sub) for sub in (self.name, *self.args))

    def print(self, level: int):
        indent = "  " * level
        print(f"{indent}func name:")
        self.name.print(level + 1)
        if self.args:
            print(f"{indent}func args:")
            for arg in self.args:
                arg.print(level + 1)

class Expr(NamedTuple):
    name:  Sub
    args:  list[Sub]
    funcs: list[Func]

    def __str__(self):
        text = ":".join(str(sub) for sub in (self.name, *self.args))
        text += "".join(str(func) for func in self.funcs)
        return text

    def print(self, level: int = 0):
        indent = "  " * level
        print(f"{indent}expr name:")
        self.name.print(level + 1)
        if self.args:
            print(f"{indent}expr args:")
            for arg in self.args:
                arg.print(level + 1)
        if self.funcs:
            print(f"{indent}expr funcs:")
            for func in self.funcs:
                func.print(level + 1)


class ExpressionParser:
    # Grammar:

    # expr      := sub arg* func*
    # arg       := ':' sub
    # func      := '#' sub arg*
    # sub       := ws '[' expr ']' ws  |  literal
    # literal   := ( escaped | [^#:\[\]\\}] )*
    # escaped   := '\' [#:\[\]\\}n]
    # ws        := [ \t]*

    STOP_PATTERN    = re.compile(r"[:#\[\]\\]")
    REPLACE_ESCAPED = re.compile(r"\\([:#\[\]}n])")

    def __init__(self, text: str):
        self.text = text
        self.pos = 0

        self._stopsIter = self.STOP_PATTERN.finditer(text)

    @staticmethod
    def parse(text: str) -> Expr:
        parser = ExpressionParser(text)
        expr, prefix = parser._readExpr()

        if prefix:
            raise ValueError(f"Unexpected suffix: {prefix!r}")

        return expr


    def _readExpr(self) -> tuple[Expr, str]:
        sub, prefix = self._readSub()

        args: list[Sub] = []
        while prefix == ":":
            arg, prefix = self._readSub()
            args.append(arg)

        funcs: list[Func] = []
        while prefix == "#":
            func, prefix = self._readFunc()
            funcs.append(func)

        return Expr(sub, args, funcs), prefix

    def _readFunc(self) -> tuple[Func, str]:
        sub, prefix = self._readSub()

        args = []
        while prefix == ":":
            argSub, prefix = self._readSub()
            args.append(argSub)

        return Func(sub, args), prefix

    def _readSub(self) -> tuple[Sub, str]:
        text, prefix = self._readNext()
        if prefix != "[":
            # Prefix may be empty when end of text was reached
            return Sub(literal=text), prefix

        # Parse sub expression:
        # Check whitespace before sub expression
        if len(text) > 0 and not text.isspace():
            raise ValueError(f"Unexpected '[' after text: {text!r}")

        expr, prefix = self._readExpr()
        if prefix != "]":
            raise ValueError("Unclosed sub expression: Expected ']'")

        # Read rest of whitespace until next stop char
        text, prefix = self._readNext()
        if len(text) > 0 and not text.isspace():
            raise ValueError(f"Unexpected text after ']': {text!r}")

        return Sub(expr=expr), prefix


    def _readNext(self) -> tuple[str, str]:
        escapePos = -1

        try:
            # Get next stop char, but skip escaped
            while True:
                stopMatch = next(self._stopsIter)
                suffix = stopMatch.group()

                if stopMatch.start() != escapePos:
                    if suffix == "\\":
                        escapePos = stopMatch.end()
                    else:
                        break

            text = self.text[self.pos : stopMatch.start()]
            self.pos = stopMatch.end()

        except StopIteration:
            suffix = ""
            text = self.text[self.pos : ]
            self.pos = len(self.text)

        # If any '\' exists in text
        if escapePos > 0:
            text = self.REPLACE_ESCAPED.sub(self._replaceEscaped, text)

        # The suffix (stop char) becomes the next prefix
        return text, suffix

    @staticmethod
    def _replaceEscaped(match: re.Match) -> str:
        char = match.group(1)
        return "\n" if char == "n" else char



class VariableHighlighter:
    class FormatRanges:
        def __init__(self, textEdit: QtWidgets.QPlainTextEdit):
            self.textEdit = textEdit
            self.doc = textEdit.document()
            self.ranges: dict[int, list[QtGui.QTextLayout.FormatRange]] = defaultdict(list)

        def setFormatRange(self, start: int, end: int, format):
            startBlock = self.doc.findBlock(start)
            endBlock   = self.doc.findBlock(end)
            for i in range(startBlock.blockNumber(), endBlock.blockNumber()+1):
                block = self.doc.findBlockByNumber(i)
                formatRange = QtGui.QTextLayout.FormatRange()
                formatRange.format = format
                formatRange.start  = max(start - block.position(), 0)
                formatRange.length = min(end - block.position(), block.length()) - formatRange.start
                self.ranges[i].append(formatRange)

        def apply(self):
            for i in range(self.doc.blockCount()):
                layout = self.doc.findBlockByNumber(i).layout()
                if ranges := self.ranges.get(i):
                    layout.setFormats(ranges)
                else:
                    layout.clearFormats()


    def __init__(self):
        self.formats = ColorCharFormats()

    def highlight(self, source: QtWidgets.QPlainTextEdit, target: QtWidgets.QPlainTextEdit, positions, disabled=False) -> None:
        sourceRanges = self.FormatRanges(source)
        targetRanges = self.FormatRanges(target)

        varIndex = 0
        for srcStart, srcEnd, targetStart, targetEnd in positions:
            format = self.formats.getFormat(varIndex)
            varIndex += 1

            if disabled:
                format = self.formats.toDisabledFormat(format)

            boldFormat = QtGui.QTextCharFormat(format)
            ColorCharFormats.setBoldFormat(boldFormat)

            sourceRanges.setFormatRange(srcStart, srcEnd, boldFormat)
            targetRanges.setFormatRange(targetStart, targetEnd, format)

        sourceRanges.apply()
        targetRanges.apply()



class TemplateRulesProcessor:
    class CacheEntry(NamedTuple):
        rulesProcessor: 'CaptionRulesProcessor'
        modTime: float


    CACHED_PROCESSORS: dict[str, CacheEntry] = {}


    @classmethod
    def getProcessor(cls, presetPath: str) -> 'CaptionRulesProcessor | None':
        if not presetPath.endswith(".json"):
            presetPath += ".json"

        presetPath = os.path.join(Config.pathExport, presetPath)
        presetPath = os.path.abspath(presetPath)

        try:
            modTime = os.path.getmtime(presetPath)
        except OSError:
            print(f"Template Parser: Failed to load rules preset from '{presetPath}'")
            cls.CACHED_PROCESSORS.pop(presetPath, None)
            return None

        cacheEntry = cls.CACHED_PROCESSORS.get(presetPath)
        if cacheEntry is None or cacheEntry.modTime != modTime:
            print(f"Template Parser: Reloading rules preset from '{presetPath}'")
            rulesProcessor = cls._createProcessor(presetPath)
            cls.CACHED_PROCESSORS[presetPath] = cacheEntry = cls.CacheEntry(rulesProcessor, modTime)

        return cacheEntry.rulesProcessor

    @classmethod
    def _createProcessor(cls, presetPath: str) -> 'CaptionRulesProcessor':
        from caption.caption_filter import CaptionRulesProcessor
        from caption.caption_preset import CaptionPreset
        from caption.caption_conditionals import ConditionalFilterRule
        from caption.caption_wildcard import expandWildcards

        preset = CaptionPreset()
        preset.loadFrom(presetPath)

        def groupGenerator():
            for group in preset.groups:
                groupTags = [
                    tag
                    for origTag in group.captions
                    for tag in expandWildcards(origTag, preset.wildcards)
                ]
                yield (groupTags, group.exclusivity, group.combineTags)

        condRulesGenerator = (ConditionalFilterRule.fromPreset(presetCond) for presetCond in preset.conditionals)

        rulesProcessor = CaptionRulesProcessor(
            preset.separator,
            preset.removeDuplicates,
            preset.removeImplications,
            preset.sortCaptions,
            preset.sortNonGroupCaptions,
            preset.whitelistGroups
        )

        rulesProcessor.setPrefixSuffix(preset.prefix, preset.suffix, preset.prefixSeparator, preset.suffixSeparator)
        rulesProcessor.setSearchReplacePairs(preset.searchReplace)
        rulesProcessor.setBannedCaptions(preset.banned)
        rulesProcessor.setCaptionGroups(groupGenerator())
        rulesProcessor.setConditionalRules(condRulesGenerator)
        return rulesProcessor
