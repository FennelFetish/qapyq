from __future__ import annotations
from enum import Enum
from collections import defaultdict
from typing import Iterable, Callable
from lib.filelist import DataKeys, sortKey
from lib.captionfile import FileTypeSelector

# https://docs.python.org/3/library/difflib.html
from difflib import SequenceMatcher


# TODO: For complex changes when pasting text, ask with confirmation dialog?


class TagPresence(Enum):
    NotPresent      = 0
    PartialPresence = 1
    FullPresence    = 2



class FileTags:
    def __init__(self, file: str):
        self.file: str = file
        self.tags: list[TagData] = list()



class TagData:
    def __init__(self, tag: str):
        self._tag: str = tag
        self.files: dict[str, FileTags] = dict()

    @property
    def tag(self) -> str:
        return self._tag

    @tag.setter
    def tag(self, tag: str):
        print(f">> Update Tag: '{self._tag}' => '{tag}'")
        self._tag = tag

    def __eq__(self, other):
        if isinstance(other, str):
            return self._tag == other
        if isinstance(other, TagData):
            return self._tag == other._tag
        return False

    def __hash__(self) -> int:
        return hash(self._tag)

    def __str__(self) -> str:
        return self._tag

    def __repr__(self) -> str:
        return f"TagData('{self._tag}')"



