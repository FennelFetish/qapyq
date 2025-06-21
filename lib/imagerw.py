# Register PIL formats first
try: import pillow_jxl
except: pass

from PIL import Image
PIL_READ_EXTENSIONS = set(ext for ext, format in Image.registered_extensions().items() if format in Image.OPEN)


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



def loadImagePIL(source):
    return Image.open(source)


def loadMatBGR(imgPath: str):
    import cv2 as cv
    mat = cv.imread(imgPath, cv.IMREAD_ANYCOLOR)
    if mat is None:
        import numpy as np
        with Image.open(imgPath) as img:
            mat = np.array(img)
        mat[..., :3] = mat[..., 2::-1] # Convert RGB(A) -> BGR(A)

    return mat

def decodeMatBGR(data: bytes | bytearray):
    import numpy as np
    from io import BytesIO
    with Image.open(BytesIO(data)) as img:
        mat = np.array(img)
    mat[..., :3] = mat[..., 2::-1] # Convert RGB(A) -> BGR(A)
    return mat
