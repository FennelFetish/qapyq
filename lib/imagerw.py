# Register PIL formats first
try: import pillow_jxl
except: pass

from config import Config

from io import BytesIO
from PIL import Image, ImageCms, ImageOps, ExifTags
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
    if forceRGB:
        return "RGB" if mode != "RGB" else None

    origMode = mode
    mode = PIL_CONVERT_MODES.get(mode, mode)
    if not allowGreyscale:
        mode = PIL_CONVERT_MODES_NOGREY.get(mode, mode)
    if not allowAlpha:
        mode = PIL_CONVERT_MODES_NOALPHA.get(mode, mode)
    return mode if mode != origMode else None


PIL_SWAP_SIZE_TRANSFORMATIONS = {
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}

def _exifSwapSizePIL(img: Image.Image) -> bool:
    # There can be exif data that wasn't loaded yet.
    exif = getattr(img, "_exif", None)
    if not exif:
        exif = img.getexif() # Slow
    if exif:
        orientation = exif.get(ExifTags.Base.Orientation, 1)
        return orientation in PIL_SWAP_SIZE_TRANSFORMATIONS
    return False


def _readSizePIL(imgPath: str) -> tuple[int, int]:
    with Image.open(imgPath) as img:
        size = img.size
        if Config.exifTransform and _exifSwapSizePIL(img):
            size = (size[1], size[0])
        return size

def _readImagePIL(source) -> Image.Image:
    with Image.open(source) as img:
        img.load()
        normalizeColorSpacePIL(img)
        if Config.exifTransform:
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
            profileName = ImageCms.getProfileName(profile).lower()
            if ("srgb" not in profileName) or ("linear" in profileName):
                ImageCms.profileToProfile(img, profile, _getSrgbProfile(), inPlace=True)
    except Exception as ex:
        print(f"WARNING: Error while verifying image color profile: {ex} ({type(ex).__name__})")



# Qt/PySide6 is optional on headless inference servers
try:
    from PySide6.QtGui import QImageReader, QImage, QColorSpace, QImageIOHandler
    from PySide6.QtCore import QSize
    from PIL import ImageQt

    QT_READ_EXTENSIONS = set(f".{format.data().decode('utf-8').lower()}" for format in QImageReader.supportedImageFormats())


    QT_SWAP_SIZE_TRANSFORMATIONS = (
        QImageIOHandler.Transformation.TransformationRotate90,
        QImageIOHandler.Transformation.TransformationMirrorAndRotate90,
        QImageIOHandler.Transformation.TransformationFlipAndRotate90,
        QImageIOHandler.Transformation.TransformationRotate270
    )

    def _exifSwapSizeQt(reader: QImageReader) -> bool:
        return reader.transformation() in QT_SWAP_SIZE_TRANSFORMATIONS


    def readSize(imgPath: str) -> tuple[int, int]:
        try:
            reader = QImageReader(imgPath)
            w, h = reader.size().toTuple()

            if w < 0:
                w, h = _readSizePIL(imgPath)
            elif Config.exifTransform and _exifSwapSizeQt(reader):
                w, h = h, w

            return (w, h)
        except:
            return (-1, -1)

    def loadQImage(imgPath: str) -> QImage | ImageQt.ImageQt:
        reader = QImageReader(imgPath)
        reader.setAutoTransform(Config.exifTransform)

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
            if Config.exifTransform and _exifSwapSizeQt(reader):
                targetHeight = min(maxWidth, h)
                targetWidth = round(targetHeight * (w/h))
                w, h = h, w
            else:
                targetWidth = min(maxWidth, w)
                targetHeight = round(targetWidth * (h/w))

            reader.setScaledSize(QSize(targetWidth, targetHeight))
            reader.setAutoTransform(Config.exifTransform)
            reader.setQuality(100)
            qimage = reader.read()
            normalizeColorSpace(qimage)

        else:
            with Image.open(imgPath) as img:
                w, h = img.size
                if Config.exifTransform and _exifSwapSizePIL(img):
                    targetHeight = min(maxWidth, h)
                    targetWidth = round(targetHeight * (w/h))
                    w, h = h, w
                else:
                    targetWidth = min(maxWidth, w)

                img.thumbnail((targetWidth, -1), resample=Image.Resampling.BOX)
                normalizeColorSpacePIL(img)
                if Config.exifTransform:
                    ImageOps.exif_transpose(img, in_place=True)
                qimage = ImageQt.ImageQt(img)

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
