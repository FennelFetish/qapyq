from enum import Enum, auto # StrEnum available in python >=3.11
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QLinearGradient
from PySide6.QtCore import Qt, QPoint
import os, json, re
import numpy as np
from config import Config
import tools.mask_ops as mask_ops
from lib.qtlib import numpyToQImageMask, qimageToNumpyMask


class MacroOp(Enum):
    @staticmethod
    def _generate_next_value_(name, start, count, last_values):
        return name

    SetLayer        = auto()    # index
    AddLayer        = auto()
    #AddSetLayer     = auto()   # Add and select new layer. Determined while recording.
    DeleteLayer     = auto()    # index
    #RenameLayer     = auto()    # index, name TODO

    Brush           = auto()    # strokes...
    Rectangle       = auto()    # color, x0, y0, x1, y1 (float 0..1)
    FloodFill       = auto()    # color, lowerDiff, upperDiff, x, y
    Clear           = auto()    # color (int)
    Invert          = auto()
    Threshold       = auto()    # color
    Normalize       = auto()    # colorMin, colorMax  # TODO: rename to minColor, maxColor
    Quantize        = auto()    # mode, gridSize
    Morph           = auto()    # mode, radius
    GaussBlur       = auto()    # mode, radius
    BlendLayers     = auto()    # mode, srcLayer

    DetectPad       = auto()    # minColor, maxColor, tolerance, fillColor
    CentroidRect    = auto()    # aspectRatio (float), color

    CondColor       = auto()    # minColor, maxColor (float)
    CondArea        = auto()    # minArea, maxArea (float)
    CondRegions     = auto()    # minRegions, maxRegions (int)

    Macro           = auto()    # name
    Detect          = auto()    # preset, color, threshold
    Segment         = auto()    # preset, color

    #ClearVram       = auto()    # ??


class MacroOpItem:
    OP_KEY = "op"

    def __init__(self, op: MacroOp, args: dict):
        self.op = op
        self.args = args
        self.enabled = True

    def toDict(self):
        data = {self.OP_KEY: self.op.name}
        data.update(self.args)
        return data

    @classmethod
    def fromDict(cls, data: dict):
        opName = data.pop(cls.OP_KEY)
        return MacroOpItem(MacroOp[opName], data)

    def __str__(self) -> str:
        return f"{self.op.name}: {self.args}"



class MacroLoadException(Exception):
    def __init__(self, message: str):
        msg = f"Error while loading macro: {message}"
        super().__init__(msg)

class MacroRunException(Exception):
    def __init__(self, message: str):
        msg = f"Error while running macro: {message}"
        super().__init__(msg)



# https://stackoverflow.com/a/72611442/1442598
def jsonIndentLimit(indent, limit):
    return re.compile(f'\n({indent}){{{limit}}}(({indent})+|(?=(}}|])))')



