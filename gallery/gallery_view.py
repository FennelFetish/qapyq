from collections import defaultdict
from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QSize, QPoint, QRect, QModelIndex, QPersistentModelIndex, QSignalBlocker, QTimer
from PySide6.QtGui import QFontMetrics, QPainter
from lib import colorlib, qtlib
from ui.tab import ImgTab
from .gallery_model import GalleryModel
from .gallery_header import GalleryHeader


class GalleryView(QtWidgets.QTableView):
    VIEW_MODE_GRID = "grid"
    VIEW_MODE_LIST = "list"

    def __init__(self, tab: ImgTab, initialItemWidth: int):
        super().__init__()
        self.tab = tab
        self.itemWidth = initialItemWidth

        self.delegate = None

        self.setShowGrid(False)
        self.setCornerButtonEnabled(False)

        self.horizontalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)

        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(200)
        #self.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.verticalHeader().setCascadingSectionResizes(False)

        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.verticalScrollBar().setSingleStep(1)
        self.verticalScrollBar().setPageStep(1)

        #self.setUpdateThreshold(100000)
        self.setUpdateThreshold(1000)


    def setViewMode(self, mode: str):
        with QSignalBlocker(self):
            self.setItemDelegate(None)
            if self.delegate:
                self.delegate.deleteLater()

            if mode == self.VIEW_MODE_GRID:
                self.delegate = GalleryGridDelegate(self)
            else:
                self.delegate = GalleryListDelegate(self)

            self.model().dataChanged.connect(self.delegate.onDataChanged)
            self.model().modelReset.connect(self.delegate.clearCache)
            self.setItemDelegate(self.delegate)

        self.updateWidth()


    def setItemWidth(self, width: int):
        if width != self.itemWidth:
            self.itemWidth = width
            self.updateWidth(force=True)

    @Slot()
    def updateWidth(self, force=False):
        totalWidth = self.parent().width() - self.verticalScrollBar().width() - 1
        numCols = max(1, totalWidth // self.delegate.itemWidth())

        if self.model().columnCount() != numCols:
            self.model().setNumColumns(numCols)
        elif force:
            self.model().modelReset.emit()

        # colWidth = totalWidth // numCols
        # for i in range(numCols):
        #     self.setColumnWidth(i, colWidth)

        self.delegate.clearCache()
        self.resizeRowsToContents()


    @Slot()
    def updateFolderRows(self):
        self.clearSpans()
        model: GalleryModel = self.model()
        numCols = model.columnCount()

        if numCols > 1:
            self.setSpan(0, 0, 1, numCols)
            for folder in model.headerItems:#[:-1]:
                self.setSpan(folder.endRow, 0, 1, numCols)
                self.openPersistentEditor(model.index(folder.row, 0))
                self.resizeRowToContents(folder.row) # TODO: Set fixed header height


    def scrollToRow(self, row: int):
        index = self.model().index(row, 0)
        self.scrollTo(index, self.ScrollHint.PositionAtTop)

    def scrollToFile(self, file: str):
        item = self.model().getFileItem(file)
        if item is not None:
            self.scrollToRow(item.pos.row)

    def getRowAtTop(self) -> int:
        index = self.indexAt(QPoint(0, 0))
        return index.row() if index.isValid() else -1

    def rowIsHeader(self, row: int) -> bool:
        index = self.model().index(row, 0)
        return index.data(GalleryModel.ROLE_TYPE) == GalleryModel.ItemType.Header


    # @override
    # def sizeHintForRow(self, row: int) -> int:
    #     if model := self.model():
    #         return model.rowHeights[row]
    #     return 0

    @override
    def wheelEvent(self, event: QtGui.QWheelEvent):
        index = self.indexAt(QPoint(0, 0))
        if index.isValid():
            row = index.row()
            delta = event.angleDelta().y()

            # Scroll up
            if delta > 0:
                if self.visualRect(index).y() == 0:
                    row -= 1
                if self.rowIsHeader(row - 1):
                    row -= 1

            # Scroll down
            elif delta < 0:
                row += 2 if self.rowIsHeader(row) else 1

            self.scrollToRow(row)

        event.accept()

    @override
    def model(self) -> GalleryModel:
        return super().model()



class BaseGalleryDelegate(QtWidgets.QStyledItemDelegate):
    SPACING = 6
    DEFAULT_HEIGHT = 200

    def __init__(self, galleryView: GalleryView):
        super().__init__()
        self.view = galleryView
        self._sizeCache = defaultdict(SizeHintRow)

        self.headerTextOpt = QtGui.QTextOption()
        self.headerTextOpt.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.headerFont = qtlib.getMonospaceFont()
        self.headerFont.setBold(True)
        self.headerFont.setPointSizeF(self.headerFont.pointSizeF() * 1.2)

        self.headerHeight = QtGui.QFontMetrics(self.headerFont).height() + 2*self.SPACING

        self.headerPen = QtGui.QPen(colorlib.BUBBLE_TEXT)
        self.headerBg = QtGui.QBrush(colorlib.BUBBLE_BG)

        self.editorPalette = None

    def itemWidth(self) -> int:
        return self.view.itemWidth


    @Slot()
    def onDataChanged(self, startIndex: QModelIndex, endIndex: QModelIndex, roles: list[int]):
        if Qt.ItemDataRole.SizeHintRole in roles:
            for row in range(startIndex.row(), endIndex.row()+1):
                self._sizeCache[row].reset()
                self.view.resizeRowToContents(row)
                #self.view.verticalHeader().resizeSection(row, 300)

        print(f"num rows cached: {len(self._sizeCache)}")


    @Slot()
    def clearCache(self):
        #print("clear size cache")
        self._sizeCache.clear()


    @override
    def paint(self, painter: QPainter, option: QtWidgets.QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        itemType = index.data(GalleryModel.ROLE_TYPE)
        if itemType is None:
            return

        painter.save()

        if itemType == GalleryModel.ItemType.Header:
            self.paintHeader(painter, option.rect, index)
        else:
            self.paintItem(painter, option.rect, index)

        painter.restore()

    def paintHeader(self, painter: QPainter, rect: QRect, index: QModelIndex | QPersistentModelIndex):
        painter.setBrush(self.headerBg)
        painter.fillRect(rect, self.headerBg)

        painter.setPen(self.headerPen)
        painter.setFont(self.headerFont)

        textRect = rect.adjusted(self.SPACING, 0, -200, 0)
        label = index.data(Qt.ItemDataRole.DisplayRole)
        painter.drawText(textRect, label, self.headerTextOpt)

    def paintItem(self, painter: QPainter, rect: QRect, index: QModelIndex | QPersistentModelIndex):
        raise NotImplementedError()


    @override
    def sizeHint(self, option: QtWidgets.QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        cacheRow = self._sizeCache[index.row()]
        if cacheRow.size is None or not cacheRow.hasCol(index.column()):

            itemType = index.data(GalleryModel.ROLE_TYPE)
            if itemType is None:
                size = QSize(0, 0)

            if itemType == GalleryModel.ItemType.Header:
                size = QSize(200, self.headerHeight)
            else:
                size = self.sizeHintItem(option.rect, index)

            cacheRow.setColSize(index.column(), size)
        # else:
        #     print("hint from cache")

        return cacheRow.size

    def sizeHintItem(self, rect: QRect, index: QModelIndex | QPersistentModelIndex) -> QSize:
        raise NotImplementedError()


    @override
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QtWidgets.QWidget:
        itemType = index.data(GalleryModel.ROLE_TYPE)
        if itemType == GalleryModel.ItemType.Header:
            header = GalleryHeader(parent, self.view.tab, index.data(Qt.ItemDataRole.DisplayRole))
            header.updateImageLabel(index.data(GalleryModel.ROLE_IMGCOUNT))
            return header

        return super().createEditor(parent, option, index)

    @override
    def setEditorData(self, editor: QtWidgets.QWidget, index: QModelIndex | QPersistentModelIndex):
        # if isinstance(editor, GalleryHeader):
        #     # editor.setText(index.data(Qt.ItemDataRole.DisplayRole))
        #     # QTimer.singleShot(0, lambda: editor.deselect())
        #editor.txtTitle.setText(index.data(Qt.ItemDataRole.DisplayRole))
        pass

    @override
    def setModelData(self, editor: QtWidgets.QWidget, model, index: QModelIndex | QPersistentModelIndex):
        # No-op to prevent any changes from being saved
        pass



class GalleryGridDelegate(BaseGalleryDelegate):
    TEXT_SPACING = 3
    TEXT_MAX_HEIGHT = 200

    def __init__(self, galleryView: GalleryView):
        super().__init__(galleryView)

        self.textFlags = Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWrapAnywhere
        self.textOpt = QtGui.QTextOption()
        self.textOpt.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.textOpt.setWrapMode(QtGui.QTextOption.WrapMode.WrapAnywhere)

        self.labelFontMetrics = QFontMetrics(QtGui.QFont())

    @override
    def paintItem(self, painter: QPainter, rect: QRect, index: QModelIndex | QPersistentModelIndex):
        x = rect.left() + self.SPACING
        y = rect.top() + self.SPACING
        w = rect.width() - self.SPACING*2

        pixmap = index.data(Qt.ItemDataRole.DecorationRole)
        if pixmap:
            ar = pixmap.height() / pixmap.width()
            imgH = round(ar * w)
            painter.drawPixmap(x, y, w, imgH, pixmap)
        else:
            imgH = 0

        y += imgH + self.TEXT_SPACING
        textHeight = rect.bottom() - self.SPACING - y
        textRect = QRect(x, y, w, textHeight)

        label = index.data(Qt.ItemDataRole.DisplayRole)
        painter.drawText(textRect, label, self.textOpt)

    @override
    def sizeHintItem(self, rect: QRect, index: QModelIndex | QPersistentModelIndex) -> QSize:
        size = index.data(GalleryModel.ROLE_IMGSIZE)
        if size is None:
            h = self.DEFAULT_HEIGHT if index.column() == 0 else 0
            return QSize(self.itemWidth(), h)

        w = rect.width()
        h = int((size[1] / size[0]) * w) + 2*self.SPACING

        label = index.data(Qt.ItemDataRole.DisplayRole)
        textRect = self.labelFontMetrics.boundingRect(0, 0, w, self.TEXT_MAX_HEIGHT, self.textFlags, label)
        h += min(textRect.height(), self.TEXT_MAX_HEIGHT)

        return QSize(w, h)



class GalleryListDelegate(BaseGalleryDelegate):
    TEXT_SPACING = 3

    def __init__(self, galleryView: GalleryView):
        super().__init__(galleryView)

        #self.textFlags = Qt.AlignmentFlag.AlignLeft
        self.textOpt = QtGui.QTextOption()
        self.textOpt.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.labelFontMetrics = QFontMetrics(QtGui.QFont())

    @override
    def itemWidth(self) -> int:
        return 800

    @override
    def paintItem(self, painter: QPainter, rect: QRect, index: QModelIndex | QPersistentModelIndex):
        x = rect.left() + self.SPACING
        y = rect.top() + self.SPACING
        h = rect.height() - self.SPACING*2

        imgW = self.view.itemWidth
        pixmap = index.data(Qt.ItemDataRole.DecorationRole)
        if pixmap:
            painter.drawPixmap(x, y, imgW, h, pixmap)

        x += imgW + self.TEXT_SPACING
        textWidth = rect.right() - self.TEXT_SPACING - x
        textRect = QRect(x, y, textWidth, h)

        label = index.data(Qt.ItemDataRole.DisplayRole)
        painter.drawText(textRect, label, self.textOpt)

    @override
    def sizeHintItem(self, rect: QRect, index: QModelIndex | QPersistentModelIndex) -> QSize:
        colWidth = self.itemWidth()
        size = index.data(GalleryModel.ROLE_IMGSIZE)
        if size is None:
            return QSize(colWidth, self.DEFAULT_HEIGHT)

        imgH = int((size[1] / size[0]) * self.view.itemWidth)
        h = imgH + 2*self.SPACING
        return QSize(colWidth, h)




class SizeHintRow:
    def __init__(self):
        self.size: QSize | None = None
        self.colMask = 0

    def hasCol(self, col: int) -> bool:
        return self.colMask & (1 << col) > 0

    def setColSize(self, col: int, size: QSize):
        self.colMask |= (1 << col)
        if self.size is None or size.height() > self.size.height():
            self.size = size

    def reset(self):
        self.size = None
        self.colMask = 0
