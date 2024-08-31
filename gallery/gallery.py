from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, QSize, Slot, Signal, QThreadPool, QObject, QRunnable
from .thumbnail_cache import ThumbnailCache
from filelist import DataKeys
import os
import qtlib


class ImageIcon:
    Caption = "caption"
    Crop = "crop"


class Gallery(QtWidgets.QWidget):
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
            ImageIcon.Crop: QtGui.QPixmap("./res/icon_crop.png")
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
        layout.setSpacing(20)
        self.setLayout(layout)

    def reloadImages(self):
        self.clearLayout()
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

            self.addImage(file, row, col)
            col += 1
            if col >= self.columns:
                col = 0
                row += 1

        self.headersUpdated.emit(headers)
    
    def addImage(self, file, row, col):
        galleryItem = GalleryItem(self, file)
        galleryItem.row = row
        self.fileItems[file] = galleryItem

        self.layout().addWidget(galleryItem, row, col, Qt.AlignTop)

        if self.filelist.getCurrentFile() == file:
            self._selectedItem = galleryItem
            galleryItem.setSelected(True)

        if compareTool := self.tab.getTool("compare"):
            if compareTool.compareFile == file:
                self._selectedCompare = galleryItem
                galleryItem.setCompare(True)

    def addHeader(self, text, row):
        label = QtWidgets.QLabel(text)
        qtlib.setMonospace(label, 1.2, bold=True)
        label.setContentsMargins(4, 4, 4, 4)

        palette = QtWidgets.QApplication.palette()
        colorFg = palette.color(QtGui.QPalette.ColorRole.BrightText).name()
        label.setStyleSheet(f"color: {colorFg}; background-color: #161616")
        self.layout().addWidget(label, row, 0, 1, self.columns)

    def clearLayout(self):
        layout = self.layout()
        for i in reversed(range(layout.count())):
            item = layout.takeAt(i)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                item.spacerItem().deleteLater()
        
        self.fileItems.clear()
        self._selectedItem = None
        self._selectedCompare = None

    def setSelectedItem(self, item, updateFileList=False):
        if self._selectedItem:
            self._selectedItem.setSelected(False)
        item.setSelected(True)
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

    def adjustGrid(self, widgetWidth):
        w = widgetWidth * 0.9
        cols = int(w // ThumbnailCache.THUMBNAIL_SIZE)
        cols -= 1
        cols = max(cols, 1)
        if cols == self.columns:
            return
    
        self.columns = cols
        layout = self.layout()

        items = []
        for i in reversed(range(layout.count())):
            items.append(layout.takeAt(i))

        headers = dict()
        row, col = 0, 0
        for widget in (item.widget() for item in reversed(items)):
            if isinstance(widget, GalleryItem):
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
        self.reloadImages()
        self.reloaded.emit()

    def onFileDataChanged(self, file, key):
        if file not in self.fileItems:
            return
        
        if key == DataKeys.CaptionState:
            widget = self.fileItems[file]
            if captionState := self.filelist.getData(file, DataKeys.CaptionState):
                widget.setIcon(ImageIcon.Caption, captionState)
            else:
                widget.removeIcon(ImageIcon.Caption)
            widget.update()

        elif key == DataKeys().CropState:
            widget = self.fileItems[file]
            if cropState := self.filelist.getData(file, DataKeys.CropState):
                widget.setIcon(ImageIcon.Crop, cropState)
            else:
                widget.removeIcon(ImageIcon.Crop)
            widget.update()



class GalleryItem(QtWidgets.QWidget):
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

        self._height = 100
        self.setMinimumSize(100, 100)

        ThumbnailCache.updateThumbnail(self.gallery.filelist, self, file)
        self._checkIcons(file)

    def _checkIcons(self, file):
        if captionState := self.gallery.filelist.getData(file, DataKeys.CaptionState):
            self.setIcon(ImageIcon.Caption, captionState)
        else:
            filenameNoExt, ext = os.path.splitext(self.filename)
            captionFile = os.path.join(os.path.dirname(file), filenameNoExt + ".txt")
            if os.path.exists(captionFile):
                self.setIcon(ImageIcon.Caption, DataKeys.IconStates.Exists)

        if cropState := self.gallery.filelist.getData(file, DataKeys.CropState):
            self.setIcon(ImageIcon.Crop, cropState)

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

    def setSelected(self, selected):
        if selected:
            self.selectionStyle |= GalleryItem.SelectionPrimary
        else:
            self.selectionStyle &= ~GalleryItem.SelectionPrimary
        self.update()

    def setCompare(self, selected):
        if selected:
            self.selectionStyle |= GalleryItem.SelectionCompare
        else:
            self.selectionStyle &= ~GalleryItem.SelectionCompare
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
        if self.selectionStyle & GalleryItem.SelectionPrimary:
            pen.setStyle(Qt.SolidLine)
        elif self.selectionStyle & GalleryItem.SelectionCompare:
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
