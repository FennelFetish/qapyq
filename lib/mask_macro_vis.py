from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from .mask_macro import MaskingMacro, MacroOp, MacroOpItem
from lib.qtlib import COLOR_BUBBLE_BLACK


class MacroVisualization(QtWidgets.QScrollArea):
    SPACING = 6
    COLORS = ["#1f363f", "#3f1f2d", "#243f1f", "#241f3f", "#3f2e1f", "#1f3f37", "#3f1f3e",
              "#353f1f", "#1f2c3f", "#3f1f22", "#1f3f26", "#2f1f3f", "#3f381f"]

    def __init__(self):
        super().__init__()
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setWidgetResizable(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Minimum)

        self.gridLayout = QtWidgets.QGridLayout()
        self.gridLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.gridLayout.setVerticalSpacing(0)
        self.gridLayout.setHorizontalSpacing(self.SPACING)

        widget = QtWidgets.QWidget()
        widget.setLayout(self.gridLayout)
        self.setWidget(widget)


    def clear(self):
        for i in reversed(range(self.gridLayout.count())):
            if widget := self.gridLayout.takeAt(i).widget():
                widget.deleteLater()


    def reload(self, path: str):
        self.clear()

        macro = MaskingMacro()
        macro.loadFrom(path)

        row = 0
        for col in range(4):
            self.gridLayout.addWidget(CellLabel(f"Layer {col}", bold=True), row, col)

        row += 1
        self.gridLayout.addWidget(QtWidgets.QWidget(), row, 0)
        self.gridLayout.setRowMinimumHeight(row, 4)

        row += 1
        row = self._loadOps(macro.operations, row)

        row += 1
        self.gridLayout.addWidget(QtWidgets.QWidget(), row, 0)
        self.gridLayout.setRowStretch(row, 1)


    def _loadOps(self, ops: list[MacroOpItem], row: int):
        startRow = row
        colors   = list(self.COLORS)
        layer    = 0
        maxLayer = 0

        self._fillBackground(row, startRow, 0, -1, colors)

        for op in ops:
            match op.op:
                case MacroOp.SetLayer:
                    layer = int(op.args["index"])
                    if layer > maxLayer:
                        self._fillBackground(row, startRow, layer, maxLayer, colors)
                        maxLayer = layer
                    continue

                case MacroOp.AddLayer:
                    maxLayer += 1
                    row = self._addRow(op, row, maxLayer, maxLayer, colors)

                case MacroOp.DeleteLayer:
                    col = int(op.args["index"])
                    row = self._addRow(op, row, col, maxLayer, colors)

                    colors.append(colors[col])
                    del colors[col]
                    maxLayer -= 1
                    layer = min(maxLayer, layer)

                case MacroOp.BlendLayers:
                    srcLayer = int(op.args["srcLayer"])
                    color1, color2 = colors[layer], colors[srcLayer]
                    if srcLayer < layer:
                        color1, color2 = color2, color1
                    row = self._addRow(op, row, layer, maxLayer, colors, color1, color2)

                case _:
                    row = self._addRow(op, row, layer, maxLayer, colors)

            row = self._addSpacing(row, maxLayer, colors)

        for i in range(maxLayer+1):
            opLabel = CellLabel(f"Layer {i} - Result", colors[i], bold=True)
            self.gridLayout.addWidget(opLabel, row, i)

        return row


    def _addRow(self, op: MacroOpItem, row: int, col: int, maxCol: int, colors: list[str], color1="", color2=""):
        if not color1:
            color1 = colors[col]

        opLabel = CellLabel(op.op.name, color1, color2, args=op.args)
        self.gridLayout.addWidget(opLabel, row, col)

        for i in range(maxCol+1):
            if i != col:
                self.gridLayout.addWidget(CellBg(colors[i]), row, i)

        return row + 1

    def _addSpacing(self, row: int, maxCol: int, colors: list[str]):
        if maxCol < 0:
            self.gridLayout.addWidget(CellBg("", self.SPACING), row, 0)
        else:
            for i in range(maxCol+1):
                self.gridLayout.addWidget(CellBg(colors[i], self.SPACING), row, i)

        return row + 1

    def _fillBackground(self, row: int, startRow: int, layer: int, maxLayer: int, colors: list[str]):
        # When a layer is selected without previous AddLayer op, that layer is expected as input.
        # Fill background above current row to visualize its existence.
        for col in range(maxLayer+1, layer+1):
            color = colors[col]

            for r in range(startRow, row, 2):
                self.gridLayout.addWidget(CellBg(color), r, col)
                self.gridLayout.addWidget(CellBg(color, self.SPACING), r+1, col)

            self.gridLayout.addWidget(CellBg(color, self.SPACING), startRow-1, col)
            self.gridLayout.itemAtPosition(0, col).widget().setInput(color)


class CellLabel(QtWidgets.QLabel):
    def __init__(self, title, color1=COLOR_BUBBLE_BLACK, color2="", bold=False, args: dict={}):
        super().__init__( self._buildTitle(title, args) )

        if bold:
            fontWeight, height = "900", 32
        else:
            fontWeight, height = "400", 26

        if color2:
            background = f"background: qlineargradient(x1:0.1, y1:0, x2:0.9, y2:0, stop:0 {color1}, stop:1 {color2})"
        else:
            background = f"background-color: {color1}"

        self.setStyleSheet(f"QLabel{{font-weight:{fontWeight}; color: #fff; {background}; border: 1px solid {COLOR_BUBBLE_BLACK}; border-radius: 8px}}")
        self.setFixedHeight(height)

    @staticmethod
    def _buildTitle(title: str, args: dict) -> str:
        params = []
        for k, v in args.items():
            if type(v) == list:
                params.append(f"{k}=[{len(v)}]")
            elif type(v) == float:
                params.append(f"{k}={v:.2f}")
            else:
                params.append(f"{k}={v}")

        if params:
            title += ": " + ", ".join(params)
        return title

    def setInput(self, color: str):
        title = f"{self.text()} - Input"
        self.setText(title)

        background = f"background-color: {color}"
        self.setStyleSheet(f"QLabel{{font-weight: 900; color: #fff; {background}; border: 1px solid {COLOR_BUBBLE_BLACK}; border-radius: 8px}}")



class CellBg(QtWidgets.QLabel):
    def __init__(self, color: str, height=0):
        super().__init__()
        if height:
            self.setFixedHeight(height)

        # Reduce opacity
        if color:
            color = f"#60{color[1:]}"
            self.setStyleSheet(f"QWidget{{background-color:{color}}}")



class MacroInspectWindow(QtWidgets.QDialog):
    def __init__(self, parent, macroName: str, macroPath: str) -> None:
        super().__init__(parent)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowTitle(f"Inspect Macro: {macroName}")
        self.resize(800, 600)

        macroVis = MacroVisualization()
        macroVis.reload(macroPath)

        btnClose = QtWidgets.QPushButton("Close")
        btnClose.clicked.connect(self.reject)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(macroVis)
        layout.addWidget(btnClose)
        self.setLayout(layout)
