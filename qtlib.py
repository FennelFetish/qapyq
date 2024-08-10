from PySide6 import QtWidgets


class PrecisionSpinBox(QtWidgets.QSpinBox):
    def __init__(self, digits=2):
        super().__init__()
        digits = max(int(digits), 1) - 1
        self._precision = 10 ** digits
        self._format = f".{digits}f"

    def textFromValue(self, val: int) -> str:
        val /= self._precision
        return f"{val:{self._format}}"
    
    def valueFromText(self, text: str) -> int:
        val = float(text) * self._precision
        return round(val)


    # def setRange(self, min, max):
    #     min *= self._precision
    #     max *= self._precision
    #     super().setRange(min, max)