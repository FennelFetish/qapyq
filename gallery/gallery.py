from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, QSize, Slot, Signal, QThreadPool, QObject, QRunnable
from .thumbnail_cache import ThumbnailCache
import os


class Gallery(QtWidgets.QWidget):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.filelist = tab.filelist

        self.columns = 4
        self.itemCount = 0

        self._selectedItem = None
        self._ignoreFileChange = False

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        self.setLayout(layout)

    def reloadImages(self):
        self.clearLayout()
        for file in self.filelist.getFiles():
            self.addImage(file)
    
    def addImage(self, file):
        galleryItem = GalleryItem(self, file)

        row = self.itemCount // self.columns
        col = self.itemCount % self.columns
        self.layout().addWidget(galleryItem, row, col)
        self.itemCount += 1

        if self.filelist.getCurrentFile() == file:
            self._selectedItem = galleryItem
            galleryItem.setSelected(True)

    def clearLayout(self):
        layout = self.layout()
        for i in reversed(range(layout.count())):
            item = layout.takeAt(i)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                item.spacerItem().deleteLater()
        self.itemCount = 0
        self._selectedItem = None

    def setSelectedItem(self, item, updateFileList=False):
        if self._selectedItem:
            self._selectedItem.setSelected(False)
        item.setSelected(True)
        self._selectedItem = item

        if updateFileList:
            try:
                self._ignoreFileChange = True
                self.filelist.setCurrentFile(item.file)
            finally:
                self._ignoreFileChange = False

    def adjustGrid(self, widgetWidth):
        w = widgetWidth * 0.9
        cols = w // ThumbnailCache.THUMBNAIL_SIZE
        cols -= 1
        cols = max(cols, 1)
        if cols == self.columns:
            return
    
        self.columns = cols
        layout = self.layout()

        items = []
        for i in reversed(range(layout.count())):
            items.append(layout.takeAt(i))

        for i, item in enumerate(reversed(items)):
            row = i // cols
            col = i % cols
            layout.addItem(item, row, col)
        
        layout.update()


    def onFileChanged(self, currentFile):
        if self._ignoreFileChange:
            return

        layout = self.layout()
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if widget and widget.file == currentFile:
                self.setSelectedItem(widget)
                break
    
    def onFileListChanged(self, currentFile):
        self.reloadImages()



class GalleryItem(QtWidgets.QWidget):
    def __init__(self, gallery, file):
        super().__init__()
        self.gallery = gallery
        self.file = file
        
        self._pixmap = None
        self.filename = os.path.basename(file)
        self.selectionStyle = None

        self._height = 100

        ThumbnailCache.updateThumbnail(self, file)

    def sizeHint(self):
        return QSize(-1, self._height)
        #return QSize(256, 256)

    # def minimumSizeHint(self):
    #     return self.sizeHint()

    # def minimumSize(self):
    #     return self.sizeHint()

    @property
    def pixmap(self):
        return self._pixmap
    
    @pixmap.setter
    def pixmap(self, pixmap):
        self._pixmap = pixmap
        w = pixmap.width()
        h = pixmap.height()
        self._height = h
        # aspect = h / w
        # h = w * aspect
        self.update()

    def setSelected(self, selected):
        self.selectionStyle = "primary" if selected else None
        self.update()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.gallery.setSelectedItem(self, True)
        elif event.button() == Qt.RightButton:
            self.gallery.tab.imgview.tool.onGalleryRightClick(self.file)

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
        
        # Draw border
        if self.selectionStyle:
            selectionColor = palette.color(QtGui.QPalette.Highlight)
            pen = QtGui.QPen(selectionColor)
            pen.setWidth(borderSize)
            painter.setPen(pen)
            painter.drawRect(x, y, w, h)
        
        # Draw filename
        textColor = palette.color(QtGui.QPalette.Text)
        pen = QtGui.QPen(textColor)
        painter.setPen(pen)
        textY = y + imgH + textSpacing
        painter.drawText(x, textY, w, textMaxHeight, Qt.AlignHCenter | Qt.TextWordWrap, self.filename)

        self._height = y + imgH + borderSize + textSpacing + textMaxHeight
        self.setFixedHeight(self._height)