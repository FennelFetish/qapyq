import os
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import QSize, Qt, Signal
from lib.filelist import DataKeys
import lib.qtlib as qtlib
from .thumbnail_cache import ThumbnailCache
from config import Config

# TODO: RowView with captions

class ImageIcon:
    Caption = "caption"
    Crop = "crop"
    Mask = "mask"

DATA_ICONS = {
    DataKeys.CaptionState: ImageIcon.Caption,
    DataKeys.CropState: ImageIcon.Crop,
    DataKeys.MaskState: ImageIcon.Mask
}


class GalleryGrid(QtWidgets.QWidget):
    headersUpdated = Signal(dict)
    fileChanged = Signal(object, int)
    reloaded = Signal()

    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.filelist = tab.filelist
        self.fileItems = {}

        self.icons = {
            ImageIcon.Caption: QtGui.QPixmap("./res/icon_caption.png"),
            ImageIcon.Crop: QtGui.QPixmap("./res/icon_crop.png"),
            ImageIcon.Mask: QtGui.QPixmap("./res/icon_mask.png")
        }

        colorWhite = QtGui.QColor(230, 230, 230)
        colorGreen = QtGui.QColor(50, 180, 60)
        colorRed   = QtGui.QColor(250, 70, 30)
        self.iconStates = {
            DataKeys.IconStates.Exists: (QtGui.QPen(colorWhite), QtGui.QBrush(colorWhite)),
            DataKeys.IconStates.Saved: (QtGui.QPen(colorGreen), QtGui.QBrush(colorGreen)),
            DataKeys.IconStates.Changed: (QtGui.QPen(colorRed), QtGui.QBrush(colorRed)),
        }

        self.columns = 4

        self._selectedItem = None
        self._selectedCompare = None
        self._ignoreFileChange = False

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.setLayout(layout)


    def freeLayout(self) -> dict:
        galleryItems = dict()
        layout = self.layout()
        for i in reversed(range(layout.count())):
            item = layout.takeAt(i)
            if widget := item.widget():
                if isinstance(widget, GalleryGridItem):
                    galleryItems[widget.file] = widget
                else:
                    widget.deleteLater()
            else:
                item.spacerItem().deleteLater()

        return galleryItems

    def reloadImages(self):
        self.fileItems = dict()
        self._selectedItem = None
        self._selectedCompare = None

        existingItems = self.freeLayout()
        headers = dict()

        currentDir = ""
        row, col = 0, 0
        for file in self.filelist.getFiles():
            if (dirname := os.path.dirname(file)) != currentDir:
                if col > 0:
                    row += 1
                    col = 0
                currentDir = dirname
                self.addHeader(dirname, row)
                headers[dirname] = row
                row += 1

            if not (galleryItem := existingItems.pop(file, None)):
                galleryItem = GalleryGridItem(self, file)
            
            self.addImage(galleryItem, file, row, col)
            col += 1
            if col >= self.columns:
                col = 0
                row += 1

        for widget in existingItems.values():
            widget.deleteLater()

        self.headersUpdated.emit(headers)
    
    def addImage(self, galleryItem, file, row, col):
        galleryItem.row = row
        self.fileItems[file] = galleryItem

        self.layout().addWidget(galleryItem, row, col, Qt.AlignTop)

        if self.filelist.getCurrentFile() == file:
            self._selectedItem = galleryItem
            galleryItem.selected = True
        else:
            galleryItem.selected = False

        if (compareTool := self.tab.getTool("compare")) and compareTool.compareFile == file:
            self._selectedCompare = galleryItem
            galleryItem.setCompare(True)
        else:
            galleryItem.setCompare(False)

    def addHeader(self, text, row):
        label = QtWidgets.QLabel(text)
        qtlib.setMonospace(label, 1.2, bold=True)
        label.setContentsMargins(4, 4, 4, 4)

        palette = QtWidgets.QApplication.palette()
        colorFg = palette.color(QtGui.QPalette.ColorRole.BrightText).name()
        label.setStyleSheet(f"color: {colorFg}; background-color: #161616")
        self.layout().addWidget(label, row, 0, 1, self.columns)


    def setSelectedItem(self, item, updateFileList=False):
        if self._selectedItem:
            self._selectedItem.selected = False
        item.selected = True
        self._selectedItem = item

        self.fileChanged.emit(item, item.row)

        if updateFileList:
            try:
                self._ignoreFileChange = True
                self.filelist.setCurrentFile(item.file)
            finally:
                self._ignoreFileChange = False

    def setSelectedCompare(self, item):
        if self._selectedCompare:
            self._selectedCompare.setCompare(False)
        item.setCompare(True)
        self._selectedCompare = item

    def adjustGrid(self):
        layout = self.layout()
        cols = int(self.width() // (ThumbnailCache.THUMBNAIL_SIZE+layout.spacing()))
        cols = max(cols, 1)
        if cols == self.columns:
            return
        self.columns = cols
        
        items = []
        for i in reversed(range(layout.count())):
            items.append(layout.takeAt(i))

        headers = dict()
        row, col = 0, 0
        for widget in (item.widget() for item in reversed(items)):
            if isinstance(widget, GalleryGridItem):
                widget.row = row
                layout.addWidget(widget, row, col, Qt.AlignTop)
                col += 1
                if col >= cols:
                    row += 1
                    col = 0
            else:
                if col > 0:
                    row += 1
                    col = 0
                layout.addWidget(widget, row, 0, 1, cols)
                headers[widget.text()] = row
                row += 1
        
        layout.update()
        self.headersUpdated.emit(headers)


    def getRowForY(self, y, compareBottom=False):
        layout = self.layout()
        row = 0
        while (rect := layout.cellRect(row, 0)).isValid():
            itemY = rect.bottom() if compareBottom else rect.top()
            if itemY < y:
                row += 1
            else:
                break
        return row

    def getYforRow(self, row, skipDownwards=False):
        layout = self.layout()
        rect = layout.cellRect(row, 0)
        if not rect.isValid():
            return -1

        # Check for header above current row
        rectAbove = layout.cellRect(row-1, 0)
        if rectAbove.height() < 100 and rectAbove.isValid():
            if skipDownwards:
                row += 1
                rect = layout.cellRect(row, 0)
            else:
                row -= 1
                rect = rectAbove
        
        y = rect.top()
        for col in range(1, self.columns):
            if (rect := layout.cellRect(row, col)).isValid():
                y = min(y, rect.top())
        return y


    def onFileChanged(self, currentFile):
        if not self._ignoreFileChange:
            widget = self.fileItems[currentFile]
            self.setSelectedItem(widget)
    
    def onFileListChanged(self, currentFile):
        # When files were appended, the selection is kept
        # and the gallery should scroll to the selection instead of the top
        if (selectedItem := self._selectedItem) and selectedItem.file != currentFile:
            selectedItem = None

        self.reloadImages()
        if selectedItem:
            self.fileChanged.emit(selectedItem, selectedItem.row)
        else:
            self.reloaded.emit()

    def onFileDataChanged(self, file, key):
        if not (icon := DATA_ICONS.get(key)):
            return

        if not (widget := self.fileItems.get(file)):
            return

        if iconState := self.filelist.getData(file, key):
            widget.setIcon(icon, iconState)
        else:
            widget.removeIcon(icon)
        widget.update()



class GalleryGridItem(QtWidgets.QWidget):
    SelectionPrimary = 1
    SelectionCompare = 2

    def __init__(self, gallery, file):
        super().__init__()
        self.gallery = gallery
        self.file = file
        self.row = -1
        
        self._pixmap = None
        self.filename = os.path.basename(file)
        self.selectionStyle: int = 0
        self.icons = {}

        self._height = 32
        self.setMinimumSize(32, 32)

        self._checkIcons(file)

    def _checkIcons(self, file):
        filelist = self.gallery.filelist

        if captionState := filelist.getData(file, DataKeys.CaptionState):
            self.setIcon(ImageIcon.Caption, captionState)
        else:
            filenameNoExt, ext = os.path.splitext(self.file)
            captionFile = filenameNoExt + ".txt"
            if os.path.exists(captionFile):
                self.setIcon(ImageIcon.Caption, DataKeys.IconStates.Exists)

        if cropState := filelist.getData(file, DataKeys.CropState):
            self.setIcon(ImageIcon.Crop, cropState)
        
        if maskState := filelist.getData(file, DataKeys.MaskState):
            self.setIcon(ImageIcon.Mask, maskState)
        else:
            filenameNoExt, ext = os.path.splitext(self.file)
            maskFile = f"{filenameNoExt}{Config.maskSuffix}.png"
            if os.path.exists(maskFile):
                self.setIcon(ImageIcon.Mask, DataKeys.IconStates.Exists)

    def setIcon(self, key, state):
        self.icons[key] = state

    def removeIcon(self, key):
        if key in self.icons:
            del self.icons[key]

    def sizeHint(self):
        return QSize(ThumbnailCache.THUMBNAIL_SIZE, self._height)

    @property
    def pixmap(self):
        return self._pixmap
    
    @pixmap.setter
    def pixmap(self, pixmap):
        self._pixmap = pixmap
        w = pixmap.width()
        h = pixmap.height()
        self._height = h
        self.update()

    @property
    def selected(self) -> bool:
        return self.selectionStyle & GalleryGridItem.SelectionPrimary

    @selected.setter
    def selected(self, selected) -> None:
        if selected:
            self.selectionStyle |= GalleryGridItem.SelectionPrimary
        else:
            self.selectionStyle &= ~GalleryGridItem.SelectionPrimary
        self.update()

    def setCompare(self, selected):
        if selected:
            self.selectionStyle |= GalleryGridItem.SelectionCompare
        else:
            self.selectionStyle &= ~GalleryGridItem.SelectionCompare
        self.update()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.gallery.setSelectedItem(self, True)
        elif event.button() == Qt.RightButton:
            self.gallery.tab.imgview.tool.onGalleryRightClick(self.file)
            self.gallery.setSelectedCompare(self)

    def paintEvent(self, event):
        palette = QtWidgets.QApplication.palette()
        
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        borderSize = 6
        x = borderSize/2
        y = x
        w = self.width() - borderSize
        h = self.height() - borderSize

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
            self.paintBorder(painter, palette, borderSize, x, y, w, h)
        
        # Draw filename
        textColor = palette.color(QtGui.QPalette.Text)
        pen = QtGui.QPen(textColor)
        painter.setPen(pen)
        textY = y + imgH + textSpacing
        painter.drawText(x, textY, w, textMaxHeight, Qt.AlignHCenter | Qt.TextWordWrap, self.filename)

        self._height = y + imgH + borderSize + textSpacing + textMaxHeight
        self.setFixedHeight(self._height)

    def paintBorder(self, painter, palette, borderSize, x, y, w, h):
        selectionColor = palette.color(QtGui.QPalette.Highlight)
        pen = QtGui.QPen(selectionColor)
        pen.setWidth(borderSize)
        pen.setJoinStyle(Qt.RoundJoin)
        if self.selectionStyle & GalleryGridItem.SelectionPrimary:
            pen.setStyle(Qt.SolidLine)
        elif self.selectionStyle & GalleryGridItem.SelectionCompare:
            pen.setStyle(Qt.DotLine)
        painter.setPen(pen)
        painter.drawRect(x, y, w, h)
    
    def paintIcons(self, painter, x, y):
        painter.save()

        sizeX, sizeY = 20, 20
        for iconKey, iconState in sorted(self.icons.items(), key=lambda item: item[0]):
            pen, brush = self.gallery.iconStates[iconState]
            painter.setPen(pen)
            painter.setBrush(brush)

            painter.drawRoundedRect(x, y, sizeX, sizeY, 3, 3)
            painter.drawPixmap(x, y, sizeX, sizeY, self.gallery.icons[iconKey])
            y += sizeX + 8
        
        painter.restore()
