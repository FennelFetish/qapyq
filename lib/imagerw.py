# Register PIL formats first
try: import pillow_jxl
except: pass

from io import BytesIO
from PIL import Image, ImageCms, ImageOps
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

def _readImagePIL(source) -> Image.Image:
    with Image.open(source) as img:
        normalizeColorSpacePIL(img)
        ImageOps.exif_transpose(img, in_place=True)
        return img


__srgbProfile = None
def _getSrgbProfile():
    global __srgbProfile
    if __srgbProfile is None:
        __srgbProfile = ImageCms.createProfile('sRGB')
    return __srgbProfile

def normalizeColorSpacePIL(img: Image.Image):
    try:
        if iccProfile := img.info.get('icc_profile'):
            profile = ImageCms.ImageCmsProfile(BytesIO(iccProfile))
            profileName = ImageCms.getProfileName(profile)
            if "srgb" not in profileName.lower():
                ImageCms.profileToProfile(img, profile, _getSrgbProfile(), inPlace=True)
    except Exception as ex:
        print(f"WARNING: Error while verifying image color profile: {ex} ({type(ex).__name__})")



# Qt/PySide6 is optional on headless inference servers
try:
    from PySide6.QtGui import QImageReader, QImage, QColorSpace
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

    def loadQImage(imgPath: str) -> QImage | ImageQt.ImageQt:
        reader = QImageReader(imgPath)
        reader.setAutoTransform(True)

        image = reader.read()
        if image.isNull():
            try:
                image = ImageQt.ImageQt(_readImagePIL(imgPath))
            except:
                pass
        else:
            normalizeColorSpace(image)

        return image

    def thumbnailQImage(imgPath: str, maxWidth: int) -> tuple[QImage | ImageQt.ImageQt, tuple[int, int]]:
        reader = QImageReader(imgPath)
        w, h = reader.size().toTuple()

        if w >= 0:
            targetWidth = max(maxWidth, round(maxWidth * (w/h))) # Account for possible EXIF rotation
            targetWidth = min(targetWidth, w)
            targetHeight = round(targetWidth * (h/w))
            reader.setScaledSize(QSize(targetWidth, targetHeight))
            reader.setAutoTransform(True)
            reader.setQuality(100)
            qimage = reader.read()
            normalizeColorSpace(qimage)
        else:
            with Image.open(imgPath) as img:
                w, h = img.size
                targetWidth = max(maxWidth, round(maxWidth * (w/h))) # Account for possible EXIF rotation
                targetWidth = min(targetWidth, w)
                img.thumbnail((targetWidth, -1), resample=Image.Resampling.BOX)
                normalizeColorSpacePIL(img)
                ImageOps.exif_transpose(img, in_place=True)
                qimage = ImageQt.ImageQt(img)

        # Swap original size when rotated
        newW, newH = qimage.size().toTuple()
        if (w > h) != (newW > newH):
            w, h = h, w
        elif newW > maxWidth * 1.25:
            qimage = qimage.scaledToWidth(maxWidth) # TransformationMode.FastTransformation by default

        return qimage, (w, h)

    def normalizeColorSpace(qimage: QImage):
        colorSpace = qimage.colorSpace()
        if not colorSpace.isValid():
            qimage.setColorSpace(QColorSpace.NamedColorSpace.SRgb)
        elif colorSpace != QColorSpace.NamedColorSpace.SRgb:
            qimage.convertToColorSpace(QColorSpace.NamedColorSpace.SRgb)

except:
    QT_READ_EXTENSIONS = set[str]()

    readSize = _readSizePIL


READ_EXTENSIONS = frozenset(PIL_READ_EXTENSIONS | QT_READ_EXTENSIONS)


# FIXME: Some RGB images with 3 channels are loaded in RGBA mode

def loadImagePIL(source, forceRGB=False, allowGreyscale=True, allowAlpha=True):
    img = _readImagePIL(source)
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
    with loadImagePIL(BytesIO(data), forceRGB, allowGreyscale, allowAlpha) as img:
        mat = np.array(img)

    if not rgb:
        mat[..., :3] = mat[..., 2::-1] # Convert RGB(A) -> BGR(A)
    return mat