class CaptionMultiEdit:
    def __init__(self, context, textEdit):
        from .caption_context import CaptionContext
        self.ctx: CaptionContext = context

        from .caption_text import CaptionTextEdit
        self.textEdit: CaptionTextEdit = textEdit

        self.filelist = self.ctx.tab.filelist
        self.separator = ", "
        self.active = False

        self._lastText = ""
        self._lastLength = 0
        self._edited = False

        self._tagData: dict[str, TagData] = dict() # Contains split tags
        self._tags: list[TagData] = list()
        self._files: list[FileTags] = list()

    def clear(self, cache=True):
        if self.active:
            if self._edited and cache:
                self._cacheCaptions()
            self._edited = False

            self._lastText = ""
            self._lastLength = 0

            self._tagData.clear()
            self._tags.clear()
            self._files.clear()
            self.active = False


    def loadCaptions(self, files: Iterable[str], loadFunc: Callable[[str], str], cacheCurrent=True) -> str:
        self.clear(cacheCurrent)
        matchNode = self.ctx.highlight.matchNode
        sepStrip = self.separator.strip()

        tagOrderMap = defaultdict[TagData, list[float]](list)

        # Sort files for consistency. FileList.selectedFiles is an unordered set.
        for file in sorted(files, key=sortKey):
            captionText = loadFunc(file)

            #tags = [tag.strip() for tag in captionText.split(sepStrip)] # Include empty
            tags = [tag for t in captionText.split(sepStrip) if (tag := t.strip())]
            fileTags = FileTags(file)
            self._files.append(fileTags)

            for i, tag in enumerate(tags):
                tagData = self._initTagData(fileTags, tag)
                fileTags.tags.append(tagData)

                splitTags = matchNode.split(tag.split(" "))
                for splitTag in splitTags:
                    self._initTagData(fileTags, splitTag, True)

                tagOrder = i / (len(tags)-1) if len(tags) > 1 else 0.0
                tagOrderMap[tagData].append(tagOrder)

        if self._files:
            self.active = True

            tagOrderMap = {tag: self._order(orderValues) for tag, orderValues in tagOrderMap.items()}
            self._tags.sort(key=tagOrderMap.get)

            text = self.separator.join(tag.tag for tag in self._tags)
            self._lastText = text
            self._lastLength = len(text)
            return text

        return ""

    def reloadCaptions(self, loadFunc: Callable[[str], str]) -> str:
        self._cacheCaptions()
        files = [file.file for file in self._files]
        return self.loadCaptions(files, loadFunc, False)

    def changeSeparator(self, separator: str, loadFunc: Callable[[str], str]) -> str:
        self._cacheCaptions()
        self.separator = separator
        files = [file.file for file in self._files]
        return self.loadCaptions(files, loadFunc, False)

    def _initTagData(self, fileTags: FileTags, tag: str, isSplit=False) -> TagData:
        tagData = self._tagData.get(tag)
        if not tagData:
            self._tagData[tag] = tagData = TagData(tag)
            if not isSplit:
                self._tags.append(tagData)

        tagData.files[fileTags.file] = fileTags
        return tagData

    @staticmethod
    def _order(values: list[float]) -> float:
        return sum(values) / len(values)


    def _cacheCaptions(self):
        for file in self._files:
            caption = self.separator.join(tag.tag for tag in file.tags)
            self.filelist.setData(file.file, DataKeys.Caption, caption)
            self.filelist.setData(file.file, DataKeys.CaptionState, DataKeys.IconStates.Changed)

    def saveCaptions(self, captionDest: FileTypeSelector) -> bool:
        if not self._files:
            return False

        success = True
        for file in self._files:
            caption = self.separator.join(tag.tag for tag in file.tags)
            success &= captionDest.saveCaption(file.file, caption)

            self.filelist.removeData(file.file, DataKeys.Caption)
            self.filelist.setData(file.file, DataKeys.CaptionState, DataKeys.IconStates.Saved)

        if success:
            self._edited = False
        return success


    # TODO: Handle duplicates -> make self._dataData a dict[str, list[FileData]]
    #                            then, search in list
    def getPresence(self, tag: str) -> TagPresence:
        if not self.active:
            return TagPresence.FullPresence

        if tagData := self._tagData.get(tag):
            if len(tagData.files) >= len(self._files):
                return TagPresence.FullPresence
            else:
                return TagPresence.PartialPresence

        return TagPresence.NotPresent


    def ensureFullPresence(self, index: int) -> bool:
        if not (0 <= index < len(self._tags)):
            return False
        tagData = self._tags[index]

        edited = False
        for file in self._files:
            if file.file not in tagData.files:
                tagData.files[file.file] = file
                file.tags.append(tagData)
                edited = True

        self._edited |= edited
        return edited


    def onCaptionEdited(self, text: str):
        print()
        textSplit = text.split(self.separator.strip())

        a = self._tags
        b = [tag.strip() for tag in textSplit]
        matcher = SequenceMatcher(None, a, b, autojunk=False)

        # Detect delete+insert as moves
        deletedTags: dict[str, list[int]] = defaultdict(list)  # References items in 'a'
        insertedTags: dict[str, list[int]] = defaultdict(list) # References placeholder indexes in 'newTagList'

        newTagList: list[TagData | None] = list()

        # NOTE: Big changes with more than one change means paste
        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op == "equal":
                print(f"Op Equal:   (i1={i1}, i2={i2}, lenA={i2-i1}),  (j1={j1}, j2={j2}, lenB={j2-j1})")
                newTagList.extend(a[i1:i2])
                continue

            self._edited = True

            # TODO: On edit, re-check combined tags for highlighting?

            match op:
                case "replace":
                    oldTags = a[i1:i2]
                    newTags = b[j1:j2]

                    print(f"Op Replace: {oldTags} => {newTags}")

                    if len(oldTags) == 1 and len(newTags) == 2:
                        if self._opSplit(newTagList, oldTags, newTags):
                            continue
                    elif len(oldTags) == 2 and len(newTags) == 1:
                        if self._opMerge(newTagList, oldTags, newTags):
                            continue

                    # TODO: Detect move, when a tag is replaced with another existing tag. And it's not a duplicate.
                    #       'blabla, red tree, monster'  =>  'monster, red tree'

                    self._opReplace(newTagList, oldTags, newTags)

                case "delete":
                    print(f"Op Delete:  {a[i1:i2]}")
                    for i in range(i1, i2):
                        tagText = self._tags[i].tag
                        deletedTags[tagText].append(i)

                case "insert":
                    print(f"Op Insert:  {b[j1:j2]}  between  {a[i1-1:i1+1]}")
                    for i in range(j1, j2):
                        tagText = b[i]
                        tagIndex = len(newTagList)
                        insertedTags[tagText].append(tagIndex)
                        newTagList.append(None) # Add empty placeholder

        # Try swapping moved tags. _opMove consumes entries from 'deletedTags' and 'insertedTags'.
        # NOTE: It is not necessarily the moved tag which is detected as deleted/inserted:
        #       When two neighboring tags are swapped, it will detect the new left tag as moved.
        self._opMove(newTagList, deletedTags, insertedTags)

        self._opDelete(deletedTags)
        self._opInsert(newTagList, insertedTags)

        self._tags = newTagList


        print()
        assert all(tag is not None for tag in newTagList)
        assert all(tag.tag == tagText for tag, tagText in zip(newTagList, b))
        assert len(newTagList) == len(b)

        newText = self.separator.join(tag.tag for tag in newTagList)
        print(f">> Updated Tags:\n{newText}")


    # Handle insertion of separator (after writing in the middle of text) by splitting a tag.
    # Make new tag for the left side of comma. Add this tag to all files.
    # Update the right side.
    def _opSplit(self, newTagList: list[TagData | None], oldTags: list[TagData], newTags: list[str]) -> bool:
        oldTag = oldTags[0]
        newTextLeft = newTags[0]
        newTextRight = newTags[1]

        middle = oldTag.tag.removeprefix(newTextLeft).removesuffix(newTextRight)
        if middle and not middle.isspace():
            return False

        print(f"  Comma inserted, split: '{oldTag}' => '{newTextLeft}', '{newTextRight}'   -   middle: '{middle}'")
        tag = self._createTagAllFiles(newTextLeft)
        newTagList.append(tag)

        oldTag.tag = newTextRight
        newTagList.append(oldTag)
        return True


    # Handle removal of separator by merging tags: Keep one, remove the other.
    # It doesn't matter which one is kept/removed: They are adjacent and the files are transferred.
    # The resulting tag will be present in all files which had one of the original tags.
    def _opMerge(self, newTagList: list[TagData | None], oldTags: list[TagData], newTags: list[str]) -> bool:
        oldLeft = oldTags[0]
        oldRight = oldTags[1]
        newText = newTags[0]

        middle = newText.removeprefix(oldLeft.tag).removesuffix(oldRight.tag)
        if middle and not middle.isspace():
            return False

        print(f"  Comma removed, merge: '{oldLeft.tag}', '{oldRight.tag}' => {newText}   -   middle: '{middle}'")
        self._transferTagFiles(oldRight, oldLeft)
        self._deleteTag(oldRight)

        oldLeft.tag = newText
        newTagList.append(oldLeft)
        return True


    def _opReplace(self, newTagList: list[TagData | None], oldTags: list[TagData], newTags: list[str]):
        # Can replace multiple with multiple.
        # Replace can also mean: Multiple tags removed with some extra separators left

        # Replace text
        for oldTag, newText in zip(oldTags, newTags):
            oldTag.tag = newText
            newTagList.append(oldTag)

        iExtra = min(len(oldTags), len(newTags))

        # Add new tags
        for newText in newTags[iExtra:]:
            tag = self._createTagAllFiles(newText)
            newTagList.append(tag)

        # Remove old tags
        for oldTag in oldTags[iExtra:]:
            self._deleteTag(oldTag)


    def _opMove(self, newTagList: list[TagData | None], deletedTags: dict[str, list[int]], insertedTags: dict[str, list[int]]):
        movedTags = deletedTags.keys() & insertedTags.keys()
        for tagText in movedTags:
            deleteIndexes = deletedTags.pop(tagText)
            insertIndexes = insertedTags.pop(tagText)

            for iDel, iIns in zip(deleteIndexes, insertIndexes):
                print(f"  Move: {self._tags[iDel]}({iDel}) => ({iIns})")
                assert newTagList[iIns] is None
                newTagList[iIns] = self._tags[iDel]

            iExtra = min(len(deleteIndexes), len(insertIndexes))

            # Handle additional deletes
            print(f"    Additional deletes: {deleteIndexes[iExtra:]}")
            for iDel in deleteIndexes[iExtra:]:
                self._deleteTag(self._tags[iDel])

            # Handle additional inserts
            print(f"    Additional inserts: {insertIndexes[iExtra:]}")
            for iIns in insertIndexes[iExtra:]:
                assert newTagList[iIns] is None
                newTagList[iIns] = self._createTagAllFiles(tagText)


        # TODO: Reorder tags in files

    def _opDelete(self, deletedTags: dict[str, list[int]]):
        for deleteIndexes in deletedTags.values():
            for iDel in deleteIndexes:
                self._deleteTag(self._tags[iDel])

    def _opInsert(self, newTagList: list[TagData | None], insertedTags: dict[str, list[int]]):
        for tagText, insertIndexes in insertedTags.items():
            for iIns in insertIndexes:
                assert newTagList[iIns] is None
                newTagList[iIns] = self._createTagAllFiles(tagText)


    def _createTagAllFiles(self, text: str) -> TagData:
        tag = TagData(text.strip())
        print(f">> Create Tag: '{tag}'")
        for file in self._files:
            tag.files[file.file] = file
            file.tags.append(tag)
        return tag

    def _deleteTag(self, tag: TagData):
        print(f">> Delete Tag: '{tag}'")
        for file in tag.files.values():
            file.tags.remove(tag)

    def _transferTagFiles(self, src: TagData, dest: TagData):
        for file in src.files.values():
            if file.file not in dest.files:
                dest.files[file.file] = file
                file.tags.append(dest)



    # def _getEdit(self, textSplit: list[str]):
    #     sepStrip = self.separator.strip()
    #     cursorPos = self.textEdit.textCursor().position()

    #     accumulatedLength = 0
    #     for i, caption in enumerate(textSplit):
    #         accumulatedLength += len(caption) + len(sepStrip)
    #         if cursorPos < accumulatedLength:
    #             return caption.strip(), i

    #     return "", -1




# Test Cases:


#    'blue_eyes, blabla, red tree, monster, red tree'
# => 'monster, red tree, blabla, monster, blue_eyes'

#   Op: delete (i1=0, i2=3),  j1=0, j2=0
#     [TagData('blue_eyes'), TagData('blabla'), TagData('red tree')]
#   Op: equal (i1=3, i2=5),  j1=0, j2=2
#   Op: insert (i1=5, i2=5),  j1=2, j2=5
#     ['blabla', 'monster', 'blue_eyes']  between  [TagData('red tree')]
#   Move: blabla(1) => (2)
#     Additional deletes: []
#     Additional inserts: []
#   Move: blue_eyes(0) => (4)
#     Additional deletes: []
#     Additional inserts: []
# >> Delete Tag: red tree
# >> Create Tag: monster


# TODO: Detect move, when a tag is replaced with another existing tag. And it's not a duplicate.
#       'blabla, red tree, monster'  =>  'monster, red tree'
