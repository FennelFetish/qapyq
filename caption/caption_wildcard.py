import re
from itertools import product
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
import lib.qtlib as qtlib


WildcardDict = dict[str, list[str]]

PATTERN_WILDCARD = re.compile( r'({{[^}]+}})' )


class WildcardWindow(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget, wildcards: WildcardDict) -> None:
        super().__init__(parent)
        self.wildcards = wildcards

        self._build()
        self.fromDict()

        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowTitle("Setup Wildcards")
        self.resize(600, 400)

    def _build(self):
        infoLayout = QtWidgets.QHBoxLayout()
        infoLayout.addWidget(QtWidgets.QLabel("One per line. Example:"), 0)

        lblExample = QtWidgets.QLabel("color: blue, green, black, white")
        qtlib.setMonospace(lblExample)
        infoLayout.addWidget(lblExample, 1)

        layout = QtWidgets.QGridLayout(self)

        row = 0
        layout.addLayout(infoLayout, row, 0, 1, 3)

        row += 1
        layout.addWidget(QtWidgets.QLabel("Use in group-tags as \"{{color}} pants\"."), row, 0, 1, 3)

        row += 1
        layout.setRowStretch(row, 1)

        self.txtWildcards = QtWidgets.QPlainTextEdit()
        qtlib.setMonospace(self.txtWildcards)
        layout.addWidget(self.txtWildcards, row, 0, 1, 3)

        row += 1
        btnSave = QtWidgets.QPushButton("Save")
        btnSave.clicked.connect(self._acceptWildcards)
        btnSave.clicked.connect(self.accept)
        layout.addWidget(btnSave, row, 0)

        btnReload = QtWidgets.QPushButton("Reload")
        btnReload.clicked.connect(self.fromDict)
        layout.addWidget(btnReload, row, 1)

        btnCancel = QtWidgets.QPushButton("Cancel")
        btnCancel.clicked.connect(self.reject)
        layout.addWidget(btnCancel, row, 2)

        self.setLayout(layout)

    @Slot()
    def fromDict(self):
        self.txtWildcards.clear()
        lines = list[str]()
        for name, tags in self.wildcards.items():
            tags = ", ".join(tags)
            lines.append(f"{name}: {tags}")
        self.txtWildcards.setPlainText("\n".join(lines))

    def toDict(self) -> WildcardDict:
        wildcards = WildcardDict()
        lines = self.txtWildcards.toPlainText().splitlines()
        for line in lines:
            name, *tags = line.split(":")
            name = name.strip()
            if name and tags:
                wildcards[name] = [tag for t in tags[0].split(",") if (tag := t.strip())]

        return wildcards

    @Slot()
    def _acceptWildcards(self):
        self.wildcards = self.toDict()



def expandWildcards(tag: str, wildcards: WildcardDict) -> list[str]:
    wildcardPos = list[int]()
    wildcardTags = list[list[str]]()

    parts = PATTERN_WILDCARD.split(tag)
    if len(parts) == 1:
        return parts

    for i, part in enumerate(parts):
        if part.startswith("{{") and part.endswith("}}"):
            part = part.strip("{}")
            if wcTags := wildcards.get(part):
                wildcardPos.append(i)
                wildcardTags.append(wcTags)

    if not wildcardPos:
        return [tag]

    tags = list[str]()
    for wildcardVals in product(*wildcardTags):
        newParts = list[str](parts)
        for i, val in enumerate(wildcardVals):
            newParts[wildcardPos[i]] = val
        tags.append("".join(newParts))

    return tags
