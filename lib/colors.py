from . import util, qtlib


BUBBLE_BLACK_H, BUBBLE_BLACK_S, BUBBLE_BLACK_V = util.get_hsv(qtlib.COLOR_BUBBLE_BLACK)

def mixBubbleColor(destColor: str, mixS: float, mixV: float) -> str:
    destH, destS, destV = util.get_hsv(destColor)
    s = BUBBLE_BLACK_S + (destS - BUBBLE_BLACK_S) * mixS
    v = BUBBLE_BLACK_V + (destV - BUBBLE_BLACK_V) * mixV
    return util.hsv_to_rgb(destH, s, v)
