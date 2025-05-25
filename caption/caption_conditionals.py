from __future__ import annotations
import re, ast, operator
from typing import Generator, Callable, ForwardRef, Any
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, Signal, QSignalBlocker
import lib.qtlib as qtlib
from ui.flow_layout import ManualStartReorderWidget, ReorderDragHandle
from .caption_tab import CaptionTab
from .caption_preset import CaptionPreset, CaptionPresetConditional


# TODO: Apply actions to all results returned by condition
#       For example: All present: "tag1, tag2"
#                    Replace tag: {{A}} -> {{B}} should replace tag1 and tag2 with B


ConditionVariableParser = ForwardRef("ConditionVariableParser")

# Separator for parameters, no whitespace
SEP = ","


# Result of evaluation:
#   - result:       bool
#   - return value: list[str]  (for matched words. values are assigned to variable of condition)
#                   or None    (if result is False)
ConditionResult = tuple[bool, list[str] | None]

# conditionFunc(tags: list[str]) -> ConditionResult
ConditionFunc = Callable[[list[str]], ConditionResult]

# actionFunc(varParser: ConditionVariableParser, tags: list[str]) -> tags: list[str]
# Returns processed list of tags
ActionFunc = Callable[[ConditionVariableParser, list[str]], list[str]]



class CaptionConditionals(CaptionTab):
    def __init__(self, context):
        super().__init__(context)
        self._build()


    def _build(self):
        self._layout = QtWidgets.QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(16)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        reorderWidget = ManualStartReorderWidget()
        reorderWidget.setLayout(self._layout)
        reorderWidget.orderChanged.connect(lambda: self.ctx.controlUpdated.emit())
        scrollArea = qtlib.RowScrollArea(reorderWidget)
        scrollArea.setFrameStyle(QtWidgets.QFrame.Shape.NoFrame)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(scrollArea)

        btnAddRule = QtWidgets.QPushButton("✚ Add Conditional Rule")
        btnAddRule.clicked.connect(lambda: self.addRule())
        layout.addWidget(btnAddRule)

        self.setLayout(layout)


    @property
    def rules(self) -> Generator[ConditionalRule]:
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            if item and (widget := item.widget()) and isinstance(widget, ConditionalRule):
                yield widget


    def addRule(self) -> ConditionalRule:
        rule = ConditionalRule()
        rule.ruleUpdated.connect(lambda: self.ctx.controlUpdated.emit())
        rule.removeClicked.connect(self.removeRule)
        self._layout.addWidget(rule)
        self.ctx.controlUpdated.emit()
        return rule

    @Slot()
    def removeRule(self, rule: ConditionalRule):
        self._layout.removeWidget(rule)
        rule.deleteLater()
        self.ctx.controlUpdated.emit()

    def clearRules(self):
        for i in reversed(range(self._layout.count())):
            item = self._layout.takeAt(i)
            if item and (widget := item.widget()):
                widget.deleteLater()


    def getFilterRules(self) -> Generator[ConditionalFilterRule]:
        for rule in self.rules:
            yield rule.getFilterRule()


    def updateState(self, tags: list[str]):
        with QSignalBlocker(self):
            for rule in self.rules:
                rule.updateConditionStates(tags)


    def saveToPreset(self, preset: CaptionPreset):
        for rule in self.rules:
            presetRule = CaptionPresetConditional()
            rule.saveToPreset(presetRule)
            preset.conditionals.append(presetRule)

    def loadFromPreset(self, preset: CaptionPreset):
        with QSignalBlocker(self):
            self.clearRules()
            for presetRule in preset.conditionals:
                ruleWidget = self.addRule()
                ruleWidget.loadFromPreset(presetRule)



