import random
import colorsys
import re


def randomColor(s=0.5, v=0.5):
    return hsv_to_rgb(rnd01(), s, v)

def hsv_to_rgb(h: float, s: float, v: float):
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    r, g, b = int(r*255), int(g*255), int(b*255)
    return '#{:02x}{:02x}{:02x}'.format(r, g, b)

def get_hue(colorHex: str) -> float:
    if len(colorHex) == 7:
        r, g, b = int(colorHex[1:3], 16), int(colorHex[3:5], 16), int(colorHex[5:7], 16)
    elif len(colorHex) == 4:
        r, g, b = int(colorHex[1], 16), int(colorHex[2], 16), int(colorHex[3], 16)
    else:
        r, g, b = 0, 0, 0
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h


def rnd01():
    return random.uniform(0.0, 1.0)

def rndMax(max: float):
    return random.uniform(0.0, max)

def rnd(min: float, max: float):
    return random.uniform(min, max)


validColorPattern = re.compile(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$')
def isValidColor(color):
    return validColorPattern.match(color) is not None


class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