class MaskingMacro:
    VERSION = "1.0"
    COMPACT_JSON_PATTERN = jsonIndentLimit("    ", 2)

    def __init__(self):
        self.operations: list[MacroOpItem] = list()
        self.recording = False

        self.opFunc = {
            MacroOp.Rectangle:      mask_ops.DrawRectangleMaskOperation.operate,
            MacroOp.Clear:          mask_ops.ClearMaskOperation.operate,
            MacroOp.Invert:         mask_ops.InvertMaskOperation.operate,
            MacroOp.Threshold:      mask_ops.ThresholdMaskOperation.operate,
            MacroOp.Normalize:      mask_ops.NormalizeMaskOperation.operate,
            MacroOp.Quantize:       mask_ops.QuantizeMaskOperation.operate,
            MacroOp.Morph:          mask_ops.MorphologyMaskOperation.operate,
            MacroOp.GaussBlur:      mask_ops.BlurMaskOperation.operate,
            MacroOp.CentroidRect:   mask_ops.CentroidRectMaskOperation.operate,

            MacroOp.CondColor:      mask_ops.ColorConditionMaskOperation.operate,
            MacroOp.CondArea:       mask_ops.AreaConditionMaskOperation.operate,
            MacroOp.CondRegions:    mask_ops.RegionConditionMaskOperation.operate
        }


    def addOperation(self, op: MacroOp, **kwargs) -> MacroOpItem | None:
        if not self.recording:
            return None

        item = MacroOpItem(op, kwargs)
        self.operations.append(item)
        return item

    def clear(self):
        self.operations = list()


    def saveTo(self, path: str):
        operations: list[dict] = []
        for item in self.operations:
            # Ignore operations that were undone through history
            if not item.enabled:
                continue
            # Flatten repeated SetLayer ops
            if item.op == MacroOp.SetLayer and operations and operations[-1][MacroOpItem.OP_KEY] == MacroOp.SetLayer.name:
                operations[-1] = item.toDict()
            else:
                operations.append(item.toDict())

        # TODO: Store summary of used detection/segmentation presets + classes.
        #       On loading, try to find existing presets that use the same model file. (macros can be shared)

        data = dict()
        data["version"] = self.VERSION
        data["operations"] = operations

        jsonStr = json.dumps(data, indent=4)
        jsonStr = self.COMPACT_JSON_PATTERN.sub(" ", jsonStr)
        with open(path, 'w') as file:
            file.writelines(jsonStr)

    def loadFrom(self, path: str):
        if os.path.exists(path):
            with open(path, 'r') as file:
                data = json.load(file)
        else:
            data = dict()

        self.clear()
        operations = data.get("operations", [])
        for opData in operations:
            try:
                self.operations.append( MacroOpItem.fromDict(opData) )
            except KeyError as ex:
                raise MacroLoadException(f"Invalid operation name: {ex}")

    @staticmethod
    def loadMacros():
        basePath = os.path.abspath(Config.pathMaskMacros)
        for root, dirs, files in os.walk(basePath):
            root = os.path.normpath(root)
            for path in (os.path.join(root, f) for f in files if f.endswith(".json")):
                name, ext = os.path.splitext( os.path.relpath(path, basePath) )
                yield (name, path)


    # TODO: Macros that use scratch layers may expect a fixed number of input layers (like 1)
    #       and blend the results from wrong layers when starting with 2 layers.
    def run(self, imgPath: str, layers: list[np.ndarray], currentLayerIndex=0) -> tuple[list[np.ndarray], list[bool]]:
        '''
        Must run in inference thread.
        '''
        layers = list(layers)
        changed = [False] * len(layers)
        shape = layers[0].shape
        layerIndex = currentLayerIndex

        #print("Running macro:")
        for opItem in self.operations:
            args = opItem.args.copy()
            #print(f"  {opItem}")

            match opItem.op:
                case MacroOp.SetLayer:
                    index = int(args["index"])
                    if 0 <= index < len(layers):
                        layerIndex = index
                    else:
                        raise MacroRunException(f"Failed to set active layer to index {index}")

                case MacroOp.AddLayer:
                    layers.append( np.zeros(shape, dtype=np.uint8) )
                    changed.append(True)

                case MacroOp.DeleteLayer:
                    index = int(args["index"])
                    if 0 <= index < len(layers):
                        del layers[index]
                        del changed[index]
                    else:
                        raise MacroRunException(f"Failed to delete layer at index {index}")

                case MacroOp.BlendLayers:
                    layers[layerIndex] = self.opBlendLayers(layers[layerIndex], layers, args)
                    changed[layerIndex] = True

                case _:
                    layers[layerIndex] = self._runOp(layers[layerIndex], imgPath, opItem.op, args)
                    changed[layerIndex] = True

        return (layers, changed)


    def _runOp(self, mat: np.ndarray, imgPath: str, op: MacroOp, args: dict) -> np.ndarray:
        if func := self.opFunc.get(op):
            return func(mat, **args)

        match op:
            case MacroOp.Brush:
                return self.opBrush(mat, args)
            case MacroOp.FloodFill:
                return self.opFloodFill(mat, args)
            case MacroOp.DetectPad:
                return self.opDetectPad(mat, imgPath, args)
            case MacroOp.Detect:
                return self.opDetect(mat, imgPath, args)
            case MacroOp.Segment:
                return self.opSegment(mat, imgPath, args)

        raise MacroRunException(f"Unrecognized operation: {op}")


    @staticmethod
    def opFloodFill(mat: np.ndarray, args: dict) -> np.ndarray:
        h, w = mat.shape
        args["x"] = round(args["x"] * (w-1))
        args["y"] = round(args["y"] * (h-1))
        return mask_ops.FillMaskOperation.operate(mat, **args)

    @staticmethod
    def opBlendLayers(mat: np.ndarray, layers: list[np.ndarray], args: dict) -> np.ndarray:
        srcMat = layers[ int(args.pop("srcLayer")) ]
        return mask_ops.BlendLayersMaskOperation.operate(srcMat, mat, **args)

    @staticmethod
    def opDetectPad(mat: np.ndarray, imgPath: str, args: dict) -> np.ndarray:
        import cv2 as cv
        image = cv.imread(imgPath, cv.IMREAD_UNCHANGED)
        return mask_ops.DetectPadMaskOperation.operate(mat, image, **args)

    def opDetect(self, mat: np.ndarray, imgPath: str, args: dict) -> np.ndarray:
        # TODO: Don't start on every call?
        from infer import Inference
        inferProc = Inference().proc
        inferProc.start()

        preset = args.pop("preset")
        threshold = args.pop("threshold")
        config: dict = Config.inferMaskPresets.get(preset)
        classes = config.get("classes", [])

        boxes = inferProc.maskBoxes(config, classes, imgPath)
        for box in boxes:
            name = box["name"]
            if box["confidence"] < threshold or (classes and name not in classes):
                continue
            mat = mask_ops.DetectMaskOperation.operate(mat, box, **args)

        return mat

    def opSegment(self, mat: np.ndarray, imgPath: str, args: dict) -> np.ndarray:
        # TODO: Don't start on every call?
        from infer import Inference
        inferProc = Inference().proc
        inferProc.start()

        preset = args.pop("preset")
        config: dict = Config.inferMaskPresets.get(preset)
        classes = config.get("classes", [])

        maskBytes = inferProc.mask(config, classes, imgPath)
        return mask_ops.SegmentMaskOperation.operate(mat, maskBytes, **args)

    def opBrush(self, mat: np.ndarray, args: dict) -> np.ndarray:
        strokeColor  = args["color"]
        strokeSize   = args["size"]
        strokeSmooth = args["smooth"]
        strokePoints = args["stroke"]

        if not strokePoints:
            return mat

        height, width = mat.shape
        image = numpyToQImageMask(mat)

        # Prepare painter
        pen = QPen()
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setWidth(strokeSize)
        gradient = QLinearGradient()

        x, y, pressure = strokePoints[0]
        x = round(x * width)
        y = round(y * height)
        lastPoint = QPoint(x, y)

        color = pressure * strokeColor
        lastColor = QColor.fromRgbF(color, color, color, 1.0)

        painter = QPainter()
        painter.begin(image)

        if strokeColor > 0.0:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Lighten)
        else: # erase
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)

        if strokeSmooth:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw point
        if len(strokePoints) == 1:
            pen.setColor(lastColor)
            painter.setPen(pen)
            painter.drawPoint(lastPoint)

        # Draw stroke
        for x, y, pressure in strokePoints[1:]:
            x: int = round(x * width)
            y: int = round(y * height)
            currentPoint = QPoint(x, y)

            color = pressure * strokeColor
            currentColor = QColor.fromRgbF(color, color, color, 1.0)
            gradient.setStops([(0.0, lastColor), (1.0, currentColor)])

            pen.setBrush(QBrush(gradient))
            painter.setPen(pen)
            painter.drawLine(lastPoint, currentPoint)
            lastPoint = currentPoint
            lastColor = currentColor

        painter.end()

        # Convert QImage to numpy
        return qimageToNumpyMask(image)