# Expression: A and B, A or B, not B (none present), A and (not B), (A or B) and C
class ConditionalRule(QtWidgets.QWidget):
    removeClicked = Signal(object)
    ruleUpdated = Signal()

    def __init__(self):
        super().__init__()

        self.conditionLayout = QtWidgets.QVBoxLayout()
        self.conditionLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.conditionLayout.setContentsMargins(0, 0, 0, 0)

        self.actionLayout = QtWidgets.QVBoxLayout()
        self.actionLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.actionLayout.setContentsMargins(0, 0, 0, 0)

        self._build()

        self.addRuleCondition()
        self.addRuleAction()

    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(3, 5, 5, 0)
        layout.setSpacing(4)

        # First Column, Drag Handle
        col = 0
        layout.setColumnStretch(col, 0)
        layout.setColumnMinimumWidth(col, 10)
        layout.addWidget(ReorderDragHandle(self), 0, col, 3, 1)

        # Left Column
        col = 1
        layout.setColumnStretch(col, 1)
        layout.addLayout(self.conditionLayout, 0, col, 2, 1, Qt.AlignmentFlag.AlignTop)

        btnAddCondition = QtWidgets.QPushButton("✚ Add Condition")
        btnAddCondition.clicked.connect(lambda: self.addRuleCondition())
        layout.addWidget(btnAddCondition, 2, col)

        # Right Column
        col = 2
        layout.setColumnStretch(col, 1)

        layout.addLayout(self._buildRightTopRow(), 0, col)
        layout.addLayout(self.actionLayout, 1, col, Qt.AlignmentFlag.AlignTop)

        btnAddAction = QtWidgets.QPushButton("✚ Add Action")
        btnAddAction.clicked.connect(lambda: self.addRuleAction())
        layout.addWidget(btnAddAction, 2, col)

        layout.setRowMinimumHeight(3, 3)

        separatorLine = QtWidgets.QFrame()
        separatorLine.setFrameStyle(QtWidgets.QFrame.Shape.HLine | QtWidgets.QFrame.Shadow.Sunken)
        layout.addWidget(separatorLine, 4, 0, 1, 3)

        self.setLayout(layout)

    def _buildRightTopRow(self):
        layout = QtWidgets.QHBoxLayout()

        self.lblExpression = QtWidgets.QLabel("Expression:")
        layout.addWidget(self.lblExpression, 0)

        self.txtExpression = QtWidgets.QLineEdit()
        self.txtExpression.setPlaceholderText("and")
        qtlib.setMonospace(self.txtExpression)
        self.txtExpression.textChanged.connect(self._onExpressionChanged)
        layout.addWidget(self.txtExpression, 1)

        btnRemoveRule = QtWidgets.QPushButton("Remove Rule")
        btnRemoveRule.clicked.connect(lambda: self.removeClicked.emit(self))
        layout.addWidget(btnRemoveRule, 0)

        return layout


    @Slot()
    def _onExpressionChanged(self, expression: str):
        checkedExpression, parsedExpression = ConditionalFilterRule.prepareExpression(expression)
        if checkedExpression:
            self.txtExpression.setStyleSheet("")
        else:
            self.txtExpression.setStyleSheet(f"color: {qtlib.COLOR_RED}")

        self.ruleUpdated.emit()


    def getFilterRule(self) -> ConditionalFilterRule:
        rule = ConditionalFilterRule()
        rule.setExpression(self.txtExpression.text())

        for cond in self.ruleConditions:
            rule.conditions[cond.variable] = cond.createConditionFunc()

        for action in self.ruleActions:
            rule.actions.append(action.createActionFunc())

        return rule

    def updateConditionStates(self, tags: list[str]):
        rule = ConditionalFilterRule()
        rule.setExpression(self.txtExpression.text())

        for cond in self.ruleConditions:
            rule.conditions[cond.variable] = cond.createConditionFunc()

        condResults, exprResult = rule.evaluateExpressionForUpdate(tags)
        exprColor = qtlib.COLOR_GREEN if exprResult else qtlib.COLOR_RED
        self.lblExpression.setStyleSheet(f"color: {exprColor}")

        for cond in self.ruleConditions:
            cond.updateConditionState(condResults.get(cond.variable, False))


    @property
    def ruleConditions(self) -> Generator[RuleCondition]:
        for i in range(self.conditionLayout.count()):
            item = self.conditionLayout.itemAt(i)
            if item and (widget := item.widget()):
                yield widget

    @property
    def ruleActions(self) -> Generator[RuleAction]:
        for i in range(self.actionLayout.count()):
            item = self.actionLayout.itemAt(i)
            if item and (widget := item.widget()):
                yield widget


    def addRuleCondition(self) -> RuleCondition:
        var = chr(65 + self.conditionLayout.count())
        cond = RuleCondition(var)
        cond.conditionUpdated.connect(self.ruleUpdated.emit)
        cond.removeClicked.connect(self.removeRuleCondition)

        self.conditionLayout.addWidget(cond)
        self._updateConditionVariables()
        self.ruleUpdated.emit()
        return cond

    @Slot()
    def removeRuleCondition(self, condWidget: RuleCondition):
        if self.conditionLayout.count() <= 1:
            return

        self.conditionLayout.removeWidget(condWidget)
        condWidget.deleteLater()
        self._updateConditionVariables()
        self.ruleUpdated.emit()
        # TODO: Update variables in expression

    def _updateConditionVariables(self):
        for i, cond in enumerate(self.ruleConditions):
            cond.variable = chr(65 + i)


    def addRuleAction(self) -> RuleAction:
        action = RuleAction()
        action.actionUpdated.connect(self.ruleUpdated.emit)
        action.removeClicked.connect(self.removeRuleAction)
        self.actionLayout.addWidget(action)
        self.ruleUpdated.emit()
        return action

    @Slot()
    def removeRuleAction(self, actionWidget: RuleAction):
        if self.actionLayout.count() <= 1:
            return

        self.actionLayout.removeWidget(actionWidget)
        actionWidget.deleteLater()
        self.ruleUpdated.emit()


    def _clearAll(self):
        for i in reversed(range(self.conditionLayout.count())):
            item = self.conditionLayout.takeAt(i)
            if item and (widget := item.widget()):
                widget.deleteLater()

        for i in reversed(range(self.actionLayout.count())):
            item = self.actionLayout.takeAt(i)
            if item and (widget := item.widget()):
                widget.deleteLater()


    def saveToPreset(self, condRule: CaptionPresetConditional):
        condRule.expression = self.txtExpression.text().strip()

        for cond in self.ruleConditions:
            presetCond = CaptionPresetConditional.Condition()
            cond.saveToPreset(presetCond)
            condRule.conditions.append(presetCond)

        for action in self.ruleActions:
            presetAction = CaptionPresetConditional.Action()
            action.saveToPreset(presetAction)
            condRule.actions.append(presetAction)

    def loadFromPreset(self, condRule: CaptionPresetConditional):
        with QSignalBlocker(self):
            self.txtExpression.setText(condRule.expression)
            self._clearAll()

            for presetCond in condRule.conditions:
                condWidget = self.addRuleCondition()
                condWidget.loadFromPreset(presetCond)

            for presetAction in condRule.actions:
                actionWidget = self.addRuleAction()
                actionWidget.loadFromPreset(presetAction)



