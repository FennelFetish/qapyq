import os
from typing_extensions import override
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import QSize, Qt, Slot
from lib.filelist import DataKeys
from lib import qtlib
from .thumbnail_cache import ThumbnailCache


class ImageIcon:
    Caption = "caption"
    Crop = "crop"
    Mask = "mask"

DATA_ICONS = {
    DataKeys.CaptionState: ImageIcon.Caption,
    DataKeys.CropState: ImageIcon.Crop,
    DataKeys.MaskState: ImageIcon.Mask
}


class GalleryItem(QtWidgets.QWidget):
    SelectionPrimary = 1
    SelectionCompare = 2

    BORDER_SIZE = 6

    def __init__(self, galleryGrid, file: str):
        super().__init__()
        from .gallery_grid import GalleryGrid
        self.gallery: GalleryGrid = galleryGrid
        self.file = file
        self.row = -1
        
        self.filename = os.path.basename(file)
        self.selectionStyle: int = 0
        self.icons = {}

        # Load initial state
        filelist = self.gallery.filelist
        for key in (DataKeys.CaptionState, DataKeys.CropState, DataKeys.MaskState):
            if state := filelist.getData(file, key):
                self.setIcon(key, state)

        if pixmap := filelist.getData(file, DataKeys.Thumbnail):
            self._pixmap = pixmap
            self._height = pixmap.height()
        else:
            self._pixmap = None
            self._height = self.gallery.thumbnailSize
        
        if imgSize := filelist.getData(file, DataKeys.ImageSize):
            self.setImageSize(imgSize[0], imgSize[1])
        else:
            self.setImageSize(0, 0)
        
        self.onThumbnailSizeUpdated()


    def setIcon(self, key, state):
        icon = DATA_ICONS.get(key)
        if not icon:
            return

        if state is None:
            if icon not in self.icons:
                return
            del self.icons[icon]
        else:
            self.icons[icon] = state
        
        self.update()

    def setImageSize(self, w: int, h: int):
        self.imgWidth, self.imgHeight = w, h

    def onThumbnailSizeUpdated(self):
        size = self.gallery.thumbnailSize
        self.setMinimumSize(size, size)


    def loadCaption(self):
        pass

    def takeFocus(self):
        pass


    @property
    def pixmap(self):
        return self._pixmap
    
    @pixmap.setter
    def pixmap(self, pixmap):
        self._pixmap = pixmap
        self._height = pixmap.height()
        self.update()
        self.gallery.thumbnailLoaded.emit()


    def sizeHint(self):
        return QSize(self.gallery.thumbnailSize, self._height)


    @property
    def selected(self) -> bool:
        return (self.selectionStyle & self.SelectionPrimary) != 0

    @selected.setter
    def selected(self, selected) -> None:
        if selected:
            self.selectionStyle |= self.SelectionPrimary
        else:
            self.selectionStyle &= ~self.SelectionPrimary
        self.update()

    def setCompare(self, selected):
        if selected:
            self.selectionStyle |= self.SelectionCompare
        else:
            self.selectionStyle &= ~self.SelectionCompare
        self.update()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.gallery.setSelectedItem(self, True)
        elif event.button() == Qt.MouseButton.RightButton:
            self.gallery.tab.imgview.tool.onGalleryRightClick(self.file)
            self.gallery.setSelectedCompare(self)


    def paintBorder(self, painter: QtGui.QPainter, palette: QtGui.QPalette, x, y, w, h):
        selectionColor = palette.color(QtGui.QPalette.ColorRole.Highlight)
        pen = QtGui.QPen(selectionColor)
        pen.setWidth(self.BORDER_SIZE)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        if self.selectionStyle & self.SelectionPrimary:
            pen.setStyle(Qt.PenStyle.SolidLine)
        elif self.selectionStyle & self.SelectionCompare:
            pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.drawRect(x, y, w, h)
    
    def paintIcons(self, painter: QtGui.QPainter, x, y):
        painter.save()

        sizeX, sizeY = 20, 20
        for iconKey, iconState in sorted(self.icons.items(), key=lambda item: item[0]):
            pen, brush = self.gallery.iconStates[iconState]
            painter.setPen(pen)
            painter.setBrush(brush)

            painter.drawRoundedRect(x, y, sizeX, sizeY, 3, 3)
            painter.drawPixmap(x, y, sizeX, sizeY, self.gallery.icons[iconKey])
            x += sizeX + 8
        
        painter.restore()



class GalleryGridItem(GalleryItem):
    def __init__(self, gallery, file):
        super().__init__(gallery, file)

    @staticmethod
    def getSpacing() -> int:
        return 4


    @override
    def paintEvent(self, event):
        palette = QtWidgets.QApplication.palette()
        
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)

        x = self.BORDER_SIZE/2
        y = x
        w = self.width() - self.BORDER_SIZE
        h = self.height() - self.BORDER_SIZE

        textSpacing = 3
        textMaxHeight = 40

        # Draw image
        if self._pixmap:
            imgW = self._pixmap.width()
            imgH = self._pixmap.height()
            aspect = imgH / imgW
            imgH = w * aspect
            painter.drawPixmap(x, y, w, imgH, self._pixmap)
        else:
            ThumbnailCache.updateThumbnail(self.gallery.filelist, self, self.file)
            imgH = 0

        # Draw icons
        self.paintIcons(painter, x+4, y+4)
        
        # Draw border
        if self.selectionStyle:
            self.paintBorder(painter, palette, x, y, w, h)
        
        # Draw filename
        textColor = palette.color(QtGui.QPalette.ColorRole.Text)
        pen = QtGui.QPen(textColor)
        painter.setPen(pen)
        textY = y + imgH + textSpacing
        painter.drawText(x, textY, w, textMaxHeight, Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, self.filename)

        self._height = y + imgH + self.BORDER_SIZE + textSpacing + textMaxHeight
        self.setFixedHeight(self._height)



