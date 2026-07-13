from __future__ import annotations
from typing import Any, Callable, TYPE_CHECKING
from dataclasses import dataclass, astuple

if TYPE_CHECKING:
    from lib.template_parser import TemplateVariableParser
    from lib.captionfile import CaptionFile


@dataclass(slots=True)
class PromptInfo:
    name: str
    prompt: str = ""
    prefill: str = ""
    hidden: bool = False
    think: bool | None = None

    @property
    def promptWithPrefill(self) -> str:
        return f"{self.prompt}\n>>> {self.prefill}" if self.prefill else self.prompt


Conversation = list[PromptInfo]



class PromptUtil:
    @staticmethod
    def toTuples(conversations: list[Conversation]) -> list[list[tuple[Any, ...]]]:
        return [
            [astuple(info) for info in conv]
            for conv in conversations
        ]

    @staticmethod
    def fromTuples(conversations: list[list[tuple[Any, ...]]]) -> list[Conversation]:
        return [
            [PromptInfo(*data) for data in conv]
            for conv in conversations
        ]


    @staticmethod
    def filter(conversations: list[Conversation], pred: Callable[[PromptInfo], bool]):
        yield from (
            info
            for conv in conversations
            for info in conv
            if pred(info)
        )

    @staticmethod
    def firstMatch(conversations: list[Conversation], pred: Callable[[PromptInfo], bool]) -> PromptInfo | None:
        return next(PromptUtil.filter(conversations, pred), None)


    @staticmethod
    def parsePrompts(varParser: TemplateVariableParser, imgFile: str, captionFile: CaptionFile | None, prompts: list[Conversation]) -> list[Conversation]:
        varParser.setup(imgFile, captionFile)

        conversations = list[Conversation]()
        missingVars = set[str]()
        for inputConv in prompts:
            conv = Conversation()
            for info in inputConv:
                parsedPrompt = varParser.parse(info.prompt)
                missingVars.update(varParser.missingVars)

                conv.append(PromptInfo(info.name, parsedPrompt, info.prefill, info.hidden, info.think))

            conversations.append(conv)

        if missingVars:
            print(f"WARNING: '{imgFile}' is missing values for variables: {', '.join(missingVars)}")

        return conversations


    @staticmethod
    def print(conversations: list[Conversation]):
        print("=== Prompts ===")
        for i, conv in enumerate(conversations):
            print(f"--- Conversation[{i}] ---")
            for k, promptInfo in enumerate(conv):
                flags = []
                if promptInfo.hidden: flags.append("hidden[?]")
                if promptInfo.think:  flags.append("think[!]")

                print(f"  Prompt[{k}] '{promptInfo.name}': {', '.join(flags)}")
                for line in promptInfo.prompt.splitlines():
                    print(f"    {line}")

                if promptInfo.prefill:
                    lineIter = iter(promptInfo.prefill.splitlines())
                    print(f"    >>> Prefill: {next(lineIter)}")
                    for line in lineIter:
                        print(f"    {line}")



class ConversationParser:
    HIDDEN_NAME_SUFFIX = "__?hidden"

    @classmethod
    def parseTemplate(cls, text: str, defaultName: str = None, rounds: int = 1) -> list[Conversation]:
        if defaultName is None:
            defaultName = "caption"
        elif not defaultName:
            raise ValueError("Empty storage key")

        allNames = set()
        current = PromptInfo(defaultName)

        promptLines: list[str] = list()         # List of text lines of current prompt
        prefillLines: list[str] | None = None   # List of text lines of current prefill

        conversations = list[Conversation]()    # List of conversations in order
        currentConversation = Conversation()    # List of prompts of current conversation in order

        for line in text.splitlines():
            if line.startswith(">>>"):
                prefillLines = []
                if line := line.lstrip(">").lstrip():
                    prefillLines.append(line)

            elif line.startswith("---") or line.startswith("==="):
                # Save prefill before changing current
                if prefillLines:
                    current.prefill = "\n".join(prefillLines)
                prefillLines = None

                # New prompt
                if promptLines:
                    current.prompt = "\n".join(promptLines)
                    promptLines.clear()
                    allNames.add(current.name)
                    currentConversation.append(current)

                current = cls._createPromptInfo(line, defaultName, allNames)

                # New conversation
                if line[0] == '=' and currentConversation:
                    conversations.append(currentConversation)
                    currentConversation = Conversation()

            else:
                if prefillLines is None:
                    promptLines.append(line)
                else:
                    prefillLines.append(line)

        if prefillLines:
            current.prefill = "\n".join(prefillLines)

        if promptLines:
            current.prompt = "\n".join(promptLines)
            currentConversation.append(current)

        if currentConversation:
            conversations.append(currentConversation)

        # Empty prompt
        if not conversations:
            conversations.append( [PromptInfo(defaultName)] )

        # Apply rounds - build temporary list to not modify 'conversations' while iterating
        if rounds > 1:
            roundConvs = [
                [PromptInfo(f"{info.name}_round{r}", info.prompt, info.prefill, info.hidden, info.think) for info in conv]
                for r in range(2, rounds+1)
                for conv in conversations
            ]
            conversations.extend(roundConvs)

        return conversations


    @classmethod
    def _createPromptInfo(cls, line: str, defaultName: str, usedNames: set[str]) -> PromptInfo:
        hidden = False
        think  = False

        if newName := line.strip("-= \t").strip():
            for _ in (0,):
                match newName[0]:
                    case "?": hidden = True
                    case "!": think  = True
                    case _:   break

                newName = newName.lstrip("?! \t").lstrip()

        if not newName:
            newName = defaultName
        if hidden:
            newName += cls.HIDDEN_NAME_SUFFIX

        name = newName
        appendNr = 2
        while name in usedNames:
            name = f"{newName}_{appendNr}"
            appendNr += 1

        return PromptInfo(name, hidden=hidden, think=think)