class ConditionalFilterRule:
    OPS: dict[Any, Any] = {
        ast.Not:        operator.not_,
        ast.BitAnd:     operator.and_,
        ast.BitOr:      operator.or_,
        ast.BitXor:     operator.xor,
        ast.Eq:         operator.eq,
        ast.NotEq:      operator.ne
    }

    def __init__(self):
        # Conditions can be empty, but that only works for custom expressions (like "True")
        self.conditions = dict[str, ConditionFunc]()
        self.actions = list[ActionFunc]()

        self._expression = ""
        self._parsedExpression: ast.Expression | None = None


    def setExpression(self, expression: str):
        self._expression, self._parsedExpression = self.prepareExpression(expression)

    @staticmethod
    def prepareExpression(expression: str) -> tuple[str, ast.Expression|None]:
        expression = expression.strip()
        expression = expression.replace(" and ", " & ")
        expression = expression.replace(" or ", " | ")
        expression = expression.replace(" xor ", " ^ ")

        if not expression:
            return "and", None
        if expression.lower() in ("and", "or"):
            return expression.lower(), None

        try:
            parsedExpression = ast.parse(expression, mode="eval")
            return expression, parsedExpression
        except SyntaxError:
            # Syntax error in expression will evaluate to false
            return "", None


    def evaluateExpression(self, tags: list[str]) -> ConditionVariableParser | None:
        if self._parsedExpression:
            results, variables = self._evalAll(tags)
            if self._eval(results, variables):
                return ConditionVariableParser(variables)
            return None

        match self._expression:
            case "and": variables = self._evalAnd(tags)
            case "or":  variables = self._evalOr(tags)
            case _:
                return None

        if variables:
            return ConditionVariableParser(variables)
        return None

    def evaluateExpressionForUpdate(self, tags: list[str]) -> tuple[dict[str, bool], bool]:
        results, variables = self._evalAll(tags)

        if self._parsedExpression:
            exprResult = self._eval(results, variables)
        else:
            match self._expression:
                case "and": exprResult = all(results.values())
                case "or":  exprResult = any(results.values())
                case _:     exprResult = False

        return results, exprResult


    def _evalAnd(self, tags: list[str]) -> dict[str, list[str]] | None:
        results = dict[str, list[str]]()

        for var, cond in self.conditions.items():
            result = cond(tags)
            if result[0]:
                results[var] = result[1] or []
            else:
                return None

        return results

    def _evalOr(self, tags: list[str]) -> dict[str, list[str]] | None:
        results = dict[str, list[str]]()

        for var, cond in self.conditions.items():
            result = cond(tags)
            if result[0]:
                results[var] = result[1] or []

        if results:
            return results
        return None

    def _evalAll(self, tags: list[str]) -> tuple[dict[str, bool], dict[str, list[str]]]:
        results   = dict[str, bool]()
        variables = dict[str, list[str]]()

        for var, cond in self.conditions.items():
            result = cond(tags)
            results[var] = result[0]
            if result[0]:
                variables[var] = result[1] or []

        return results, variables


    def _eval(self, condResults: dict[str, bool], condVariables: dict[str, list[str]]) -> bool:
        def getAttr(value, attr: str):
            match attr:
                case "val":
                    return condVariables.get(value, [""])[0]
                case _:
                    return False

        def eval(node):
            match node:
                case ast.UnaryOp(op=op, operand=operand):
                    return self.OPS[type(op)](eval(operand))

                case ast.BinOp(left=left, op=op, right=right):
                    return self.OPS[type(op)](eval(left), eval(right))

                case ast.Compare(left=left, ops=[op], comparators=[comparator]):
                    return self.OPS[type(op)](eval(left), eval(comparator))

                case ast.Attribute(value=value, attr=attr):
                    return getAttr(value.id, attr) if isinstance(value, ast.Name) else False

                case ast.Constant(value=value):
                    return value

                case ast.Name(id=id):
                    return condResults.get(id, False)

                case _:
                    raise TypeError(node)

        try:
            return bool(eval(self._parsedExpression.body))
        except:
            return False



