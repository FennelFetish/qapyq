import random
import colorsys
import re


# def randomColor(s=0.5, v=0.5):
#     return hsv_to_rgb(rnd01(), s, v)

def hsv_to_rgb(h: float, s: float, v: float) -> str:
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    r, g, b = int(r*255), int(g*255), int(b*255)
    return '#{:02x}{:02x}{:02x}'.format(r, g, b)

def get_hsv(colorHex: str) -> tuple[float, float, float]:
    colorHex = colorHex.lstrip('#')
    if len(colorHex) == 3:
        colorHex = ''.join(c*2 for c in colorHex)
    elif len(colorHex) != 6:
        return (0.0, 0.0, 0.0)

    r, g, b = int(colorHex[0:2], 16), int(colorHex[2:4], 16), int(colorHex[4:6], 16)
    return colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)

def get_hue(colorHex: str) -> float:
    h, s, v = get_hsv(colorHex)
    return h


def rnd01():
    return random.uniform(0.0, 1.0)

# def rndMax(max: float):
#     return random.uniform(0.0, max)

# def rnd(min: float, max: float):
#     return random.uniform(min, max)


validColorPattern = re.compile(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$')
def isValidColor(color):
    return validColorPattern.match(color) is not None


class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
