import random, traceback
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