class RuleParams(QtWidgets.QHBoxLayout):
    def __init__(self, defs: dict[str, ConditionDef] | dict[str, ActionDef], signalUpdate, firstStretch=1):
        super().__init__()
        self.setContentsMargins(0, 0, 0, 0)
        self._defs = defs
        self.signalUpdate = signalUpdate
        self.firstStretch = firstStretch

        self.txtParams = list[QtWidgets.QLineEdit]()
        self._definition: ConditionDef | ActionDef = None

        # Not part of the layout
        self.cboDefinitions = qtlib.NonScrollComboBox()
        for defKey, defVal in defs.items():
            self.cboDefinitions.addItem(defVal.name, defKey)
        self.cboDefinitions.currentIndexChanged.connect(self._onDefinitionChanged)
        self._onDefinitionChanged(self.cboDefinitions.currentIndex())

    @Slot()
    def _onDefinitionChanged(self, index: int):
        defKey: str = self.cboDefinitions.itemData(index)
        self._definition = self._defs[defKey]
        self.updateParams()

    def updateParams(self):
        numParams = self._definition.numParams
        params = self._definition.params

        # Update existing text fields
        for i, txt in enumerate(self.txtParams[0:numParams]):
            txt.setToolTip(params[i])
            txt.show()
        for txt in self.txtParams[numParams:]:
            txt.setToolTip("")
            txt.hide()

        # Add missing text fields
        startIndex = max(0, len(self.txtParams))
        for i in range(startIndex, numParams):
            txt = QtWidgets.QLineEdit()
            qtlib.setMonospace(txt)
            txt.setMinimumWidth(50)
            txt.setToolTip(params[i])
            txt.textChanged.connect(lambda: self.signalUpdate.emit())

            self.txtParams.append(txt)
            stretch = self.firstStretch if i==0 else 1
            self.addWidget(txt, stretch)

        # Set tab order
        if parentWidget := self.parentWidget():
            for i, txt in enumerate(self.txtParams[:-1]):
                parentWidget.setTabOrder(txt, self.txtParams[i+1])

        self.signalUpdate.emit()

    @property
    def definitionKey(self) -> str:
        return self.cboDefinitions.currentData()

    def createFunc(self):
        params = [txt.text() for txt in self.txtParams[:self._definition.numParams]]
        return self._definition.factory(params)

    def toDict(self, data: dict[str, str]):
        for i, paramName in enumerate(self._definition.params):
            data[paramName] = self.txtParams[i].text()

    def fromDict(self, defKey: str, data: dict[str, str]):
        if defKey in self._defs:
            defIndex = self.cboDefinitions.findData(defKey)
        else:
            defKey = self.cboDefinitions.itemData(0)
            defIndex = 0
            data = {}

        self.cboDefinitions.setCurrentIndex(defIndex)
        self._definition = self._defs[defKey]
        self.updateParams()

        if data:
            for i, paramName in enumerate(self._definition.params):
                value: str = data.get(paramName, "")
                self.txtParams[i].setText(value)
        else:
            for txt in self.txtParams:
                txt.setText("")



