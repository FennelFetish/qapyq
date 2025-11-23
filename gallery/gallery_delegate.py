from collections import defaultdict
from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QSize, QPoint, QRect, QModelIndex, QPersistentModelIndex
from PySide6.QtGui import QFontMetrics, QPainter, QPixmap
from lib import colorlib
from lib.filelist import DataKeys
from .gallery_caption import GalleryCaption
from .gallery_model import GalleryModel, ImageIcon, SelectionState
from .gallery_header import GalleryHeader


class SizeHintCacheRow:
    __slots__ = ('size', 'colMask')

    def __init__(self):
        self.size: QSize | None = None
        self.colMask = 0

    def hasColumn(self, col: int) -> bool:
        return self.colMask & (1 << col) > 0

    def setColumnSize(self, col: int, size: QSize):
        self.colMask |= (1 << col)
        if self.size is None or size.height() > self.size.height():
            self.size = size

    def reset(self):
        self.size = None
        self.colMask = 0



class BaseGalleryDelegate(QtWidgets.QStyledItemDelegate):
    DEFAULT_HEIGHT = 200

    BORDER_SIZE = 6
    BORDER_SIZE_SECONDARY = 3


    def __init__(self, galleryView, galleryCaption: GalleryCaption):
        super().__init__()

        from .gallery_view import GalleryView
        self.view: GalleryView = galleryView
        self.caption = galleryCaption

        self.numColumns = 1
        self.xSpacing = 0

        self.sizeCache = defaultdict(SizeHintCacheRow)
        self.captionCache = dict[tuple[int, int], tuple[QtGui.QTextLayout, ...]]()

        self.icons = {
            ImageIcon.Caption:  QtGui.QPixmap("./res/icon_caption.png"),
            ImageIcon.Crop:     QtGui.QPixmap("./res/icon_crop.png"),
            ImageIcon.Mask:     QtGui.QPixmap("./res/icon_mask.png")
        }

        colorWhite = QtGui.QColor(230, 230, 230)
        colorGreen = QtGui.QColor(50, 180, 60)
        colorRed   = QtGui.QColor(250, 70, 30)
        self.iconColors = {
            DataKeys.IconStates.Exists:     (QtGui.QPen(colorWhite), QtGui.QBrush(colorWhite)),
            DataKeys.IconStates.Saved:      (QtGui.QPen(colorGreen), QtGui.QBrush(colorGreen)),
            DataKeys.IconStates.Changed:    (QtGui.QPen(colorRed),   QtGui.QBrush(colorRed)),
        }

        self._initPens()

    def _initPens(self):
        palette = QtWidgets.QApplication.palette()
        textColor = palette.color(QtGui.QPalette.ColorRole.Text)
        selectionColor = palette.color(QtGui.QPalette.ColorRole.Highlight)

        self.PEN_TEXT = QtGui.QPen(textColor)
        self.PEN_TEXT_ERROR = QtGui.QPen(colorlib.RED)

        self.PEN_PRIMARY = QtGui.QPen(selectionColor)
        self.PEN_PRIMARY.setStyle(Qt.PenStyle.SolidLine)
        self.PEN_PRIMARY.setWidth(self.BORDER_SIZE)
        self.PEN_PRIMARY.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        self.PEN_SECONDARY = QtGui.QPen(selectionColor)
        self.PEN_SECONDARY.setStyle(Qt.PenStyle.DotLine)
        self.PEN_SECONDARY.setWidth(self.BORDER_SIZE_SECONDARY)
        self.PEN_SECONDARY.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        self.BRUSH_HIGHLIGHT = QtGui.QBrush(selectionColor)


    def itemWidth(self) -> int:
        return self.view.itemWidth

    def spacing(self) -> int:
        return 4


    def setNumColumns(self, columnCount: int):
        self.numColumns = columnCount
        totalSpacing = self.spacing() * (columnCount-1)
        self.xSpacing = totalSpacing // columnCount


    @Slot()
    def clearCache(self):
        self.sizeCache.clear()
        self.captionCache.clear()
        self.view.updateVisibleRows()

    @Slot(QModelIndex, QModelIndex, list)
    def onDataChanged(self, startIndex: QModelIndex, endIndex: QModelIndex, roles: list[int]):
        resetSizeHint = Qt.ItemDataRole.SizeHintRole in roles

        if GalleryModel.ROLE_CAPTION in roles:
            resetSizeHint = True
            for row in range(startIndex.row(), endIndex.row()+1):
                for col in range(startIndex.column(), endIndex.column()+1):
                    self.captionCache.pop((row, col), None)

        if resetSizeHint:
            for row in range(startIndex.row(), endIndex.row()+1):
                self.sizeCache[row].reset()
                self.view.resizeRowToContents(row)


    def _adjustRect(self, rect: QRect, column: int):
        xOffset = round((column / (self.numColumns-1)) * self.xSpacing) if self.numColumns > 1 else 0
        halfBorder = self.BORDER_SIZE // 2
        spacing = self.spacing()

        x = rect.left()   + halfBorder + xOffset
        y = rect.top()    + halfBorder + spacing
        w = rect.width()  - self.BORDER_SIZE - self.xSpacing
        h = rect.height() - self.BORDER_SIZE - spacing*2
        return QRect(x, y, w, h)


    @override
    def paint(self, painter: QPainter, option: QtWidgets.QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        itemType = index.data(GalleryModel.ROLE_TYPE)
        if itemType != GalleryModel.ItemType.File:
            return

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)

        rect = self._adjustRect(option.rect, index.column())
        self.paintItem(painter, rect, index)

    def paintItem(self, painter: QPainter, rect: QRect, index: QModelIndex | QPersistentModelIndex):
        raise NotImplementedError()

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

    def paintBorder(self, painter: QtGui.QPainter, x: int, y: int, w: int, h: int, selectionState: int):
        painter.save()

        if selectionState == SelectionState.Primary:
            painter.setPen(self.PEN_PRIMARY)
            painter.drawRect(x, y, w, h)
        elif selectionState == SelectionState.Secondary:
            painter.setPen(self.PEN_SECONDARY)
            painter.drawRect(x, y, w, h)

        painter.restore()

    def paintIcons(self, painter: QtGui.QPainter, x, y, icons: dict[str, DataKeys.IconStates]):
        painter.save()

        sizeX, sizeY = 20, 20
        for iconKey, iconState in sorted(icons.items(), key=lambda item: item[0]):
            if iconState is None:
                continue

            pen, brush = self.iconColors[iconState]
            painter.setPen(pen)
            painter.setBrush(brush)

            painter.drawRoundedRect(x, y, sizeX, sizeY, 3, 3)
            painter.drawPixmap(x, y, sizeX, sizeY, self.icons[iconKey])
            x += sizeX + 8

        painter.restore()


    @override
    def sizeHint(self, option: QtWidgets.QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        itemType = index.data(GalleryModel.ROLE_TYPE)
        if itemType != GalleryModel.ItemType.File:
            return QSize(0, 0)

        cacheRow = self.sizeCache[index.row()]
        if not cacheRow.hasColumn(index.column()):
            h = self.sizeHintHeight(option.rect, index)
            h += self.BORDER_SIZE + 2*self.spacing()
            cacheRow.setColumnSize(index.column(), QSize(0, h))

        return cacheRow.size

    def sizeHintHeight(self, rect: QRect, index: QModelIndex | QPersistentModelIndex) -> int:
        raise NotImplementedError()


    @override
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QtWidgets.QWidget:
        itemType = index.data(GalleryModel.ROLE_TYPE)
        if itemType == GalleryModel.ItemType.Header:
            return GalleryHeader(parent, self.view.tab, index.data(Qt.ItemDataRole.DisplayRole))
        return super().createEditor(parent, option, index)

    @override
    def setEditorData(self, editor: QtWidgets.QWidget, index: QModelIndex | QPersistentModelIndex):
        if isinstance(editor, GalleryHeader):
            editor.updateImageLabel(index.data(GalleryModel.ROLE_IMGCOUNT))

    @override
    def setModelData(self, editor: QtWidgets.QWidget, model, index: QModelIndex | QPersistentModelIndex):
        pass  # No-op to prevent any changes from being saved



class GalleryGridDelegate(BaseGalleryDelegate):
    TEXT_SPACING = 4
    TEXT_MAX_HEIGHT = 200

    def __init__(self, galleryView, galleryCaption: GalleryCaption):
        super().__init__(galleryView, galleryCaption)

        self.textFlags = Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWrapAnywhere
        self.textOpt = QtGui.QTextOption()
        self.textOpt.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.textOpt.setWrapMode(QtGui.QTextOption.WrapMode.WrapAnywhere)

        self.labelFontMetrics = QFontMetrics(QtGui.QFont())


    def _getCaptionLayouts(self, w: int, h: int, index: QModelIndex | QPersistentModelIndex) -> tuple[QtGui.QTextLayout, ...]:
        key = (index.row(), index.column())
        textLayouts = self.captionCache.get(key)

        if textLayouts is None:
            if label := index.data(GalleryModel.ROLE_CAPTION):
                textLayouts = tuple(self.caption.layoutCaption(label, w, h)[1])
            else:
                textLayouts = ()
            self.captionCache[key] = textLayouts

        return textLayouts


    @override
    def paintItem(self, painter: QPainter, rect: QRect, index: QModelIndex | QPersistentModelIndex):
        x, y, w, h = rect.left(), rect.top(), rect.width(), rect.height()

        pixmap: QPixmap | None = index.data(Qt.ItemDataRole.DecorationRole)
        if pixmap:
            ar = pixmap.height() / pixmap.width()
            imgH = round(ar * w)
            painter.drawPixmap(x, y, w, imgH, pixmap)
        else:
            imgH = 0

        self.paintIcons(painter, x+4, y+4, index.data(GalleryModel.ROLE_ICONS))
        self.paintBorder(painter, x, y, w, h, index.data(GalleryModel.ROLE_SELECTION))

        textX = x + self.BORDER_SIZE // 2
        textY = y + imgH + self.TEXT_SPACING
        textW = w - self.BORDER_SIZE
        textH = rect.bottom() - textY

        if self.caption.captionsEnabled:
            for textLayout in self._getCaptionLayouts(textW, textH, index):
                textLayout.draw(painter, QPoint(textX, textY))
        else:
            label = index.data(GalleryModel.ROLE_FILENAME)
            textRect = QRect(textX, textY, textW, textH)
            painter.drawText(textRect, label, self.textOpt)

    @override
    def sizeHintHeight(self, rect: QRect, index: QModelIndex | QPersistentModelIndex) -> int:
        imgSize = index.data(GalleryModel.ROLE_IMGSIZE)
        if imgSize is None:
            return self.DEFAULT_HEIGHT

        imgW, imgH = imgSize
        w = rect.width() - self.BORDER_SIZE - self.xSpacing
        h = round((imgH / imgW) * w)

        textW = w - self.BORDER_SIZE

        if self.caption.captionsEnabled:
            label = index.data(GalleryModel.ROLE_CAPTION)
            if label:
                textH, textLayouts = self.caption.layoutCaption(label, textW, self.TEXT_MAX_HEIGHT)
                h += round(textH) + self.TEXT_SPACING + self.BORDER_SIZE//2 + 2
        else:
            label = index.data(GalleryModel.ROLE_FILENAME)
            textRect = self.labelFontMetrics.boundingRect(0, 0, textW, self.TEXT_MAX_HEIGHT, self.textFlags, label)
            h += min(textRect.height(), self.TEXT_MAX_HEIGHT) + self.TEXT_SPACING + self.BORDER_SIZE//2 + 2

        return h



class GalleryListDelegate(BaseGalleryDelegate):
    TEXT_SPACING = 8

    def __init__(self, galleryView, galleryCaption: GalleryCaption):
        super().__init__(galleryView, galleryCaption)

        #self.textFlags = Qt.AlignmentFlag.AlignLeft
        self.textOpt = QtGui.QTextOption()
        self.textOpt.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.labelFontMetrics = QFontMetrics(QtGui.QFont())

    @override
    def itemWidth(self) -> int:
        return 800

    @override
    def spacing(self) -> int:
        return 10

    @override
    def paintItem(self, painter: QPainter, rect: QRect, index: QModelIndex | QPersistentModelIndex):
        x, y, w, h = rect.left(), rect.top(), rect.width(), rect.height()

        imgW = self.view.itemWidth
        pixmap = index.data(Qt.ItemDataRole.DecorationRole)
        if pixmap:
            painter.drawPixmap(x, y, imgW, h, pixmap)

        self.paintIcons(painter, x+4, y+4, index.data(GalleryModel.ROLE_ICONS))
        self.paintBorder(painter, x, y, w, h, index.data(GalleryModel.ROLE_SELECTION))

        x += imgW + self.TEXT_SPACING
        textW = rect.right() - self.BORDER_SIZE//2 - x
        textRect = QRect(x, y, textW, h)

        label = index.data(GalleryModel.ROLE_FILENAME)
        painter.drawText(textRect, label, self.textOpt)

    @override
    def sizeHintHeight(self, rect: QRect, index: QModelIndex | QPersistentModelIndex) -> int:
        size = index.data(GalleryModel.ROLE_IMGSIZE)
        if size is None:
            return self.DEFAULT_HEIGHT

        h = int((size[1] / size[0]) * self.view.itemWidth)
        return h
