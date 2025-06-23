# Register PIL formats first
try: import pillow_jxl
except: pass

from PIL import Image
PIL_READ_EXTENSIONS = set(ext for ext, format in Image.registered_extensions().items() if format in Image.OPEN)


PIL_CONVERT_MODES = {
    "1":     "L",
    "P":     "RGBA",  # There are P images with alpha
    "PA":    "RGBA",
    "CMYK":  "RGB",
    "YCbCr": "RGB",
    "LAB":   "RGB",
    "HSV":   "RGB",
    "I":     "RGBA",
    "F":     "RGBA",
    "RGBX":  "RGB",
    "RGBa":  "RGBA",
    "La":    "LA"
}

PIL_CONVERT_MODES_NOGREY = {
    "1":  "RGB",
    "L":  "RGB",
    "LA": "RGBA",
    "La": "RGBA"
}

PIL_CONVERT_MODES_NOALPHA = {
    "RGBA": "RGB",
    "P":    "RGB",
    "PA":   "RGB",
    "LA":   "L",
    "La":   "L"
}


def _getConversionMode(mode: str, forceRGB=False, allowGreyscale=True, allowAlpha=True) -> str | None:
    if forceRGB and mode != "RGB":
        return "RGB"

    origMode = mode
    mode = PIL_CONVERT_MODES.get(mode, mode)
    if not allowGreyscale:
        mode = PIL_CONVERT_MODES_NOGREY.get(mode, mode)
    if not allowAlpha:
        mode = PIL_CONVERT_MODES_NOALPHA.get(mode, mode)
    return mode if mode != origMode else None


def _readSizePIL(imgPath: str) -> tuple[int, int]:
    with Image.open(imgPath) as img:
        return img.size



# Qt/PySide6 is optional on headless inference servers
try:
    from PySide6.QtGui import QImageReader, QImage
    from PySide6.QtCore import QSize
    from PIL import ImageQt

    QT_READ_EXTENSIONS = set(f".{format.data().decode('utf-8').lower()}" for format in QImageReader.supportedImageFormats())

    def readSize(imgPath: str) -> tuple[int, int]:
        try:
            reader = QImageReader(imgPath)
            w, h = reader.size().toTuple()
            if w < 0:
                w, h = _readSizePIL(imgPath)
            return (w, h)
        except:
            return (-1, -1)

    def loadQImagePIL(imgPath: str) -> ImageQt.ImageQt:
        with Image.open(imgPath) as img:
            return ImageQt.ImageQt(img)

    def thumbnailQImage(imgPath: str, maxWidth: int) -> tuple[QImage | ImageQt.ImageQt, tuple[int, int]]:
        reader = QImageReader(imgPath)
        w, h = reader.size().toTuple()

        if w >= 0:
            targetWidth = min(maxWidth, w)
            targetHeight = round(targetWidth * (h / w))
            reader.setScaledSize(QSize(targetWidth, targetHeight))
            reader.setQuality(100)
            qimage = reader.read()
        else:
            with Image.open(imgPath) as img:
                w, h = img.size
                img.thumbnail((maxWidth, -1), resample=Image.Resampling.BOX)
                qimage = ImageQt.ImageQt(img)

        return qimage, (w, h)

except:
    QT_READ_EXTENSIONS = set[str]()

    readSize = _readSizePIL


READ_EXTENSIONS = frozenset(PIL_READ_EXTENSIONS | QT_READ_EXTENSIONS)


# FIXME: RGB images with 3 channels are loaded in RGBA mode

def loadImagePIL(source, forceRGB=False, allowGreyscale=True, allowAlpha=True):
    img = Image.open(source)
    if convertMode := _getConversionMode(img.mode, forceRGB, allowGreyscale, allowAlpha):
        img = img.convert(convertMode)
    return img


# Always load with PIL: OpenCV has problems with loading certain modes (like P)

def loadMatBGR(imgPath: str, rgb=False, forceRGB=False, allowGreyscale=True, allowAlpha=True):
    import numpy as np
    with loadImagePIL(imgPath, forceRGB, allowGreyscale, allowAlpha) as img:
        mat = np.array(img)

    if not rgb:
        mat[..., :3] = mat[..., 2::-1] # Convert RGB(A) -> BGR(A)
    return mat

def decodeMatBGR(data: bytes | bytearray, rgb=False, forceRGB=False, allowGreyscale=True, allowAlpha=True):
    import numpy as np
    from io import BytesIO
    with loadImagePIL(BytesIO(data), forceRGB, allowGreyscale, allowAlpha) as img:
        mat = np.array(img)

    if not rgb:
        mat[..., :3] = mat[..., 2::-1] # Convert RGB(A) -> BGR(A)
    return mat
