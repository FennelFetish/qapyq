import colorsys, re
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette, QTextCharFormat
from lib import util


DARK_THEME = True

HUE_OFFSET = 0.3819444  # 1.0 - inverted golden ratio = ~137.5°


# Default colors for dark theme
RED   = "#FF1616"
GREEN = "#30FF30"

BUBBLE_BG       = "#161616"
BUBBLE_BG_HOVER = "#808070"
BUBBLE_BG_BAN   = "#454545"

BUBBLE_TEXT          = "#FFF"
BUBBLE_TEXT_DISABLED = "#777"

BUBBLE_MIX_S = 0.35
BUBBLE_MIX_V = 0.17

BUBBLE_BG_H, BUBBLE_BG_S, BUBBLE_BG_V = 0, 0, 0

GROUP_COLOR_S = 0.55
GROUP_COLOR_V = 0.4

TEXT_HIGHLIGHT_V = 1.0

FOCUS     = "#901313"
FOCUS_BAN = "#686868"


def initColors(colorScheme: Qt.ColorScheme):
    from PySide6.QtWidgets import QApplication
    v = QApplication.palette().color(QPalette.ColorRole.Text).valueF()
    global TEXT_HIGHLIGHT_V
    TEXT_HIGHLIGHT_V = max(v, 0.65)

    if colorScheme == Qt.ColorScheme.Light:
        global DARK_THEME
        DARK_THEME = False

        global RED, GREEN
        RED   = "#FA0000"
        GREEN = "#08AA08"

        global BUBBLE_BG, BUBBLE_BG_HOVER, BUBBLE_BG_BAN, BUBBLE_TEXT
        BUBBLE_BG       = "#D0D0D0"
        BUBBLE_BG_HOVER = "#FFFFF0"
        BUBBLE_BG_BAN   = "#A0A0A0"
        BUBBLE_TEXT     = "#000"

        global BUBBLE_MIX_S, BUBBLE_MIX_V
        BUBBLE_MIX_S = 0.04
        BUBBLE_MIX_V = 0.02

        global GROUP_COLOR_S, GROUP_COLOR_V
        GROUP_COLOR_S = 0.4
        GROUP_COLOR_V = 0.82

        global FOCUS, FOCUS_BAN
        FOCUS     = "#E04444"
        FOCUS_BAN = "#909090"

        global bubbleMuteColor
        bubbleMuteColor = __bubbleMuteLight

    else:
        TEXT_HIGHLIGHT_V **= 0.5  # Brighter highlighting

    global BUBBLE_BG_H, BUBBLE_BG_S, BUBBLE_BG_V
    BUBBLE_BG_H, BUBBLE_BG_S, BUBBLE_BG_V = toHsv(BUBBLE_BG)



def mixBubbleColor(destColor: str, mixS: float, mixV: float) -> str:
    destH, destS, destV = toHsv(destColor)
    s = BUBBLE_BG_S + (destS - BUBBLE_BG_S) * mixS
    v = BUBBLE_BG_V + (destV - BUBBLE_BG_V) * mixV
    return hsvToRgb(destH, s, v)


def __bubbleMuteDark(color: str) -> str:
    h, s, v = toHsv(color)
    s *= 0.7
    v = min(max(v*1.8, 0.7), 1.0)
    return hsvToRgb(h, s, v)

def __bubbleMuteLight(color: str) -> str:
    h, s, v = toHsv(color)
    s = min(s*1.5, 1.0)
    v *= 0.52
    return hsvToRgb(h, s, v)

bubbleMuteColor = __bubbleMuteDark


def bubbleStyle(color: str, borderColor="") -> str:
    borderColor = borderColor or BUBBLE_BG
    return f"color: {BUBBLE_TEXT}; background-color: {color}; border: 1px solid {borderColor}; border-radius: 8px"

def bubbleStyleNoBorder(color: str, textColor="") -> str:
    textColor = textColor or BUBBLE_TEXT
    return f"color: {textColor}; background-color: {color}; border: 0px"

def bubbleStylePad(color: str, padding=2, borderColor="") -> str:
    return bubbleStyle(color, borderColor) + f"; padding: {padding}px"

def bubbleClass(className: str, color: str, borderColor="") -> str:
    style = bubbleStyle(color, borderColor)
    return f".{className}{{{style}}}"

