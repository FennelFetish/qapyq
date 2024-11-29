from enum import Enum


class MacroOp(Enum):
    SetLayer        = 0
    AddLayer        = 1
    DeleteLayer     = 2

    ClearVram       = 10 # ??


class MaskingMacro:
    def __init__(self):
        self.operations = list()

    def addOperation(self, op: MacroOp, **kwargs):
        cmd = {"op": op.name}
        cmd.update(kwargs)
        print(f"addOp: {cmd}")
        self.operations.append(cmd)


    def saveTo(self, path: str):
        pass

    def loadFrom(self, path: str):
        pass
