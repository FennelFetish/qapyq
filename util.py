import random
import colorsys
import re


def randomColor(s=0.5, v=0.5):
    return hsv_to_rgb(rnd01(), s, v)

def hsv_to_rgb(h: float, s: float, v: float):
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    r, g, b = int(r*255), int(g*255), int(b*255)
    return '#{:02x}{:02x}{:02x}'.format(r, g, b)

def rnd01():
    return random.uniform(0.0, 1.0)

def rndMax(max: float):
    return random.uniform(0.0, max)

def rnd(min: float, max: float):
    return random.uniform(min, max)


def isValidColor(color):
    colorPattern = re.compile(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$')
    return colorPattern.match(color) is not None


# TODO: Don't return caption names starting with '?'
# TODO: Start new message history with '===name==='
def parsePrompts(text: str, defaultName="caption") -> dict:
    if not defaultName:
        defaultName = "caption"

    namePattern = r"^---(.*?)---$"
    currentName = defaultName
    currentPrompt = []
    prompts = {}
    
    lines = text.splitlines()
    for line in lines:
        line = line.strip()

        if line.startswith("---"):
            if currentPrompt:
                prompts[currentName] = "\n".join(currentPrompt)
                currentPrompt.clear()

            nameMatch = re.match(namePattern, line)
            newName = nameMatch.group(1).strip() if nameMatch else defaultName
            currentName = newName

            appendNr = 1
            while currentName in prompts:
                currentName = f"{newName}_{appendNr}"
                appendNr += 1
        else:
            currentPrompt.append(line)

    prompts[currentName] = "\n".join(currentPrompt)
    return prompts


class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
