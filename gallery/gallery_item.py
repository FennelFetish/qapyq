from __future__ import annotations
import os
from typing_extensions import override
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import QSize, Qt, Slot
from lib.filelist import DataKeys
from lib import qtlib
from .thumbnail_cache import ThumbnailCache

# Imported at the bottom because of circular dependency
# from .gallery_grid import GalleryGrid


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
    SELECTION_PRIMARY   = 1
    SELECTION_SECONDARY = 2

    BORDER_SIZE = 6
    BORDER_SIZE_SECONDARY = 3

    PEN_TEXT: QtGui.QPen = None
    PEN_PRIMARY: QtGui.QPen = None
    PEN_SECONDARY: QtGui.QPen = None


    def __init__(self, galleryGrid: GalleryGrid, file: str):
        super().__init__()
        self.gallery = galleryGrid
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

    @classmethod
    def _initPens(cls):
        palette = QtWidgets.QApplication.palette()
        textColor = palette.color(QtGui.QPalette.ColorRole.Text)
        selectionColor = palette.color(QtGui.QPalette.ColorRole.Highlight)

        cls.PEN_TEXT = QtGui.QPen(textColor)

        cls.PEN_PRIMARY = QtGui.QPen(selectionColor)
        cls.PEN_PRIMARY.setStyle(Qt.PenStyle.SolidLine)
        cls.PEN_PRIMARY.setWidth(cls.BORDER_SIZE)
        cls.PEN_PRIMARY.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        cls.PEN_SECONDARY = QtGui.QPen(selectionColor)
        cls.PEN_SECONDARY.setStyle(Qt.PenStyle.DotLine)
        cls.PEN_SECONDARY.setWidth(cls.BORDER_SIZE_SECONDARY)
        cls.PEN_SECONDARY.setJoinStyle(Qt.PenJoinStyle.RoundJoin)


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

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


    @property
    def selected(self) -> bool:
        return (self.selectionStyle & self.SELECTION_PRIMARY) != 0

    @selected.setter
    def selected(self, selected: bool) -> None:
        if selected:
            self.selectionStyle |= self.SELECTION_PRIMARY
        else:
            self.selectionStyle &= ~self.SELECTION_PRIMARY
        self.update()

    @property
    def selectedSecondary(self) -> bool:
        return (self.selectionStyle & self.SELECTION_SECONDARY) != 0

    @selectedSecondary.setter
    def selectedSecondary(self, selected: bool):
        if selected:
            self.selectionStyle |= self.SELECTION_SECONDARY
        else:
            self.selectionStyle &= ~self.SELECTION_SECONDARY
        self.update()


    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            ctrl  = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)

            # Secondary range selection
            if shift:
                if ctrl:
                    self.gallery.filelist.unselectFileRange(self.file)
                else:
                    self.gallery.filelist.selectFileRange(self.file)

            # Toggle secondary selection
            elif ctrl:
                if not self.selected:
                    if self.selectedSecondary:
                        self.gallery.filelist.unselectFile(self.file)
                    else:
                        self.gallery.filelist.selectFile(self.file)

            # Select for comparison
            elif event.modifiers() & Qt.KeyboardModifier.AltModifier:
                self.gallery.tab.mainWindow.setTool("compare")
                self.gallery.tab.imgview.tool.onGalleryRightClick(self.file)

            # Primary selection
            elif not self.selected:
                with self.gallery.tab.takeFocus() as filelist:
                    filelist.setCurrentFile(self.file)

        # Primary selection and open menu
        elif event.button() == Qt.MouseButton.RightButton:
            with self.gallery.tab.takeFocus() as filelist:
                filelist.setCurrentFile(self.file)

            menu = GalleryItemMenu(self.gallery)
            menu.exec( self.mapToGlobal(event.pos()) )


    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.selected:
            self.gallery.filelist.clearSelection()
            event.accept()

        super().mouseDoubleClickEvent(event)


    def onDragOver(self, event: QtGui.QMouseEvent):
        if not self.selected:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if self.selectedSecondary:
                    self.gallery.filelist.unselectFile(self.file)
            elif not self.selectedSecondary:
                self.gallery.filelist.selectFile(self.file)


    def paintBorder(self, painter: QtGui.QPainter, x: int, y: int, w: int, h: int):
        if self.selected:
            painter.setPen(self.PEN_PRIMARY)
            painter.drawRect(x, y, w, h)
        elif self.selectedSecondary:
            painter.setPen(self.PEN_SECONDARY)
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
    TEXT_SPACING = 3
    TEXT_MAX_HEIGHT = 40

    def __init__(self, gallery, file):
        super().__init__(gallery, file)

    @staticmethod
    def getSpacing() -> int:
        return 4


    @override
    def paintEvent(self, event):
        if not self.PEN_TEXT:
            self._initPens()

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
            imgH = w * aspect
            painter.drawPixmap(x, y, w, imgH, self._pixmap)
        else:
            ThumbnailCache.updateThumbnail(self.gallery.filelist, self, self.file)
            imgH = 0

        self.paintIcons(painter, x+4, y+4)
        self.paintBorder(painter, x, y, w, h)

        # Draw filename
        textY = y + imgH + self.TEXT_SPACING
        flags = Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap
        painter.setPen(self.PEN_TEXT)
        painter.drawText(x, textY, w, self.TEXT_MAX_HEIGHT, flags, self.filename)

        self._height = y + imgH + self.BORDER_SIZE + self.TEXT_SPACING + self.TEXT_MAX_HEIGHT
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
        # Will load caption when painted
        if not self._built:
            return

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
        if not self.PEN_TEXT:
            self._initPens()
        if not self._built:
            self._build()
        if not self._captionLoaded:
            self.loadCaption()

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

        self.paintIcons(painter, x+4, y+4)
        self.paintBorder(painter, x, y, w, h)

        self._height = y + imgH + self.BORDER_SIZE
        self._height = max(self._height, 100)
        self.setMinimumHeight(self._height)



class GalleryItemMenu(QtWidgets.QMenu):
    def __init__(self, galleryGrid: GalleryGrid):
        super().__init__("Gallery")
        self.gallery = galleryGrid

        actClearSelection = self.addAction("Clear Selection")
        if galleryGrid.filelist.selectedFiles:
            actClearSelection.triggered.connect(lambda: self.gallery.filelist.clearSelection())
            strFiles = "Files"
        else:
            actClearSelection.setEnabled(False)
            strFiles = "File"

        actNewTab = self.addAction(f"Open {strFiles} in New Tab")
        actNewTab.triggered.connect(self._openFilesInNewTab)

        self.addSeparator()

        actUnloadSelection = self.addAction(f"Unload Selected {strFiles}")
        actUnloadSelection.triggered.connect(self._unloadSelectedFiles)

    @Slot()
    def _openFilesInNewTab(self):
        filelist = self.gallery.filelist
        files = filelist.selectedFiles or (filelist.getCurrentFile(),)
        newTab = self.gallery.tab.mainWindow.addTab()
        newTab.filelist.loadFilesFixed(files, filelist)

    @Slot()
    def _unloadSelectedFiles(self):
        filelist = self.gallery.filelist
        if filelist.selectedFiles:
            filelist.filterFiles(lambda file: file not in filelist.selectedFiles)
        else:
            currentFile = filelist.getCurrentFile()
            filelist.filterFiles(lambda file: file != currentFile)



from .gallery_grid import GalleryGrid
