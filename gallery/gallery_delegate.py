from collections import defaultdict, OrderedDict
from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QSize, QPoint, QRect, QModelIndex, QPersistentModelIndex, QTimer, QSignalBlocker
from PySide6.QtGui import QFontMetrics, QPainter, QPixmap
from lib import colorlib, qtlib
from lib.filelist import DataKeys
from caption.caption_text import BorderlessNavigationTextEdit
from config import Config
from .gallery_caption import GalleryCaption, LayoutInfo
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
        self.xSpacing = round(totalSpacing / columnCount)


    def clearCache(self):
        self.sizeCache = defaultdict(SizeHintCacheRow)

    @Slot(QModelIndex, QModelIndex, list)
    def onDataChanged(self, startIndex: QModelIndex, endIndex: QModelIndex, roles: list[int]):
        resetSizeHint = self._onDataChanged(startIndex, endIndex, roles)

        if resetSizeHint or Qt.ItemDataRole.SizeHintRole in roles:
            for row in range(startIndex.row(), endIndex.row()+1):
                self.sizeCache[row].reset()
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
        filename = index.data(GalleryModel.ROLE_FILENAME)
        if filename is None:
            return

        if not self.fastRender:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)

        rect = self._adjustRect(option.rect, index.column())
        self.paintItem(painter, rect, index, filename)

    def paintItem(self, painter: QPainter, rect: QRect, index: QModelIndex | QPersistentModelIndex, filename: str):
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
        match itemType:
            case GalleryModel.ItemType.File:
                cacheRow = self.sizeCache[index.row()]
                if not cacheRow.hasColumn(index.column()):
                    if imgSize := index.data(GalleryModel.ROLE_IMGSIZE):
                        imgW, imgH = imgSize
                        h = self.sizeHintHeight(option.rect, index, imgW, imgH)
                        h += self.BORDER_SIZE + 2*self.spacing()
                    else:
                        h = int(self.view.itemWidth * 1.5)

                    cacheRow.setColumnHeight(index.column(), h)

                return cacheRow.size

            case GalleryModel.ItemType.Header:
                return QSize(0, self.HEADER_HEIGHT)

            case _:
                return QSize(0, 0)

    def sizeHintHeight(self, rect: QRect, index: QModelIndex | QPersistentModelIndex, imgW: int, imgH: int) -> int:
        raise NotImplementedError()


    @override
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QtWidgets.QWidget:
        path = index.data(GalleryModel.ROLE_FOLDERPATH)
        if path is not None:
            return GalleryHeader(parent, self.view.tab, path)
        return None

    @override
    def setEditorData(self, editor: QtWidgets.QWidget, index: QModelIndex | QPersistentModelIndex):
        if isinstance(editor, GalleryHeader):
            editor.updateImageLabel(index.data(GalleryModel.ROLE_IMGCOUNT))

    @override
    def setModelData(self, editor: QtWidgets.QWidget, model, index: QModelIndex | QPersistentModelIndex):
        pass  # No-op to prevent any changes from being saved



