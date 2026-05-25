import os, csv, time
from typing import Callable, Any
from typing_extensions import override
from abc import ABC, abstractmethod


def csvFileFilter(path: str) -> bool:
    return path.endswith(".csv")


ColumnGetter = Callable[[list[str]], str]



class CsvLoader(ABC):
    def __init__(self):
        pass

    def loadAll(self, folder: str):
        for (root, dirs, files) in os.walk(folder, topdown=True, followlinks=True):
            for file in filter(csvFileFilter, files):
                path = os.path.join(root, file)
                try:
                    self.load(path)
                except Exception:
                    import traceback
                    traceback.print_exc()
                    self.fileFail(path)

    def load(self, file: str):
        t = time.monotonic_ns()
        self._loadCsv(file)
        t = (time.monotonic_ns() - t) / 1_000_000
        self.fileDone(file, t)


    def _loadCsv(self, path: str):
        bufferSize = 1048576 # 1MB
        with open(path, 'r', newline='', encoding='utf-8', errors='replace', buffering=bufferSize) as csvFile:
            skipHeaderRow, getters = self.detectColumns(csvFile, path)

            csvFile.seek(0)
            reader = csv.reader(csvFile)
            if skipHeaderRow:
                next(reader)

            for i, row in enumerate(reader):
                values = [get(row) for get in getters]
                self.processRow(i, values)

    @abstractmethod
    def detectColumns(self, csvFile, path: str) -> tuple[bool, list[ColumnGetter]]:
        'Returns: skipHeaderRow, list of column getters'
        ...

    @abstractmethod
    def processRow(self, rowIndex: int, values: list[str]):
        ...

    def fileDone(self, file: str, timeMs: float):
        pass

    def fileFail(self, file: str):
        pass


    @staticmethod
    def createColumnGetter(col: int, default: Any) -> Callable[[list[str]], Any]:
        if col >= 0:
            return lambda row: row[col]
        else:
            return lambda row: default



class ColumnNameCsvLoader(CsvLoader):
    def __init__(self):
        super().__init__()
        self.columnNames: tuple[str, ...] = ()
        self.defaultValues: dict[str, str] = {}

    def setColumnNames(self, *columnNames: str):
        self.columnNames = columnNames

    def setOptionalColumns(self, **defaultValues: str):
        self.defaultValues = defaultValues

    @override
    def detectColumns(self, csvFile, path: str) -> tuple[bool, list[ColumnGetter]]:
        reader = csv.reader(csvFile)
        headerRow = next(reader)

        getters = []
        for colName in self.columnNames:
            try:
                col = headerRow.index(colName)
                getters.append(lambda row, col=col: row[col])
            except ValueError:
                try:
                    defaultVal = self.defaultValues[colName]
                    getters.append(lambda row, defaultVal=defaultVal: defaultVal)
                except KeyError:
                    raise ValueError(f"Couldn't find '{colName}' column in CSV file '{path}'") from None

        return True, getters
