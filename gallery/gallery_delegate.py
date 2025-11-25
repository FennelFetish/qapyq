from collections import defaultdict, OrderedDict
from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QSize, QPoint, QRect, QModelIndex, QPersistentModelIndex, QTimer, QSignalBlocker
from PySide6.QtGui import QFontMetrics, QPainter, QPixmap
from lib import colorlib, qtlib
from lib.filelist import DataKeys
from caption.caption_text import NavigationTextEdit
from config import Config
from .gallery_caption import GalleryCaption
from .gallery_model import GalleryModel, SelectionState
from .gallery_header import GalleryHeader


class SizeHintCacheRow:
    __slots__ = ('size', 'colMask')

    def __init__(self):
        self.size: QSize | None = None
        self.colMask = 0

    def hasColumn(self, col: int) -> bool:
        return self.colMask & (1 << col) > 0

    def setColumnHeight(self, col: int, height: int):
        self.colMask |= (1 << col)
        if self.size is None or height > self.size.height():
            self.size = QSize(0, height)

    def reset(self):
        self.size = None
        self.colMask = 0



class GalleryDelegate(QtWidgets.QStyledItemDelegate):
    HEADER_HEIGHT = 32

    BORDER_SIZE = 6
    BORDER_SIZE_SECONDARY = 3


    def __init__(self, galleryView, galleryCaption: GalleryCaption):
        super().__init__(galleryView)
        self.sizeCache = defaultdict(SizeHintCacheRow)
        self.fastRender = False

        self.numColumns = 1
        self.xSpacing = 0

        from .gallery_view import GalleryView
        self.view: GalleryView = galleryView
        self.caption = galleryCaption

        self._initIcons()
        self._initPens()

    def _initIcons(self):
        self.icons = {
            DataKeys.CaptionState:  QtGui.QPixmap("./res/icon_caption.png"),
            DataKeys.CropState:     QtGui.QPixmap("./res/icon_crop.png"),
            DataKeys.MaskState:     QtGui.QPixmap("./res/icon_mask.png")
        }

        colorWhite = QtGui.QColor(230, 230, 230)
        colorGreen = QtGui.QColor(50, 180, 60)
        colorRed   = QtGui.QColor(250, 70, 30)
        self.iconColors = {
            DataKeys.IconStates.Exists:     (QtGui.QPen(colorWhite), QtGui.QBrush(colorWhite)),
            DataKeys.IconStates.Saved:      (QtGui.QPen(colorGreen), QtGui.QBrush(colorGreen)),
            DataKeys.IconStates.Changed:    (QtGui.QPen(colorRed),   QtGui.QBrush(colorRed)),
        }

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

        highlightBg = QtGui.QColor(selectionColor)
        highlightBg.setAlphaF(0.25)
        self.BRUSH_HIGHLIGHT_BG = QtGui.QBrush(highlightBg)
        self.BRUSH_HIGHLIGHT = QtGui.QBrush(selectionColor)


    def itemWidth(self) -> int:
        return self.view.itemWidth

    def spacing(self) -> int:
        return 4


    def rowNeedsEditor(self, isHeader: bool):
        return isHeader

    def openRowEditors(self, row: int):
        self.view.openPersistentEditor(self.view.model().index(row, 0))

    def closeRowEditors(self, row: int):
        self.view.closePersistentEditor(self.view.model().index(row, 0))


    def setNumColumns(self, columnCount: int):
        self.numColumns = columnCount
        totalSpacing = self.spacing() * (columnCount-1)
        self.xSpacing = totalSpacing // columnCount


    def clearCache(self):
        self.sizeCache.clear()

    @Slot(QModelIndex, QModelIndex, list)
    def onDataChanged(self, startIndex: QModelIndex, endIndex: QModelIndex, roles: list[int]):
        resetSizeHint = self._onDataChanged(startIndex, endIndex, roles)

        if resetSizeHint or Qt.ItemDataRole.SizeHintRole in roles:
            for row in range(startIndex.row(), endIndex.row()+1):
                self.sizeCache[row].reset()

                # for col in range(startIndex.column(), endIndex.column()+1):
                #     self.sizeHintChanged.emit(self.view.model().index(row, col))

                self.view.resizeRowToContents(row)

    def _onDataChanged(self, startIndex: QModelIndex, endIndex: QModelIndex, roles: list[int]) -> bool:
        return False


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

        if not self.fastRender:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)

        rect = self._adjustRect(option.rect, index.column())
        self.paintItem(painter, rect, index)

    def paintItem(self, painter: QPainter, rect: QRect, index: QModelIndex | QPersistentModelIndex):
        raise NotImplementedError()

    def paintHightlightBg(self, painter: QtGui.QPainter, x: int, y: int, w: int, h: int):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.BRUSH_HIGHLIGHT_BG)
        painter.drawRect(x, y, w, h)

    def paintHighlight(self, painter: QtGui.QPainter, x: int, y: int, w: int, h: int):
        w += x
        h += y
        s = 32

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.BRUSH_HIGHLIGHT)

        painter.drawConvexPolygon((QPoint(x, y), QPoint(x+s, y), QPoint(x, y+s))) # Top left
        painter.drawConvexPolygon((QPoint(w, y), QPoint(w, y+s), QPoint(w-s, y))) # Top right
        painter.drawConvexPolygon((QPoint(x, h), QPoint(x, h-s), QPoint(x+s, h))) # Bottom left
        painter.drawConvexPolygon((QPoint(w, h), QPoint(w-s, h), QPoint(w, h-s))) # Bottom right

    def paintBorder(self, painter: QtGui.QPainter, x: int, y: int, w: int, h: int, selectionState: int):
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if selectionState == SelectionState.Primary:
            painter.setPen(self.PEN_PRIMARY)
            painter.drawRect(x, y, w, h)
        elif selectionState == SelectionState.Secondary:
            painter.setPen(self.PEN_SECONDARY)
            painter.drawRect(x, y, w, h)

    def paintIcons(self, painter: QtGui.QPainter, x, y, icons: dict[str, DataKeys.IconStates]):
        sizeX, sizeY = 20, 20
        for iconKey, iconState in sorted(icons.items(), key=lambda item: item[0]):
            pen, brush = self.iconColors[iconState]
            painter.setPen(pen)
            painter.setBrush(brush)

            painter.drawRoundedRect(x, y, sizeX, sizeY, 3, 3)
            painter.drawPixmap(x, y, sizeX, sizeY, self.icons[iconKey])
            x += sizeX + 8


    @override
    def sizeHint(self, option: QtWidgets.QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        itemType = index.data(GalleryModel.ROLE_TYPE)
        if itemType == GalleryModel.ItemType.Header:
            return QSize(0, self.HEADER_HEIGHT)
        if itemType != GalleryModel.ItemType.File:
            return QSize(0, 0)

        cacheRow = self.sizeCache[index.row()]
        if not cacheRow.hasColumn(index.column()):
            h = self.sizeHintHeight(option.rect, index)
            h += self.BORDER_SIZE + 2*self.spacing()
            cacheRow.setColumnHeight(index.column(), h)

        return cacheRow.size

    def sizeHintHeight(self, rect: QRect, index: QModelIndex | QPersistentModelIndex) -> int:
        raise NotImplementedError()


    @override
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QtWidgets.QWidget:
        itemType = index.data(GalleryModel.ROLE_TYPE)
        if itemType == GalleryModel.ItemType.Header:
            return GalleryHeader(parent, self.view.tab, index.data(Qt.ItemDataRole.DisplayRole))
        return None

    @override
    def setEditorData(self, editor: QtWidgets.QWidget, index: QModelIndex | QPersistentModelIndex):
        if isinstance(editor, GalleryHeader):
            editor.updateImageLabel(index.data(GalleryModel.ROLE_IMGCOUNT))

    @override
    def setModelData(self, editor: QtWidgets.QWidget, model, index: QModelIndex | QPersistentModelIndex):
        pass  # No-op to prevent any changes from being saved



class GalleryGridDelegate(GalleryDelegate):
    TEXT_SPACING = 4
    TEXT_MAX_HEIGHT = 200

    def __init__(self, galleryView, galleryCaption: GalleryCaption):
        super().__init__(galleryView, galleryCaption)

        self.layoutCache = OrderedDict[tuple[int, int], tuple[QtGui.QTextLayout, ...]]()

        self.textFlags = Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWrapAnywhere
        self.textOpt = QtGui.QTextOption()
        self.textOpt.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.textOpt.setWrapMode(QtGui.QTextOption.WrapMode.WrapAnywhere)

        self.labelFontMetrics = QFontMetrics(QtGui.QFont())


    @Slot()
    def clearCache(self):
        self.layoutCache.clear()
        super().clearCache()

    def _onDataChanged(self, startIndex: QModelIndex, endIndex: QModelIndex, roles: list[int]) -> bool:
        if (GalleryModel.ROLE_CAPTION in roles) or (Qt.ItemDataRole.SizeHintRole in roles):
            for row in range(startIndex.row(), endIndex.row()+1):
                for col in range(startIndex.column(), endIndex.column()+1):
                    self.layoutCache.pop((row, col), None)
            return True

        return False


    def _getCaptionLayouts(self, w: int, h: int, index: QModelIndex | QPersistentModelIndex) -> tuple[QtGui.QTextLayout, ...]:
        key = (index.row(), index.column())
        textLayouts = self.layoutCache.get(key)

        if textLayouts is None:
            if label := index.data(GalleryModel.ROLE_CAPTION):
                textLayouts = tuple(self.caption.layoutCaption(label, w, h)[1])
            else:
                textLayouts = ()
            self.layoutCache[key] = textLayouts

            if len(self.layoutCache) > Config.galleryCacheSize:
                self.layoutCache.popitem(last=False)

        else:
            self.layoutCache.move_to_end(key)

        return textLayouts


    @override
    def paintItem(self, painter: QPainter, rect: QRect, index: QModelIndex | QPersistentModelIndex):
        x, y, w, h = rect.left(), rect.top(), rect.width(), rect.height()

        pen = self.PEN_TEXT
        imgH = 0

        pixmap: QPixmap | None = index.data(Qt.ItemDataRole.DecorationRole)
        if pixmap is not None:
            if pixmap.isNull():
                pen = self.PEN_TEXT_ERROR
            else:
                imgH = round((pixmap.height() / pixmap.width()) * w)
                painter.drawPixmap(x, y, w, imgH, pixmap)

        if index.data(GalleryModel.ROLE_HIGHLIGHT):
            self.paintHightlightBg(painter, x, y+imgH, w, h-imgH)
            self.paintHighlight(painter, x, y, w, imgH)

        self.paintIcons(painter, x+4, y+4, index.data(GalleryModel.ROLE_ICONS))
        self.paintBorder(painter, x, y, w, h, index.data(GalleryModel.ROLE_SELECTION))

        textX = x + self.BORDER_SIZE // 2
        textY = y + imgH + self.TEXT_SPACING
        textW = w - self.BORDER_SIZE
        textH = rect.bottom() - textY

        painter.setPen(pen)
        if self.caption.captionsEnabled and pen is not self.PEN_TEXT_ERROR:
            p = QPoint(textX, textY)
            for textLayout in self._getCaptionLayouts(textW, textH, index):
                textLayout.draw(painter, p)
        else:
            label = index.data(GalleryModel.ROLE_FILENAME)
            textRect = QRect(textX, textY, textW, textH)
            painter.drawText(textRect, label, self.textOpt)


    @override
    def sizeHintHeight(self, rect: QRect, index: QModelIndex | QPersistentModelIndex) -> int:
        imgSize = index.data(GalleryModel.ROLE_IMGSIZE)
        if imgSize is None:
            return self.view.itemWidth

        imgW, imgH = imgSize
        w = rect.width() - self.BORDER_SIZE - self.xSpacing
        h = round((imgH / imgW) * w)

        textW = w - self.BORDER_SIZE

        if self.caption.captionsEnabled:
            label = index.data(GalleryModel.ROLE_CAPTION)
            if label:
                textH, _ = self.caption.layoutCaption(label, textW, self.TEXT_MAX_HEIGHT)
                h += round(textH) + self.TEXT_SPACING + self.BORDER_SIZE//2 + 2
        else:
            label = index.data(GalleryModel.ROLE_FILENAME)
            textRect = self.labelFontMetrics.boundingRect(0, 0, textW, self.TEXT_MAX_HEIGHT, self.textFlags, label)
            h += min(textRect.height(), self.TEXT_MAX_HEIGHT) + self.TEXT_SPACING + self.BORDER_SIZE//2 + 2

        return h



class GalleryListDelegate(GalleryDelegate):
    MIN_HEIGHT = 60
    LABEL_HEIGHT = 18
    TEXT_SPACING = 6

    def __init__(self, galleryView, galleryCaption: GalleryCaption):
        super().__init__(galleryView, galleryCaption)

        self.textOpt = QtGui.QTextOption()
        self.textOpt.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self.labelFontMetrics = QFontMetrics(QtGui.QFont())


    @override
    def itemWidth(self) -> int:
        return 800


    @override
    def rowNeedsEditor(self, isHeader: bool):
        return True

    @override
    def openRowEditors(self, row: int):
        for col in range(self.numColumns):
            self.view.openPersistentEditor(self.view.model().index(row, col))

    @override
    def closeRowEditors(self, row: int):
        for col in range(self.numColumns):
            self.view.closePersistentEditor(self.view.model().index(row, col))


    @override
    def paintItem(self, painter: QPainter, rect: QRect, index: QModelIndex | QPersistentModelIndex):
        x, y, w, h = rect.left(), rect.top(), rect.width(), rect.height()

        pen = self.PEN_TEXT
        imgW = self.view.itemWidth
        imgH = 0

        pixmap: QPixmap | None = index.data(Qt.ItemDataRole.DecorationRole)
        if pixmap is not None:
            if pixmap.isNull():
                pen = self.PEN_TEXT_ERROR
            else:
                imgH = round((pixmap.height() / pixmap.width()) * imgW)
                painter.drawPixmap(x, y, imgW, imgH, pixmap)

        textX = x + imgW + self.TEXT_SPACING
        textY = y - self.BORDER_SIZE//2
        textW = rect.right() - textX
        textH = self.LABEL_HEIGHT + 2

        if index.data(GalleryModel.ROLE_HIGHLIGHT):
            self.paintHightlightBg(painter, textX, textY, textW, textH)
            self.paintHighlight(painter, x, y, imgW, imgH)

        self.paintIcons(painter, x+4, y+4, index.data(GalleryModel.ROLE_ICONS))
        self.paintBorder(painter, x, y, imgW, h, index.data(GalleryModel.ROLE_SELECTION))

        label = index.data(GalleryModel.ROLE_FILENAME)
        textRect = QRect(textX, textY, textW, textH)
        painter.setPen(pen)
        painter.drawText(textRect, label, self.textOpt)

    @override
    def sizeHintHeight(self, rect: QRect, index: QModelIndex | QPersistentModelIndex) -> int:
        imgSize = index.data(GalleryModel.ROLE_IMGSIZE)
        if imgSize is None:
            return self.view.itemWidth

        imgW, imgH = imgSize
        h = int((imgH / imgW) * self.view.itemWidth)
        return max(h, self.MIN_HEIGHT)


    @override
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QtWidgets.QWidget:
        itemType = index.data(GalleryModel.ROLE_TYPE)
        if itemType == GalleryModel.ItemType.File:
            return GalleryListItem(parent, self, index)
        return super().createEditor(parent, option, index)

    @override
    def updateEditorGeometry(self, editor: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        if not isinstance(editor, GalleryListItem):
            super().updateEditorGeometry(editor, option, index)
            return

        rowSize = self.sizeHint(option, index)
        rect = QRect(option.rect)
        rect.setHeight(rowSize.height())
        rect = self._adjustRect(rect, index.column())

        h = rect.height() - self.LABEL_HEIGHT - self.BORDER_SIZE//2
        editor.txtCaption.setFixedHeight(max(h, 0))

        x = self.view.itemWidth + self.TEXT_SPACING
        rect.adjust(x, 0, 0, 0)
        editor.setGeometry(rect)

    @override
    def setEditorData(self, editor: QtWidgets.QWidget, index: QModelIndex | QPersistentModelIndex):
        if isinstance(editor, GalleryListItem):
            editor.updateData(index)
        else:
            super().setEditorData(editor, index)

    @override
    def setModelData(self, editor: QtWidgets.QWidget, model: GalleryModel, index: QModelIndex | QPersistentModelIndex):
        if isinstance(editor, GalleryListItem):
            value = editor.caption if editor.edited else None
            model.setData(index, value, GalleryModel.ROLE_CAPTION_EDIT)



class GalleryListItem(QtWidgets.QWidget):
    TEXT_PALETTE = None

    def __init__(self, parent: QtWidgets.QWidget, delegate: GalleryListDelegate, index: QModelIndex | QPersistentModelIndex):
        super().__init__(parent)
        self.delegate = delegate
        self.file     = index.data(Qt.ItemDataRole.DisplayRole)
        self.edited   = False
        self.selected = False

        self._build()

    def _build(self):
        labelHeight = self.delegate.LABEL_HEIGHT

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0) # spacing moves the text field when showing the buttons
        layout.setColumnStretch(0, 1)
        layout.setColumnMinimumWidth(2, 4)

        row = 0
        layout.setRowMinimumHeight(row, labelHeight)

        self.btnSave = QtWidgets.QPushButton("Save")
        self.btnSave.clicked.connect(self.saveCaption)
        self.btnSave.setFixedHeight(labelHeight)
        self.btnSave.hide()
        layout.addWidget(self.btnSave, row, 1)

        self.btnReload = QtWidgets.QPushButton("Reload")
        self.btnReload.clicked.connect(self.reloadCaption)
        self.btnReload.setFixedHeight(labelHeight)
        self.btnReload.hide()
        layout.addWidget(self.btnReload, row, 3)

        row += 1
        layout.setRowMinimumHeight(row, 4)

        row += 1
        layout.setRowStretch(row, 1)

        self.txtCaption = NavigationTextEdit(self.delegate.caption.separator)
        qtlib.setMonospace(self.txtCaption)
        qtlib.setShowWhitespace(self.txtCaption)
        self.txtCaption.textChanged.connect(self._onCaptionChanged)
        self.txtCaption.setFrameStyle(QtWidgets.QFrame.Shape.NoFrame)
        layout.addWidget(self.txtCaption, row, 0, 1, 4, Qt.AlignmentFlag.AlignTop)

        if GalleryListItem.TEXT_PALETTE is None:
            GalleryListItem.TEXT_PALETTE = self._initPalette(self.txtCaption)
        self.txtCaption.setPalette(GalleryListItem.TEXT_PALETTE)

        self.setLayout(layout)

    @staticmethod
    def _initPalette(widget: QtWidgets.QWidget):
        palette = widget.palette()

        bgColor = palette.color(QtGui.QPalette.ColorRole.Base).toHsv()
        h, s, v = bgColor.hueF(), bgColor.saturationF(), bgColor.valueF()
        v *= 0.87 if colorlib.DARK_THEME else 0.92
        bgColor.setHsvF(h, s, v)
        palette.setColor(QtGui.QPalette.ColorRole.Base, bgColor)
        return palette


    @property
    def caption(self) -> str:
        return self.txtCaption.getCaption()


    def updateData(self, index: QModelIndex | QPersistentModelIndex):
        self.txtCaption.separator = self.delegate.caption.separator

        if not self.edited:
            text = index.data(GalleryModel.ROLE_CAPTION_EDIT)
            if text is not None:
                self._setEdited(True)
            else:
                text = index.data(GalleryModel.ROLE_CAPTION)
                self._setEdited(False)

            with QSignalBlocker(self.txtCaption):
                self.txtCaption.setCaption(text)

            if not self.edited:
                # TODO: Undo stack is cleared everytime the editor is destroyed when going out of view.
                # Cache widgets instead.
                self.txtCaption.document().clearUndoRedoStacks()

            QTimer.singleShot(0, self._updateHighlight)

        selection = index.data(GalleryModel.ROLE_SELECTION)
        selected = (selection == SelectionState.Primary)
        if not self.selected and selected:
            self.takeFocus()
        self.selected = selected


    def _setEdited(self, edited: bool):
        self.edited = edited
        self.btnSave.setVisible(edited)
        self.btnReload.setVisible(edited)

    @Slot()
    def _onCaptionChanged(self):
        self._setEdited(True)
        self.delegate.commitData.emit(self)
        self._updateHighlight()

    @Slot()
    def _updateHighlight(self):
        cap = self.delegate.caption
        if cap.captionHighlight:
            text = self.txtCaption.toPlainText()
            cap.captionHighlight.highlight(text, cap.separator, self.txtCaption)


    @Slot()
    def reloadCaption(self):
        self._setEdited(False)
        self.delegate.commitData.emit(self)

    @Slot()
    def saveCaption(self):
        if self.delegate.caption.captionSrc.saveCaption(self.file, self.caption):
            self.delegate.view.tab.filelist.setData(self.file, DataKeys.CaptionState, DataKeys.IconStates.Saved)
            self._setEdited(False)
            self.delegate.commitData.emit(self)


    def takeFocus(self):
        self.txtCaption.setFocus()
        self.txtCaption.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.matches(QtGui.QKeySequence.StandardKey.Save) and self.txtCaption.hasFocus():
            self.saveCaption()
            event.accept()
            return
        return super().keyPressEvent(event)
