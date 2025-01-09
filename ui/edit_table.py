from typing import Iterable
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Signal, Slot, QModelIndex, QSortFilterProxyModel, QAbstractItemModel, QRect, QEvent


class EditableTable(QtWidgets.QTableView):
    contentChanged = Signal()

    def __init__(self, numColumns: int):
        super().__init__()
        self.stringModel = StringModel(numColumns)
        self.proxyModel = StringProxyModel()
        self.proxyModel.setSourceModel(self.stringModel)
        self.setModel(self.proxyModel)

        self.setSortingEnabled(True)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self.verticalHeader().setVisible(False)

        self.setSelectionBehavior(QtWidgets.QTableView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QtWidgets.QTableView.SelectionMode.SingleSelection)

        self.sortByColumn(0, Qt.SortOrder.AscendingOrder)

        deleteDelegate = DeleteButtonDelegate(self.stringModel.getContentRows, numColumns, self)
        self.setItemDelegateForColumn(numColumns, deleteDelegate)
        deleteDelegate.deleteRow.connect(self.removeRow)

        self.stringModel.dataChanged.connect(self.onCellEdited)
        self.stringModel.dataChanged.connect(self._notifyContentChanged)
        self.stringModel.modelReset.connect(self._notifyContentChanged)
        self.stringModel.rowsInserted.connect(self._notifyContentChanged)
        self.stringModel.rowsRemoved.connect(self._notifyContentChanged)


    def setHorizontalHeaderLabels(self, labels: list[str]) -> None:
        self.stringModel.setHeaderLabels(labels)
        self.resizeColumnsToContents()

    def clear(self):
        self.stringModel.clear()

    def addRow(self, contents: Iterable[str]) -> None:
        self.stringModel.addRow(contents)

    @Slot()
    def removeRow(self, row: int) -> None:
        self.stringModel.removeRow(row)


    def setContent(self, content: Iterable[Iterable[str]]):
        self.stringModel.setContent(content)

    def getContent(self) -> list[tuple]:
        return [tuple(row) for row in self.stringModel.contents]

    def getContentColumn(self, column: int) -> list[str]:
        return [str(row[column]) for row in self.stringModel.contents]


    @Slot()
    def _notifyContentChanged(self):
        self.contentChanged.emit()

    @Slot()
    def onCellEdited(self, topLeft: QModelIndex, bottomRight: QModelIndex, roles: list[int]):
        index = self.proxyModel.mapFromSource(topLeft)

        row = index.row()
        column = index.column() + 1
        if column >= self.stringModel.getContentColumns():
            column = 0
            row += 1

        index = self.proxyModel.index(row, column)
        if index.isValid():
            self.setCurrentIndex(index)