class GalleryGridDelegate(GalleryDelegate):
    TEXT_MAX_HEIGHT = 200
    TEXT_SPACING = 4
    TEXT_SPACING_BOTTOM = TEXT_SPACING + GalleryDelegate.BORDER_SIZE//2 + 2

    def __init__(self, galleryView, galleryCaption: GalleryCaption):
        super().__init__(galleryView, galleryCaption)

        self.layoutCache: OrderedDict[tuple[int, int], LayoutInfo] = OrderedDict()

        self.textFlags = Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWrapAnywhere
        self.textOpt = QtGui.QTextOption()
        self.textOpt.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.textOpt.setWrapMode(QtGui.QTextOption.WrapMode.WrapAnywhere)

        self.labelFontMetrics = QFontMetrics(QtGui.QFont())


    @Slot()
    def clearCache(self):
        self.layoutCache = OrderedDict()
        super().clearCache()

    def _onDataChanged(self, startIndex: QModelIndex, endIndex: QModelIndex, roles: list[int]) -> bool:
        if (Qt.ItemDataRole.SizeHintRole in roles) or (GalleryModel.ROLE_CAPTION in roles):
            for row in range(startIndex.row(), endIndex.row()+1):
                for col in range(startIndex.column(), endIndex.column()+1):
                    self.layoutCache.pop((row, col), None)
            return True

        return False


    def _getCaptionLayouts(self, w: int, h: int, index: QModelIndex | QPersistentModelIndex) -> LayoutInfo:
        # When a row consists of images with different aspect ratios, the tallest image+caption defines the row height.
        # The space available for each caption is different. Therefore, to always use all available vertical space,
        # don't cache and reuse the layout which was used to calculate the size hint,
        # but do full relayouting when the final row height becomes available in the first paintItem().

        key = (index.row(), index.column())
        layoutInfo = self.layoutCache.get(key)

        if layoutInfo is None:
            text = index.data(GalleryModel.ROLE_CAPTION)
            layoutInfo = self.caption.layoutCaption(text, w, h)

            self.layoutCache[key] = layoutInfo
            if len(self.layoutCache) > Config.galleryCacheSize:
                self.layoutCache.popitem(last=False)

        else:
            self.layoutCache.move_to_end(key)

        return layoutInfo


    @override
    def paintItem(self, painter: QPainter, rect: QRect, index: QModelIndex | QPersistentModelIndex, filename: str):
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

        if self.fastRender:
            return

        textX = x + self.BORDER_SIZE // 2
        textY = y + imgH + self.TEXT_SPACING
        textW = w - self.BORDER_SIZE
        textH = rect.bottom() - textY

        painter.setPen(pen)

        # Only load caption when thumbnail and final size hint is ready
        if self.caption.captionsEnabled and imgH > 0:
            p = QPoint(textX, textY)
            layoutInfo = self._getCaptionLayouts(textW, textH, index)
            for textLayout in layoutInfo.layouts:
                textLayout.draw(painter, p)
        else:
            textRect = QRect(textX, textY, textW, textH)
            painter.drawText(textRect, filename, self.textOpt)


    @override
    def sizeHintHeight(self, rect: QRect, index: QModelIndex | QPersistentModelIndex, imgW: int, imgH: int) -> int:
        w = rect.width() - self.BORDER_SIZE - self.xSpacing
        h = round((imgH / imgW) * w)

        textW = w - self.BORDER_SIZE

        if self.caption.captionsEnabled:
            text = index.data(GalleryModel.ROLE_CAPTION)
            layoutInfo = self.caption.layoutCaption(text, textW, self.TEXT_MAX_HEIGHT)
            if layoutInfo.height > 0:
                h += layoutInfo.height + self.TEXT_SPACING_BOTTOM
        else:
            label = index.data(GalleryModel.ROLE_FILENAME)
            textRect = self.labelFontMetrics.boundingRect(0, 0, textW, self.TEXT_MAX_HEIGHT, self.textFlags, label)
            h += min(textRect.height(), self.TEXT_MAX_HEIGHT) + self.TEXT_SPACING_BOTTOM

        return h



