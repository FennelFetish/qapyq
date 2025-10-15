from __future__ import annotations
import os
from typing_extensions import override
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import QSize, Qt, Slot, QPoint, QPointF, QTimer, QSignalBlocker
from lib.filelist import DataKeys
from lib.captionfile import FileTypeSelector
from lib.util import CaptionSplitter
from lib import colorlib, qtlib
from caption.caption_text import NavigationTextEdit
from caption.caption_highlight import CaptionHighlight, MatcherNode
from caption.caption_filter import CaptionRulesProcessor, CaptionRulesSettings

# Imported at the bottom because of circular dependency
# from .gallery_grid import GalleryGrid
# from .thumbnail_cache import ThumbnailCache


class ImageIcon:
    Caption = "caption"
    Crop = "crop"
    Mask = "mask"

DATA_ICONS = {
    DataKeys.CaptionState: ImageIcon.Caption,
    DataKeys.CropState: ImageIcon.Crop,
    DataKeys.MaskState: ImageIcon.Mask
}



class GalleryContext:
    def __init__(self, captionSrc: FileTypeSelector):
        self.captionSrc = captionSrc
        self.captionsEnabled: bool = False

        self.updateTextFlags()

        from .gallery_sort import GallerySortControl
        self.gallerySort: GallerySortControl = None

        self.captionHighlight: CaptionHighlight | None = None
        self.filterNode: MatcherNode[bool] | None = None
        self.splitter = CaptionSplitter()
        self.separator = ", "

        self.rulesProcessor: CaptionRulesProcessor | None = None
        self.rulesSettings = CaptionRulesSettings()
        self.rulesSettings.prefixSuffix = False

    def updateTextFlags(self):
        if self.captionsEnabled:
            self.textFlags = Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap
            self.textOpt = QtGui.QTextOption()
            self.textOpt.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.textOpt.setWrapMode(QtGui.QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        else:
            self.textFlags = Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWrapAnywhere
            self.textOpt = QtGui.QTextOption()
            self.textOpt.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.textOpt.setWrapMode(QtGui.QTextOption.WrapMode.WrapAnywhere)

    def loadCaption(self, file: str, filter=False) -> str:
        caption = self.captionSrc.loadCaption(file)
        if caption is None:
            return ""

        if filter:
            if self.filterNode:
                tags = self.splitter.split(caption)
                caption = self.separator.join(
                    tag for tag in tags
                    if self.filterNode.match(tag.split(" "))
                )

            if self.rulesProcessor:
                caption = self.rulesProcessor.process(caption, self.rulesSettings)

        return caption



class GalleryItem(QtWidgets.QWidget):
    SELECTION_PRIMARY   = 1
    SELECTION_SECONDARY = 2

    BORDER_SIZE = 6
    BORDER_SIZE_SECONDARY = 3

    PEN_TEXT: QtGui.QPen = None
    PEN_TEXT_ERROR: QtGui.QPen = None
    PEN_PRIMARY: QtGui.QPen = None
    PEN_SECONDARY: QtGui.QPen = None

    BRUSH_HIGHLIGHT: QtGui.QBrush = None

    MIN_HEIGHT = 200


    def __init__(self, galleryGrid: GalleryGrid, file: str):
        super().__init__()
        self.gallery = galleryGrid
        self.file = file
        self.row = -1

        self.filename = os.path.basename(file)
        self.selectionStyle: int = 0
        self.highlight: bool = False
        self.icons = {}

        # Load initial state
        filelist = self.gallery.filelist
        for key in (DataKeys.CaptionState, DataKeys.CropState, DataKeys.MaskState):
            if state := filelist.getData(file, key):
                self.setIcon(key, state)

        self._pixmap: QtGui.QPixmap | None = filelist.getData(file, DataKeys.Thumbnail)
        self._height = self._pixmap.height() if self._pixmap else self.MIN_HEIGHT

        self.ready = self._pixmap is not None
        self.reloadCaption = True

        if imgSize := filelist.getData(file, DataKeys.ImageSize):
            self.setImageSize(imgSize[0], imgSize[1])
        else:
            self.setImageSize(0, 0)

        self.onThumbnailSizeUpdated()
        self.setFixedHeight(self.MIN_HEIGHT)

    @classmethod
    def _initPens(cls):
        palette = QtWidgets.QApplication.palette()
        textColor = palette.color(QtGui.QPalette.ColorRole.Text)
        selectionColor = palette.color(QtGui.QPalette.ColorRole.Highlight)

        cls.PEN_TEXT = QtGui.QPen(textColor)
        cls.PEN_TEXT_ERROR = QtGui.QPen(colorlib.RED)

        cls.PEN_PRIMARY = QtGui.QPen(selectionColor)
        cls.PEN_PRIMARY.setStyle(Qt.PenStyle.SolidLine)
        cls.PEN_PRIMARY.setWidth(cls.BORDER_SIZE)
        cls.PEN_PRIMARY.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        cls.PEN_SECONDARY = QtGui.QPen(selectionColor)
        cls.PEN_SECONDARY.setStyle(Qt.PenStyle.DotLine)
        cls.PEN_SECONDARY.setWidth(cls.BORDER_SIZE_SECONDARY)
        cls.PEN_SECONDARY.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        cls.BRUSH_HIGHLIGHT = QtGui.QBrush(selectionColor)

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
        self.imgWidth  = max(w, 0)
        self.imgHeight = max(h, 0)

    def onThumbnailSizeUpdated(self):
        size = self.gallery.thumbnailSize
        self.setMinimumSize(size, size)


    def takeFocus(self):
        pass


    @property
    def pixmap(self):
        return self._pixmap

    @pixmap.setter
    def pixmap(self, pixmap: QtGui.QPixmap):
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


    def paintHighlight(self, painter: QtGui.QPainter, x: int, y: int, w: int, h: int, imgW: int, imgH: int, drawRect=True):
        painter.save()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.BRUSH_HIGHLIGHT)

        if drawRect:
            painter.drawRect(x, y+imgH-1, w, h-imgH+1)

        w = imgW + x
        h = imgH + y
        s = 20
        painter.drawConvexPolygon((QPoint(x, y), QPoint(x+s, y), QPoint(x, y+s))) # Top left
        painter.drawConvexPolygon((QPoint(w, y), QPoint(w, y+s), QPoint(w-s, y))) # Top right
        painter.drawConvexPolygon((QPoint(x, h), QPoint(x, h-s), QPoint(x+s, h))) # Bottom left
        painter.drawConvexPolygon((QPoint(w, h), QPoint(w-s, h), QPoint(w, h-s))) # Bottom right

        painter.restore()

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
    TEXT_MAX_HEIGHT = 200

    def __init__(self, gallery, file):
        super().__init__(gallery, file)
        self.labelText = self.filename

    @staticmethod
    def getSpacing() -> int:
        return 4

    def loadCaption(self):
        ctx = self.gallery.ctx
        self.labelText = ctx.loadCaption(self.file, True) if ctx.captionsEnabled else self.filename
        self.reloadCaption = False

    def _layoutCaption(self, w: int) -> tuple[float, list[QtGui.QTextLayout]]:
        ctx = self.gallery.ctx
        layouts = list[QtGui.QTextLayout]()
        totalHeight = 0.0

        for line in filter(None, self.labelText.splitlines()):
            textLayout = QtGui.QTextLayout(line)
            textLayout.setCacheEnabled(True)
            textLayout.setTextOption(ctx.textOpt)
            layouts.append(textLayout)

            if ctx.captionHighlight:
                ctx.captionHighlight.highlightTextLayout(line, ctx.separator, textLayout)

            textLayout.beginLayout()
            while (line := textLayout.createLine()).isValid():
                line.setLineWidth(w)
                line.setPosition(QPointF(0, totalHeight))
                totalHeight += line.height()
                if totalHeight >= self.TEXT_MAX_HEIGHT:
                    textLayout.endLayout()
                    return self._addEllipsis(w, totalHeight, layouts)

            textLayout.endLayout()

        return totalHeight, layouts

    def _addEllipsis(self, w: int, h: float, layouts: list[QtGui.QTextLayout]) -> tuple[float, list[QtGui.QTextLayout]]:
        textLayout = QtGui.QTextLayout("…")
        textLayout.setCacheEnabled(True)
        textLayout.setTextOption(self.gallery.ctx.textOpt)

        textLayout.beginLayout()
        line = textLayout.createLine()
        line.setLineWidth(w)

        lineHeight = line.height()
        h -= lineHeight * 0.4
        line.setPosition(QPointF(0, h))
        h += lineHeight

        textLayout.endLayout()
        layouts.append(textLayout)
        return h, layouts


    @override
    def paintEvent(self, event):
        if not self.PEN_TEXT:
            self._initPens()
        if self.reloadCaption:
            self.loadCaption()

        painter = QtGui.QPainter(self)
        if not painter.isActive():
            return

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)

        x = self.BORDER_SIZE // 2
        y = x
        w = self.width() - self.BORDER_SIZE
        h = self.height() - self.BORDER_SIZE

        pen = self.PEN_TEXT

        # Draw image
        if self._pixmap is not None:
            if self._pixmap.isNull():
                pen = self.PEN_TEXT_ERROR
                imgH = 0
            else:
                aspect = self._pixmap.height() / self._pixmap.width()
                imgH = round(w * aspect)
                painter.drawPixmap(x, y, w, imgH, self._pixmap)
        else:
            if self.ready:
                ThumbnailCache.updateThumbnail(self.gallery.filelist, self, self.file)
            imgH = self.MIN_HEIGHT

        if self.highlight:
            self.paintHighlight(painter, x, y, w, h, w, imgH)

        self.paintIcons(painter, x+4, y+4)
        self.paintBorder(painter, x, y, w, h)

        # Draw label
        ctx = self.gallery.ctx
        textY = y + imgH + self.TEXT_SPACING
        textW = w - self.BORDER_SIZE
        painter.setPen(pen)

        if ctx.captionsEnabled:
            if self.labelText:
                textH, textLayouts = self._layoutCaption(textW)
                for textLayout in textLayouts:
                    textLayout.draw(painter, QPoint(self.BORDER_SIZE, textY))
            else:
                textH = -2 * self.TEXT_SPACING
        else:
            textRect = painter.fontMetrics().boundingRect(self.BORDER_SIZE, textY, textW, self.TEXT_MAX_HEIGHT, ctx.textFlags, self.labelText)
            if textRect.height() > self.TEXT_MAX_HEIGHT:
                textRect.setHeight(self.TEXT_MAX_HEIGHT)
            painter.drawText(textRect, self.labelText, ctx.textOpt)
            textH = textRect.height()

        painter.end()

        self._height = y + imgH + self.TEXT_SPACING + textH + self.TEXT_SPACING + y
        self.setFixedHeight(int(self._height + 0.5))



