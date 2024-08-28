from .view import ViewTool
from PySide6 import QtGui


# Multiple layers (rgba as 4 alpha channels; binary masks: set layer color)
# Blur tools (gaussian)
# Auto masking (RemBg, clipseg, yolo ...)
# Invert mask
# Brushes: Set size, solid brush, blurry brush, subtractive brush ...


class MaskTool(ViewTool):
    def __init__(self, tab):
        super().__init__(tab)
        print("MaskTool Ctor")

        #self._mask = QImage

# === Tool Interface ===
    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        # self._mask.setRect(self._imgview.viewport().rect())
        # imgview._guiScene.addItem(self._mask)
        # imgview._guiScene.addItem(self._cropRect)

        # imgview.rotation = self._toolbar.slideRot.value() / 10
        # imgview.updateImageTransform()

        # self._toolbar.updateSize()
        # imgview.filelist.addListener(self)

    def onDisabled(self, imgview):
        super().onDisabled(imgview)
        # imgview._guiScene.removeItem(self._mask)
        # imgview._guiScene.removeItem(self._cropRect)

        # imgview.rotation = 0.0
        # imgview.updateImageTransform()

        # imgview.filelist.removeListener(self)


    def onSceneUpdate(self):
        super().onSceneUpdate()

        # imgsize = self._imgview.image.pixmap().size()
        # self._mask = QtGui.QImage(imgsize, QtGui.QImage.Format_Mono)