class GalleryListDelegate(GalleryDelegate):
    MIN_HEIGHT = 60
    LABEL_HEIGHT = 18
    TEXT_SPACING = 6

    def __init__(self, galleryView, galleryCaption: GalleryCaption):
        super().__init__(galleryView, galleryCaption)

        self.sizeUpdateTimer = QTimer(singleShot=True, interval=50)
        self.sizeUpdateTimer.timeout.connect(self.view.updateVisibleRows)

        self.textOpt = QtGui.QTextOption()
        self.textOpt.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)


    @override
    def itemWidth(self) -> int:
        return 800


    @override
    def _onDataChanged(self, startIndex: QModelIndex, endIndex: QModelIndex, roles: list[int]) -> bool:
        if Qt.ItemDataRole.SizeHintRole in roles:
            self.sizeUpdateTimer.start()
            return True
        return False

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
    def paintItem(self, painter: QPainter, rect: QRect, index: QModelIndex | QPersistentModelIndex, filename: str):
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

        if self.fastRender:
            return

        textRect = QRect(textX, textY, textW, textH)
        painter.setPen(pen)
        painter.drawText(textRect, filename, self.textOpt)

    @override
    def sizeHintHeight(self, rect: QRect, index: QModelIndex | QPersistentModelIndex, imgW: int, imgH: int) -> int:
        h = round((imgH / imgW) * self.view.itemWidth)
        return max(h, self.MIN_HEIGHT)


    @override
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QtWidgets.QWidget:
        if file := index.data(GalleryModel.ROLE_FILEPATH):
            edited = index.data(GalleryModel.ROLE_DOC_EDITED)
            return GalleryCaptionEditor(parent, self, file, edited)

        return super().createEditor(parent, option, index)

    @override
    def updateEditorGeometry(self, editor: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        if not isinstance(editor, GalleryCaptionEditor):
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
        if isinstance(editor, GalleryCaptionEditor):
            editor.updateData(index)
        else:
            super().setEditorData(editor, index)

    @override
    def setModelData(self, editor: QtWidgets.QWidget, model: GalleryModel, index: QModelIndex | QPersistentModelIndex):
        if isinstance(editor, GalleryCaptionEditor):
            model.setData(index, editor.edited, GalleryModel.ROLE_DOC_EDITED)



class GalleryCaptionEditor(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget, delegate: GalleryListDelegate, file: str, edited: bool):
        super().__init__(parent)
        self.delegate   = delegate
        self.file       = file
        self.edited     = edited
        self.selected   = False

        self._build()

        self._saveShortcut = QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Save, self, context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._saveShortcut.activated.connect(self.saveCaption)


    def _build(self):
        labelHeight = self.delegate.LABEL_HEIGHT

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0) # spacing moves the text field when showing the buttons
        layout.setColumnStretch(0, 1)
        layout.setColumnMinimumWidth(2, 4)

        row = 0
        layout.setRowMinimumHeight(row, labelHeight)

        self.btnSave = qtlib.SaveButton("Save")
        self.btnSave.setChanged(True)
        self.btnSave.setFixedHeight(labelHeight)
        self.btnSave.clicked.connect(self.saveCaption)
        layout.addWidget(self.btnSave, row, 1)

        self.btnReload = QtWidgets.QPushButton("Reload")
        self.btnReload.setFixedHeight(labelHeight)
        self.btnReload.clicked.connect(self.reloadCaption)
        layout.addWidget(self.btnReload, row, 3)

        if not self.edited:
            self.btnSave.hide()
            self.btnReload.hide()

        row += 1
        layout.setRowMinimumHeight(row, 4)

        row += 1
        layout.setRowStretch(row, 1)

        caption = self.delegate.caption
        self.txtCaption = BorderlessNavigationTextEdit(caption.separator, caption.autoCompleteSources)
        self.txtCaption.setActivePalette(True)
        self.txtCaption.textChanged.connect(self._onCaptionChanged)
        layout.addWidget(self.txtCaption, row, 0, 1, 4, Qt.AlignmentFlag.AlignTop)

        self.setLayout(layout)


    def updateData(self, index: QModelIndex | QPersistentModelIndex):
        self.txtCaption.separator = self.delegate.caption.separator

        doc = index.data(GalleryModel.ROLE_CAPTION_DOC)
        if doc is not self.txtCaption.document():
            with QSignalBlocker(self.txtCaption):
                self.txtCaption.setDocument(doc)
                self.txtCaption.moveCursor(QtGui.QTextCursor.MoveOperation.End)

        QTimer.singleShot(0, self._updateHighlight)

        selection = index.data(GalleryModel.ROLE_SELECTION)
        selected = (selection == SelectionState.Primary)
        if self.selected != selected:
            self.selected = selected
            if selected:
                self.takeFocus()
            else:
                cursor = self.txtCaption.textCursor()
                cursor.clearSelection()
                self.txtCaption.setTextCursor(cursor)


    def setEdited(self, edited: bool):
        self.btnSave.setVisible(edited)
        self.btnReload.setVisible(edited)

        self.edited = edited
        self.delegate.commitData.emit(self)

    @Slot()
    def _onCaptionChanged(self):
        self.setEdited(True)
        self._updateHighlight()

    @Slot()
    def _updateHighlight(self):
        cap = self.delegate.caption
        if cap.captionHighlight:
            text = self.txtCaption.toPlainText()
            cap.captionHighlight.highlight(text, cap.separator, self.txtCaption)


    @Slot()
    def reloadCaption(self):
        index = self.delegate.view.model().getFileIndex(self.file)
        if index.isValid():
            text = index.data(GalleryModel.ROLE_CAPTION)
            with QSignalBlocker(self.txtCaption):
                self.txtCaption.setCaption(text)
            self.setEdited(False)
            self._updateHighlight()

    @Slot()
    def saveCaption(self):
        text = self.txtCaption.rstripCaption()
        if self.delegate.caption.captionSrc.saveCaption(self.file, text):
            self.delegate.view.tab.filelist.setData(self.file, DataKeys.CaptionState, DataKeys.IconStates.Saved)
            self.setEdited(False)


    def takeFocus(self):
        self.txtCaption.setFocus()
        self.txtCaption.moveCursor(QtGui.QTextCursor.MoveOperation.End)