class GalleryListItem(GalleryItem):
    COLUMN_WIDTH = 800
    HEADER_HEIGHT = 18
    SIZE_POLICY = (QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.MinimumExpanding)

    def __init__(self, gallery, file):
        self._built = False
        self.gridLayout = QtWidgets.QGridLayout()

        super().__init__(gallery, file)
        self.setSizePolicy(*self.SIZE_POLICY)


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
        self.btnReload.clicked.connect(self._reloadCaption)
        self.btnReload.setFixedHeight(self.HEADER_HEIGHT)
        self.btnReload.hide()
        layout.addWidget(self.btnReload, row, 3)

        row += 1
        self.txtCaption = NavigationTextEdit(self.gallery.ctx.separator)
        self.txtCaption.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        qtlib.setMonospace(self.txtCaption)
        qtlib.setShowWhitespace(self.txtCaption)
        self.txtCaption.textChanged.connect(self._onCaptionChanged)
        layout.addWidget(self.txtCaption, row, 1, 1, 3)

        self.setLayout(layout)


    @override
    def setImageSize(self, w: int, h: int):
        super().setImageSize(w, h)
        if self._built and self._pixmap is not None:
            if w < 1 or h < 1:
                self.lblFilename.setStyleSheet(f"color: {colorlib.RED}")
            self.lblFilename.setText(f"{self.filename} ({self.imgWidth}x{self.imgHeight})")

    @override
    def onThumbnailSizeUpdated(self):
        size = self.gallery.thumbnailSize
        self.setMinimumSize(size*2, size)
        self.gridLayout.setColumnMinimumWidth(0, self.gallery.thumbnailSize + 4)


    @property
    def captionEdited(self) -> bool:
        return not (self.btnSave.isHidden() and self.btnReload.isHidden())

    @Slot()
    def _reloadCaption(self):
        self.loadCaption(False)

    def loadCaption(self, reset: bool):
        # Will load caption when painted
        if not self._built:
            return

        ctx = self.gallery.ctx
        caption = ctx.loadCaption(self.file)
        self.txtCaption.separator = ctx.separator

        # This loadCaption() method is called during repaint. Postpone highlighting to not repaint recursively.
        with QSignalBlocker(self.txtCaption):
            self.txtCaption.setCaption(caption)
        QTimer.singleShot(0, self.updateCaptionHighlight)

        if reset:
            self.txtCaption.document().clearUndoRedoStacks()

        self.btnSave.hide()
        self.btnReload.hide()
        self.reloadCaption = False

    @Slot()
    def _onCaptionChanged(self):
        self.btnSave.show()
        self.btnReload.show()
        self.updateCaptionHighlight()

    @Slot()
    def updateCaptionHighlight(self):
        ctx = self.gallery.ctx
        if ctx.captionHighlight:
            text = self.txtCaption.toPlainText()
            ctx.captionHighlight.highlight(text, ctx.separator, self.txtCaption)


    @Slot()
    def _saveCaption(self):
        text = self.txtCaption.getCaption()
        if self.gallery.ctx.captionSrc.saveCaption(self.file, text):
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
        if self.reloadCaption:
            self.loadCaption(True)

        painter = QtGui.QPainter(self)
        if not painter.isActive():
            return

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)

        x = self.BORDER_SIZE // 2
        y = x
        w = self.width() - self.BORDER_SIZE
        h = self.height() - self.BORDER_SIZE

        imgW = self.gallery.thumbnailSize
        imgH = self.MIN_HEIGHT

        # Draw image
        if self._pixmap is not None:
            if not self._pixmap.isNull():
                aspect = self._pixmap.height() / self._pixmap.width()
                imgH = round(imgW * aspect)
                painter.drawPixmap(x, y, imgW, imgH, self._pixmap)
        elif self.ready:
            ThumbnailCache.updateThumbnail(self.gallery.filelist, self, self.file)

        if self.highlight:
            self.paintHighlight(painter, x, y, w, h, imgW, imgH, False)

        self.paintIcons(painter, x+4, y+4)
        self.paintBorder(painter, x, y, w, h)
        painter.end()

        self._height = y + imgH + self.BORDER_SIZE
        self._height = max(self._height, 100)
        self.setMinimumHeight(int(self._height + 0.5))



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

        actSemanticSort = self.addAction(f"Sort by Similarity to Selected {strFiles}")
        actSemanticSort.triggered.connect(self._sortBySimilarity)

        actNewTab = self.addAction(f"Open Selected {strFiles} in New Tab")
        actNewTab.triggered.connect(self._openFilesInNewTab)

        self.addSeparator()

        actUnloadSelection = self.addAction(f"Unload Selected {strFiles}")
        actUnloadSelection.triggered.connect(self._unloadSelectedFiles)

    @Slot()
    def _sortBySimilarity(self):
        filelist = self.gallery.filelist
        files = list(filelist.selectedFiles) if filelist.selectedFiles else [filelist.getCurrentFile()]
        self.gallery.ctx.gallerySort.updateSortByImage(files)

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
from .thumbnail_cache import ThumbnailCache