class RuleCondition(QtWidgets.QWidget):
    conditionUpdated = Signal()
    removeClicked = Signal(object)

    def __init__(self, var: str):
        super().__init__()
        self._var = var

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        btnRemove = qtlib.BubbleRemoveButton()
        btnRemove.clicked.connect(lambda: self.removeClicked.emit(self))
        layout.addWidget(btnRemove)

        self.lblVar = QtWidgets.QLabel(var)
        qtlib.setMonospace(self.lblVar, 1.0, bold=True)
        layout.addWidget(self.lblVar)

        layout.addWidget(QtWidgets.QLabel("If:"))

        self.params = RuleParams(CONDITIONS, self.conditionUpdated, 10)
        layout.addWidget(self.params.cboDefinitions)
        layout.addLayout(self.params)

        self.setLayout(layout)

    @property
    def variable(self) -> str:
        return self._var

    @variable.setter
    def variable(self, var: str):
        if var != self._var:
            self._var = var
            self.lblVar.setText(var)

    def updateConditionState(self, state: bool):
        color = qtlib.COLOR_GREEN if state else qtlib.COLOR_RED
        self.lblVar.setStyleSheet(f"color: {color}")

    def createConditionFunc(self) -> ConditionFunc:
        return self.params.createFunc()

    def saveToPreset(self, cond: CaptionPresetConditional.Condition):
        cond.key = self.params.definitionKey
        self.params.toDict(cond.params)

    def loadFromPreset(self, cond: CaptionPresetConditional.Condition):
        with QSignalBlocker(self):
            self.params.fromDict(cond.key, cond.params)



class RuleAction(QtWidgets.QWidget):
    actionUpdated = Signal()
    removeClicked = Signal(object)

    def __init__(self):
        super().__init__()

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.params = RuleParams(ACTIONS, self.actionUpdated)
        layout.addWidget(self.params.cboDefinitions)
        layout.addLayout(self.params)

        btnRemove = qtlib.BubbleRemoveButton()
        btnRemove.clicked.connect(lambda: self.removeClicked.emit(self))
        layout.addWidget(btnRemove)

        self.setLayout(layout)

    def createActionFunc(self) -> ActionFunc:
        return self.params.createFunc()

    def saveToPreset(self, action: CaptionPresetConditional.Action):
        action.key = self.params.definitionKey
        self.params.toDict(action.params)

    def loadFromPreset(self, action: CaptionPresetConditional.Action):
        with QSignalBlocker(self):
            self.params.fromDict(action.key, action.params)



class ConditionVariableParser:
    PATTERN_VAR = re.compile( r'{{([^}]+)}}' )

    def __init__(self, vars: dict[str, list[str]]):
        self.vars = vars
        self.separator = ", "

    def parse(self, template: str) -> str:
        # TODO: Parse wildcards here?
        return self.PATTERN_VAR.sub(self._replace, template)

    def _replace(self, match: re.Match) -> str:
        var = match.group(1).strip()
        var, *attr = var.split(".")
        attr = attr[0].strip() if attr else ""

        values = self.vars.get(var)
        if not values:
            return ""
        if not attr:
            return values[0]

        match attr:
            case "last":
                return values[-1]
            case "all":
                return self.separator.join(values)

        if attr.isdigit():
            index = int(attr)
            if 0 <= index < len(values):
                return values[index]

        return ""