def bubbleClassAux(className: str, auxClassName: str, colorBg: str, borderColor="", textColor="", bold=True) -> str:
    borderColor = borderColor or BUBBLE_BG
    textColor   = textColor or BUBBLE_TEXT
    fontWeight  = "font-weight: 600" if bold else ""
    return f".{className}{{background-color: {colorBg}; border: 1px solid {borderColor}; border-radius: 8px}}" \
           f".{auxClassName}{{color: {textColor}; {fontWeight}}}"

def removeButtonStyle(className: str) -> str:
    if DARK_THEME:
        textColor, bgColor, borderColor = "#D54040", "#1B1B1B", "#402020"
    else:
        textColor, bgColor, borderColor = "#E01010", "#DBDBDB", "#908080"

    return f".{className}{{color: {textColor}; background-color: {bgColor}; " \
           f"border: 1px solid {borderColor}; border-radius: 4px; padding: 0px 0px 1px 0px}}"



def getHighlightColor(colorHex: str) -> QColor:
    h, s, v = toHsv(colorHex)

    # Try to keep saturation at around 0.4 for bright text (dark themes)
    # and around 0.8 for dark text (bright themes), but allow extreme values.
    # Smooth curve with start/end at 0 and 1, with plateau in the middle.
    # https://www.desmos.com/calculator/y4dgc8uz0b
    plateauLower = 1.32 if DARK_THEME else 0.32
    plateauWidth = 1.6
    plateau = ((2*s - 1) ** 5) * 0.5 + 0.5
    smoothstep = 3*s*s - 2*s*s*s
    sMix = (2*abs(s-0.5)) ** plateauWidth
    s = (1-sMix)*plateau + sMix*smoothstep
    s = s ** plateauLower

    # Try to keep 'v' at 'vPalette', but mix towards 'v' for extreme values.
    # Smooth curve goes through (0,1), (vPalette,0), (1,1), sample at 'v'.
    # https://www.desmos.com/calculator/obmyhuqy37
    vPalette = TEXT_HIGHLIGHT_V
    vMix = (vPalette-v)/vPalette if v<vPalette else (v-vPalette)/max(1-vPalette, 0.001)
    vMix = vMix ** 8.0
    v = (1.0-vMix)*vPalette + vMix*v

    return QColor.fromHsvF(h, s, v)



class ColorCharFormats:
    def __init__(self):
        self.defaultFormat = QTextCharFormat()

        if DARK_THEME:
            self._sv = (0.4, TEXT_HIGHLIGHT_V)
            self._svDisabled = (0.25, 0.5)
        else:
            self._sv = (0.85, TEXT_HIGHLIGHT_V)
            self._svDisabled = (0.18, 0.75)

        self._formats = []
        self._nextHue = util.rnd01()

    def getFormat(self, index: int) -> QTextCharFormat:
        while index >= len(self._formats):
            color = hsvToRgb(self._nextHue, self._sv[0], self._sv[1])
            self._nextHue += HUE_OFFSET

            charFormat = QTextCharFormat()
            charFormat.setForeground(QColor(color))
            self._formats.append(charFormat)

        return self._formats[index]

    def addFormat(self, format: QTextCharFormat) -> None:
        self._formats.append(format)

    def toDisabledFormat(self, charFormat: QTextCharFormat) -> QTextCharFormat:
        color = charFormat.foreground().color()
        h, s, v, a = color.getHsvF()
        s, v = self._svDisabled
        color.setHsvF(h, s, v, a)

        charFormat = QTextCharFormat()
        charFormat.setForeground(color)
        return charFormat

    @staticmethod
    def setBoldFormat(charFormat: QTextCharFormat, bold=True) -> None:
        charFormat.setFontWeight(700 if bold else 400)



def hsvToRgb(h: float, s: float, v: float) -> str:
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    r, g, b = int(r*255), int(g*255), int(b*255)
    return '#{:02x}{:02x}{:02x}'.format(r, g, b)

def toHsv(colorHex: str) -> tuple[float, float, float]:
    colorHex = colorHex.lstrip('#')
    if len(colorHex) == 3:
        colorHex = ''.join(c*2 for c in colorHex)
    elif len(colorHex) != 6:
        return (0.0, 0.0, 0.0)

    r, g, b = int(colorHex[0:2], 16), int(colorHex[2:4], 16), int(colorHex[4:6], 16)
    return colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)

def getHue(colorHex: str) -> float:
    h, s, v = toHsv(colorHex)
    return h


def htmlRed(text: str) -> str:
    return f"<font color='{RED}'>{text}</font>"


__validColorPattern = re.compile(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$')
def isValidColor(color):
    return __validColorPattern.match(color) is not None