class GalleryListItem(GalleryItem):
    COLUMN_WIDTH = 800
    HEADER_HEIGHT = 18

    def __init__(self, gallery, file):
        self._built = False
        self.gridLayout = QtWidgets.QGridLayout()

        super().__init__(gallery, file)
        self._captionLoaded = False

        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.MinimumExpanding)


    def _build(self):
        self._built = True

        layout = self.gridLayout
        layout.setContentsMargins(self.BORDER_SIZE, self.BORDER_SIZE, self.BORDER_SIZE, self.BORDER_SIZE)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnMinimumWidth(0, self.gallery.thumbnailSize + 4)
        layout.setRowStretch(0, 0)
        layout.setRowStretch(1, 1)

        row = 0
        self.lblFilename = QtWidgets.QLabel(self.filename)
        self.lblFilename.setFixedHeight(self.HEADER_HEIGHT)
        layout.addWidget(self.lblFilename, row, 1)
        self.setImageSize(self.imgWidth, self.imgHeight)

        self.btnSave = QtWidgets.QPushButton("Save")
        self.btnSave.clicked.connect(self._saveCaption)
        self.btnSave.setFixedHeight(self.HEADER_HEIGHT)
        self.btnSave.hide()
        layout.addWidget(self.btnSave, row, 2)

        self.btnReload = QtWidgets.QPushButton("Reload")
        self.btnReload.clicked.connect(self.loadCaption)
        self.btnReload.setFixedHeight(self.HEADER_HEIGHT)
        self.btnReload.hide()
        layout.addWidget(self.btnReload, row, 3)

        row += 1
        self.txtCaption = QtWidgets.QPlainTextEdit()
        self.txtCaption.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        qtlib.setMonospace(self.txtCaption)
        qtlib.setShowWhitespace(self.txtCaption)
        self.txtCaption.textChanged.connect(self._onCaptionChanged)
        layout.addWidget(self.txtCaption, row, 1, 1, 3)

        self.setLayout(layout)


    @override
    def setImageSize(self, w: int, h: int):
        super().setImageSize(w, h)
        if self._built:
            self.lblFilename.setText(f"{self.filename} ({self.imgWidth}x{self.imgHeight})")

    @override
    def onThumbnailSizeUpdated(self):
        size = self.gallery.thumbnailSize
        self.setMinimumSize(size*2, size)
        self.gridLayout.setColumnMinimumWidth(0, self.gallery.thumbnailSize + 4)


    @Slot()
    def loadCaption(self):
        caption = self.gallery.captionSrc.loadCaption(self.file)
        if caption is None:
            caption = ""
        
        self.txtCaption.setPlainText(caption)
        self._captionLoaded = True

        self.btnSave.hide()
        self.btnReload.hide()

    @Slot()
    def _onCaptionChanged(self):
        self.btnSave.show()
        self.btnReload.show()

    @Slot()
    def _saveCaption(self):
        text = self.txtCaption.toPlainText()
        if self.gallery.captionSrc.saveCaption(self.file, text):
            self.btnSave.hide()
            self.btnReload.hide()

            self.gallery.filelist.setData(self.file, DataKeys.CaptionState, DataKeys.IconStates.Saved)


    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.matches(QtGui.QKeySequence.StandardKey.Save) and self.txtCaption.hasFocus():
            self._saveCaption()
            event.accept()
            return
        return super().keyPressEvent(event)

    @override
    def takeFocus(self):
        if self._built:
            self.txtCaption.setFocus()
            self.txtCaption.moveCursor(QtGui.QTextCursor.MoveOperation.End)


    @staticmethod
    def getSpacing() -> int:
        return 10


    @override
    def paintEvent(self, event):
        if not self._built:
            self._build()
        if not self._captionLoaded:
            self.loadCaption()

        palette = QtWidgets.QApplication.palette()
        
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)

        x = self.BORDER_SIZE/2
        y = x
        w = self.width() - self.BORDER_SIZE
        h = self.height() - self.BORDER_SIZE

        # Draw image
        if self._pixmap:
            imgW = self._pixmap.width()
            imgH = self._pixmap.height()
            aspect = imgH / imgW
            imgW = self.gallery.thumbnailSize
            imgH = imgW * aspect
            painter.drawPixmap(x, y, imgW, imgH, self._pixmap)
        else:
            ThumbnailCache.updateThumbnail(self.gallery.filelist, self, self.file)
            imgH = 0

        # Draw icons
        self.paintIcons(painter, x+4, y+4)
        
        # Draw border
        if self.selectionStyle:
            self.paintBorder(painter, palette, x, y, w, h)
        
        self._height = y + imgH + self.BORDER_SIZE
        self._height = max(self._height, 100)
        self.setMinimumHeight(self._height)