def splitParams(paramText: str) -> list[str]:
    return [p for p in paramText.split(SEP)]

def splitParamsNonEmpty(paramText: str) -> list[str]:
    return [p for p in paramText.split(SEP) if p]

def splitParamsStrip(paramText: str) -> list[str]:
    return [p for param in paramText.split(SEP) if (p := param.strip())]

def splitParamsStripSet(paramText: str) -> set[str]:
    return set(p for param in paramText.split(SEP) if (p := param.strip()))

def getIntParam(paramText: str, default: int) -> int:
    try:
        return int(paramText)
    except ValueError:
        return default


def parseSearchReplace(varParser: ConditionVariableParser, search: list[str], replace: list[str]):
    parsedPairs = {
        varParser.parse(s): varParser.parse(r)
        for s, r in zip(search, replace)
    }
    parsedPairs.pop("", None)
    return parsedPairs


# (?:^|\s)(search)(?:$|\s)
def findWord(text: str, search: str) -> Generator[int]:
    start = 0
    while (index := text.find(search, start)) >= 0:
        if (index == 0 or text[index-1].isspace()) and (index+len(search) >= len(text) or text[index+len(search)].isspace()):
            yield index
        start = index + len(search) + 1  # Add one for space



# ===== Conditions =====

def falseCondition(tags: list[str]) -> ConditionResult:
    return False, None


# TODO: Split using matcher node (separate Cond)
def createCondAllTagsPresent(params: list[str]) -> ConditionFunc:
    searchSet = splitParamsStripSet(params[0])

    if not searchSet:
        return falseCondition

    def condAllTagsPresent(tags: list[str]) -> ConditionResult:
        foundTags: list[str] = []
        for tag in tags:
            if (tag in searchSet) and (tag not in foundTags):
                foundTags.append(tag)

        if len(foundTags) >= len(searchSet):
            return True, foundTags
        else:
            return False, None

    return condAllTagsPresent


# TODO: Split using matcher node (separate Cond)
def createCondAnyTagsPresent(params: list[str]) -> ConditionFunc:
    searchSet = splitParamsStripSet(params[0])

    def condAnyTagsPresent(tags: list[str]) -> ConditionResult:
        for tag in tags:
            if tag in searchSet:
                return True, [tag]
        return False, None

    return condAnyTagsPresent


def createCondNumTagsPresent(params: list[str]) -> ConditionFunc:
    searchSet = splitParamsStripSet(params[0])
    minTags = getIntParam(params[1], 1)
    maxTags = getIntParam(params[2], 2**31)

    def condNumTagsPresent(tags: list[str]) -> ConditionResult:
        foundTags = [tag for tag in tags if tag in searchSet]
        if minTags <= len(foundTags) <= maxTags:
            return True, foundTags
        return False, None

    return condNumTagsPresent


def createCondAnyWordsPresent(params: list[str]) -> ConditionFunc:
    search = splitParamsStrip(params[0])

    def condAnyWordsPresent(tags: list[str]) -> ConditionResult:
        for tag in tags:
            for s in search:
                if any(True for _ in findWord(tag, s)):
                    return True, [s]

        return False, None

    return condAnyWordsPresent


def createCondAnyStringsPresent(params: list[str]) -> ConditionFunc:
    search = splitParamsNonEmpty(params[0])

    def condAnyStringsPresent(tags: list[str]) -> ConditionResult:
        for tag in tags:
            if any(True for s in search if (s in tag)):
                return True, [tag]

        return False, None

    return condAnyStringsPresent



class ConditionDef:
    def __init__(self, name: str, factory: Callable, params: list[str]):
        self.name = name
        self.params = params
        self.factory = factory

    @property
    def numParams(self) -> int:
        return len(self.params)


