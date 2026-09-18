import random, re, traceback
from functools import wraps


def rnd01():
    return random.uniform(0.0, 1.0)


def stripCountPadding(text: str) -> tuple[str, int, int]:
    textStrip = text.lstrip()
    padLeft = len(text) - len(textStrip)

    textStrip = textStrip.rstrip()
    padRight = len(text) - padLeft - len(textStrip)

    return textStrip, padLeft, padRight


def formatTime(timeMs: float, addMilliseconds: bool = False) -> str:
    timeMs   = int(timeMs)
    s, ms    = divmod(timeMs, 1000)
    hours, s = divmod(s, 3600)
    minutes, seconds = divmod(s, 60)

    text = f"{minutes:02}:{seconds:02}.{ms:03}" if addMilliseconds else f"{minutes:02}:{seconds:02}"
    if hours > 0:
        text = f"{hours:02}:{text}"

    return text


def returnOnException(default=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except:
                traceback.print_exc()
                return default

        return wrapper

    return decorator



class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]



class CaptionSplitter:
    def __init__(self, chars: str = ",.:;\n", strings: list[str] = []):
        self.sepChars = chars.replace("\\n", "\n")
        self.sepStrings = strings

        if self.sepChars:
            self.sep = self.sepChars[0]
            self.trans = str.maketrans({
                char: self.sep for char in self.sepChars[1:]
            })
        else:
            self.sep = ""
            self.trans = None

    def split(self, caption: str) -> list[str]:
        if self.trans is None:
            capSplit = [caption]
        else:
            capSplit = caption.translate(self.trans).split(self.sep)

        for sepString in self.sepStrings:
            capSplit = [
                splitPart
                for cap in capSplit
                for splitPart in cap.split(sepString)
            ]

        return [cap for c in capSplit if (cap := c.strip())]

    # def splitReturnSeparators(self, caption: str) -> list[tuple[str, str]]:
    #     raise NotImplementedError



class PromptWeights:
    # Weight pattern: optional whitespace, optional sign, decimal number, optional whitespace.
    # Uses fullmatch() so it must match the whole suffix.
    _WEIGHT = re.compile(r'\s*[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\s*')

    _PARENS = re.compile(r'[()]')

    @classmethod
    def stripWeights(cls, prompt: str) -> str:
        isWeight = cls._WEIGHT.fullmatch

        out: list[str]          = []  # Top-level target
        target: list[str]       = out
        stack: list[list[str]]  = []
        start: int              = 0

        for match in cls._PARENS.finditer(prompt):
            pos = match.start()

            # Append normal text since the previous parenthesis
            if pos > start:
                target.append(prompt[start:pos])

            # New frame
            if prompt[pos] == '(':
                target = []
                stack.append(target)

            # Close frame: Found ')'
            elif stack:
                parts = stack.pop()
                target = stack[-1] if stack else out

                chunk = ''.join(parts)

                # Strip trailing :weight if present
                end = chunk.rfind(':')
                if 0 <= end < len(chunk)-1 and isWeight(chunk, end+1):
                    chunk = chunk[:end].rstrip()

                if chunk:
                    target.append(chunk)

            # Unmatched ')' is plain text
            else:
                target.append(')')

            start = pos + 1

        # No parentheses at all
        if start == 0:
            return prompt

        # Append remaining tail text
        if start < len(prompt):
            target.append(prompt[start:])

        # Any remaining '(' was unmatched. Keep it literally.
        # Extend instead of joining/prepending to reduce allocations.
        while stack:
            parts = stack.pop()
            target = stack[-1] if stack else out
            target.append('(')
            target.extend(parts)

        return ''.join(out)