class StringModel(QAbstractItemModel):
    ROLE_ROW = Qt.ItemDataRole.UserRole.value

    def __init__(self, numColumns: int):
        super().__init__()
        self.font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
        self.numColumns = numColumns
        self.contents: list[list[str]] = list()
        self.headerLabels = []

    def setHeaderLabels(self, labels: list[str]):
        self.headerLabels = labels

    def clear(self):
        self.beginResetModel()
        self.contents.clear()
        self.endResetModel()


    def setContent(self, content: Iterable[Iterable[str]]):
        self.beginResetModel()
        self.contents.clear()

        for rowContent in content:
            rowList = list(rowContent)
            if len(rowList) != self.numColumns:
                raise ValueError(f"Cannot add content with length {len(rowList)} to table with {self.numColumns} columns.")
            self.contents.append(rowList)

        self.endResetModel()


    def addRow(self, values: Iterable[str]) -> None:
        row = len(self.contents)
        self.insertRow(row)
        for col, val in zip(range(self.numColumns), values):
            index = self.index(row, col)
            self.setData(index, val)


    def getContentRows(self) -> int:
        return len(self.contents)
    
    def getContentColumns(self) -> int:
        return self.numColumns


    # QAbstractItemModel Interface

    def rowCount(self, parent=QModelIndex()):
        # One extra row for inserting new data
        return len(self.contents) + 1

    def columnCount(self, parent=QModelIndex()):
        return self.numColumns + 1


    def insertRows(self, row: int, count: int, parent=QModelIndex()) -> bool:
        self.beginInsertRows(parent, row, row+count-1)
        for i in range(count):
            self.contents.insert(row, [""] * self.numColumns)
        self.endInsertRows()
        return True

    def removeRows(self, row: int, count: int, parent=QModelIndex()) -> bool:
        maxRow = len(self.contents) - 1
        lastRow = row + count - 1
        if row > maxRow or lastRow > maxRow:
            return False

        self.beginRemoveRows(parent, row, lastRow)
        del self.contents[row:row+count]
        self.endRemoveRows()
        return True


    def setData(self, index: QModelIndex, value: str, role=Qt.ItemDataRole.EditRole) -> bool:
        col = index.column()
        if col >= self.numColumns:
            return False
        if col == 0 and not value:
            return False

        row = index.row()
        if row >= len(self.contents):
            if col > 0:
                return False
            self.insertRow(row)

        rowData: list[str] = self.contents[row]
        rowData[col] = value
        self.dataChanged.emit(index, index, [role])
        return True

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.FontRole:
            return self.font

        row = index.row()
        col = index.column()
        if row >= len(self.contents) or col >= self.numColumns:
            return None

        rowData: list[str] = self.contents[row]
        match role:
            case Qt.ItemDataRole.DisplayRole | Qt.ItemDataRole.EditRole:
                return rowData[col]
            case self.ROLE_ROW:
                return rowData

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole) -> str | None:
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return super().headerData(section, orientation, role)

        if section < len(self.headerLabels):
            return self.headerLabels[section]
        return None


    def flags(self, index):
        flags = Qt.ItemFlag.NoItemFlags
        if index.column() < self.numColumns:
            flags |= Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable
        return flags

    def index(self, row, column, parent=QModelIndex()):
        return self.createIndex(row, column)

    def parent(self, index):
        return QModelIndex()



class StringProxyModel(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        #self.setFilterKeyColumn(0)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        insertionRow = self.sourceModel().rowCount()-1
        descending = (self.sortOrder() == Qt.SortOrder.DescendingOrder)

        if left.row() == insertionRow:
            return False ^ descending
        elif right.row() == insertionRow:
            return True ^ descending

        return super().lessThan(left, right)



class DeleteButtonDelegate(QtWidgets.QStyledItemDelegate):
    deleteRow = Signal(int)

    def __init__(self, rowFunc, column: int, parent):
        super().__init__(parent)
        self.rowFunc = rowFunc
        self.col = column

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem, index: QModelIndex):
        if index.column() != self.col or index.row() == self.rowFunc():
            super().paint(painter, option, index)
            return

        button = QtWidgets.QStyleOptionButton()
        button.rect = self.getButtonRect(option)
        button.text = "⨯"
        QtWidgets.QApplication.style().drawControl(QtWidgets.QStyle.ControlElement.CE_PushButton, button, painter)

    def editorEvent(self, event: QEvent, model: StringProxyModel, option: QtWidgets.QStyleOptionViewItem, index: QModelIndex):
        if index.column() != self.col or index.row() == self.rowFunc() or event.type() != QEvent.Type.MouseButtonRelease:
            return super().editorEvent(event, model, option, index)

        buttonRect = self.getButtonRect(option)
        if not buttonRect.contains(event.pos()):
            return False

        index = model.mapToSource(index)
        self.deleteRow.emit(index.row())
        return True

    def getButtonRect(self, option: QtWidgets.QStyleOptionViewItem) -> QRect:
        buttonSize = QtWidgets.QApplication.style().pixelMetric(QtWidgets.QStyle.PixelMetric.PM_ButtonIconSize)
        #buttonSize = 20
        x = (option.rect.width()-buttonSize) / 2
        y = (option.rect.height()-buttonSize) / 2 - 1
        rect = QRect(option.rect.left() + x, option.rect.top() + y, buttonSize, buttonSize)
        return rect