CONDITIONS = {
    "AllTagsPresent":       ConditionDef("All tags present", createCondAllTagsPresent, ["tags"]),
    "AnyTagsPresent":       ConditionDef("Any tags present", createCondAnyTagsPresent, ["tags"]),
    "NumTagsPresent":       ConditionDef("Some tags present", createCondNumTagsPresent, ["tags", "min", "max"]),
    "AnyWordsPresent":      ConditionDef("Any words present", createCondAnyWordsPresent, ["words"]),
    "AnyStringsPresent":    ConditionDef("Any strings present", createCondAnyStringsPresent, ["strings"])
}

# TODO: Any superset present (words checked as subsets)


# ===== Actions =====

def createActionAddTags(params: list[str]) -> ActionFunc:
    addTags = splitParamsStrip(params[0])

    def actAddTags(varParser: ConditionVariableParser, tags: list[str]) -> list[str]:
        tags.extend(varParser.parse(tag) for tag in addTags)
        return tags

    return actAddTags


def createActionRemoveTags(params: list[str]) -> ActionFunc:
    removeTags = splitParamsStrip(params[0])

    def actRemoveTags(varParser: ConditionVariableParser, tags: list[str]) -> list[str]:
        removeSet = set(varParser.parse(tag) for tag in removeTags)
        return [tag for tag in tags if tag not in removeSet]

    return actRemoveTags


def createActionRemoveTagsContaining(params: list[str]) -> ActionFunc:
    search = [param for param in splitParams(params[0]) if param]

    def actRemoveTagsContaining(varParser: ConditionVariableParser, tags: list[str]) -> list[str]:
        parsedSearch = [varParser.parse(s) for s in search]
        return [
            tag for tag in tags
            if not any(s in tag for s in parsedSearch)
        ]

    return actRemoveTagsContaining


def createActionReplaceTags(params: list[str]) -> ActionFunc:
    search  = splitParamsStrip(params[0])
    replace = splitParams(params[1])

    def actReplaceTags(varParser: ConditionVariableParser, tags: list[str]) -> list[str]:
        parsedPairs = parseSearchReplace(varParser, search, replace)

        newTags = list[str]()
        for tag in tags:
            replacement = parsedPairs.get(tag)
            if replacement is not None:
                newTags.append(replacement)
            else:
                newTags.append(tag)

        return newTags

    return actReplaceTags


def createActionReplaceWords(params: list[str]) -> ActionFunc:
    search  = splitParamsStrip(params[0])
    replace = splitParams(params[1])

    def actReplaceWords(varParser: ConditionVariableParser, tags: list[str]) -> list[str]:
        parsedPairs = parseSearchReplace(varParser, search, replace)

        newTags = list[str]()
        tagParts = list[str]()
        for tag in tags:
            for s, r in parsedPairs.items():
                tagParts.clear()
                start = 0
                for index in findWord(tag, s):
                    tagParts.append(tag[start:index])
                    tagParts.append(r)
                    start = index + len(s)

                if start > 0:
                    tagParts.append(tag[start:])
                    tag = "".join(tagParts)

            newTags.append(tag)

        return newTags

    return actReplaceWords


def createActionReplaceStrings(params: list[str]) -> ActionFunc:
    search  = splitParams(params[0])
    replace = splitParams(params[1])

    def actReplaceStrings(varParser: ConditionVariableParser, tags: list[str]) -> list[str]:
        parsedPairs = parseSearchReplace(varParser, search, replace)

        newTags = list[str]()
        for tag in tags:
            for s, r in parsedPairs.items():
                tag = tag.replace(s, r)
            newTags.append(tag)

        return newTags

    return actReplaceStrings



class ActionDef:
    def __init__(self, name: str, factory: Callable, params: list[str]):
        self.name = name
        self.params = params
        self.factory = factory

    @property
    def numParams(self) -> int:
        return len(self.params)


ACTIONS = {
    "AddTags":              ActionDef("Add tags", createActionAddTags, ["tags"]),
    "RemoveTags":           ActionDef("Remove tags", createActionRemoveTags, ["tags"]),
    "RemoveTagsContaining": ActionDef("Remove tags containing", createActionRemoveTagsContaining, ["words"]),
    "ReplaceTags":          ActionDef("Replace tags", createActionReplaceTags, ["search", "replace"]),
    "ReplaceWords":         ActionDef("Replace words", createActionReplaceWords, ["search", "replace"]),
    "ReplaceStrings":       ActionDef("Replace strings", createActionReplaceStrings, ["search", "replace"])

    # Add tag to different key?
}
