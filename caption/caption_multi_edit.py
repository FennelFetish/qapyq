from __future__ import annotations
from collections import defaultdict
from typing import Iterable, Callable, Generator
from lib.filelist import FileList, DataKeys, sortKey
from lib.captionfile import FileTypeSelector
from .caption_highlight import MatcherNode

# https://docs.python.org/3/library/difflib.html
from difflib import SequenceMatcher

import logging
logger = logging.getLogger("CaptionMultiEdit")


# TODO: For complex changes when pasting text, ask with confirmation dialog?


class FileTags:
    def __init__(self, file: str):
        self._file: str = file
        self._tags: list[TagData] = list()
        self.edited = False

    @property
    def file(self) -> str:
        return self._file

    @property
    def tags(self) -> Iterable[str]:
        return (tag.tag for tag in self._tags)

    def appendTag(self, tag: TagData):
        self._tags.append(tag)
        self.edited = True

    def removeTag(self, tag: TagData):
        for i, t in enumerate(self._tags):
            if t is tag:
                del self._tags[i]
                break
        else:
            logger.warning(f"FileTags.removeTag: Tag '{tag.tag}' not found")

        self.edited = True

    def getOrderDictAbs(self) -> dict[TagData, float]:
        return {tag: float(i) for i, tag in enumerate(self._tags)}

    def getOrderDictRel(self) -> dict[TagData, float]:
        if len(self._tags) == 1:
            return {self._tags[0]: 0.0}

        maxIndex = len(self._tags) - 1
        return {tag: i/maxIndex for i, tag in enumerate(self._tags)}

    def sortFilesRel(self, extraOrder: Iterable[tuple[TagData, float]]):
        # Keep order of other tags, which may be different from display order.
        # TODO: Make more accurate
        order = self.getOrderDictRel()
        order.update(extraOrder)
        self._tags.sort(key=order.__getitem__)
        self.edited = True



class TagData:
    def __init__(self, tag: str):
        self._tag: str = tag
        self.files: dict[str, FileTags] = dict()

    @property
    def tag(self) -> str:
        return self._tag

    @tag.setter
    def tag(self, text: str):
        self._tag = text
        for file in self.files.values():
            file.edited = True

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



class TagCounter:
    def __init__(self):
        self._counts: dict[str, int] = dict()

    def getAndIncrease(self, tag: str) -> int:
        count = self._counts.get(tag)
        if count is None:
            count = 0

        self._counts[tag] = count + 1
        return count

    def clear(self):
        self._counts.clear()



class CaptionMultiEdit:
    ORDER_OFFSET = 0.0001

    def __init__(self, filelist: FileList):
        self.filelist = filelist
        self.separator = ", "
        self.active = False
        self._edited = False

        self._tagData: dict[str, list[TagData]] = defaultdict(list)
        self._tags: list[TagData] = list()
        self._files: list[FileTags] = list()

        self._splitTagFiles: dict[str, set[FileTags]] = defaultdict(set)

    @property
    def isEdited(self) -> bool:
        return self._edited

    def clear(self, cache=True):
        if not self.active:
            return

        if self._edited and cache:
            self._cacheCaptions()
        self._edited = False

        self._tagData.clear()
        self._tags.clear()
        self._files.clear()
        self._splitTagFiles.clear()
        self.active = False


    def loadCaptions(self, files: Iterable[str], loadFunc: Callable[[str], str], cacheCurrent=True) -> str:
        self.clear(cacheCurrent)
        sepStrip = self.separator.strip()

        tagCount = TagCounter()
        tagOrderMap = defaultdict[TagData, list[float]](list)

        # TODO: Set self._edited to True if any captions have an entry in cache. (for turning Save button red)
        # Sort files for consistent tag order. FileList.selectedFiles is an unordered set.
        for file in sorted(files, key=sortKey):
            captionText = loadFunc(file)

            fileTags = FileTags(file)
            self._files.append(fileTags)

            tagCount.clear()
            tags = [tag for t in captionText.split(sepStrip) if (tag := t.strip())]

            for i, tag in enumerate(tags):
                # Allow duplicate tags. Map them across files:
                # File 1: 'tag, tag'      -> 2 TagData objects are created.
                # File 2: 'tag, tag, tag' -> Reuses the two TagData objects that were created for File 1, and adds a new one.
                count = tagCount.getAndIncrease(tag)

                tagList = self._tagData[tag]
                if len(tagList) > count:
                    tagData = tagList[count]
                else:
                    tagData = TagData(tag)
                    tagList.append(tagData)
                    self._tags.append(tagData)

                fileTags.appendTag(tagData)
                tagData.files[fileTags.file] = fileTags

                tagOrder = i / (len(tags)-1) if len(tags) > 1 else 0.0
                tagOrderMap[tagData].append(tagOrder)

            fileTags.edited = False

        if self._files:
            self.active = True

            # Stable sort. File order matters, because tag insertion order depends on it.
            tagOrderMap = {tag: self._order(orderValues) for tag, orderValues in tagOrderMap.items()}
            self._tags.sort(key=tagOrderMap.__getitem__)

            return self.separator.join(tag.tag for tag in self._tags)

        return ""

    @staticmethod
    def _order(values: list[float]) -> float:
        return sum(values) / len(values)


    def changeSeparator(self, separator: str, loadFunc: Callable[[str], str]) -> str:
        if self._edited:
            self._cacheCaptions()
        self.separator = separator
        files = [file.file for file in self._files]
        return self.loadCaptions(files, loadFunc, False)

    def _cacheCaptions(self):
        for file in self._files:
            if file.edited:
                caption = self.separator.join(file.tags)
                self.filelist.setData(file.file, DataKeys.Caption, caption)
                self.filelist.setData(file.file, DataKeys.CaptionState, DataKeys.IconStates.Changed)

    def saveCaptions(self, captionDest: FileTypeSelector) -> bool:
        if not self._files:
            return False

        success = True
        for file in self._files:
            caption = self.separator.join(file.tags)
            if captionDest.saveCaption(file.file, caption):
                self.filelist.removeData(file.file, DataKeys.Caption)
                self.filelist.setData(file.file, DataKeys.CaptionState, DataKeys.IconStates.Saved)
                file.edited = False
            else:
                success = False

        if success:
            self._edited = False
        return success


    # Used for input text and Bubbles (highlighting with HighlightState)
    def getTagPresence(self) -> list[float] | None:
        if self.active:
            return [len(tag.files) / len(self._files) for tag in self._tags]
        return None

    # Used for refined preview in Caption Window and preview in Batch Rules (highlighting without HighlightState)
    def getTotalTagPresence(self, tags: list[str], matchNode: MatcherNode) -> list[float] | None:
        if not self.active:
            return None

        if not self._splitTagFiles:
            self._updateSplitTagFiles(matchNode)

        presence = list[float]()
        for tag in tags:
            minPres = 2.0
            for splitTag in matchNode.splitAllPreserveExtra( (tag.strip(),) ):
                if files := self._splitTagFiles.get(splitTag):
                    pres = len(files) / len(self._files)
                    minPres = min(minPres, pres)

            presence.append(minPres if minPres < 2.0 else 0.0)

        return presence

    def _updateSplitTagFiles(self, matchNode: MatcherNode):
        for tag in self._tags:
            for splitTag in matchNode.splitAllPreserveExtra( (tag.tag,) ):
                self._splitTagFiles[splitTag].update(tag.files.values())


    def ensureFullPresence(self, index: int) -> bool:
        if not (0 <= index < len(self._tags)):
            return False
        tagData = self._tags[index]

        edited = False
        for file in self._files:
            if file.file not in tagData.files:
                tagData.files[file.file] = file
                file.appendTag(tagData)
                edited = True

        self._splitTagFiles.clear()
        self._edited |= edited
        return edited

    def getTagFiles(self, index: int) -> list[str]:
        if 0 <= index < len(self._tags):
            tagData = self._tags[index]
            return list( tagData.files.keys() )
        return []


    def _getOpCodes(self, a: list[TagData], b: list[str]) -> Generator[tuple[str, int, int, int, int]]:
        # SequenceMatcher can't handle duplicates which are next to each other.
        # It may detect edits to neighboring duplicate tags as insert+delete, which would break file association.
        # Use simple string comparison to catch simple edits. It's probably faster, too.
        op: tuple[str, int, int, int, int] | None = None

        tagCountChange = len(b) - len(a)
        if abs(tagCountChange) <= 1:
            iFirstDiff = next((i for i, (oldTag, newTag) in enumerate(zip(a, b)) if oldTag != newTag), -1)
            if iFirstDiff < 0:
                if tagCountChange > 0:
                    op = ("insert", len(a), len(a), len(a), len(b))  # Insert at end
                elif tagCountChange < 0:
                    op = ("delete", len(b), len(a), len(b), len(b))  # Remove last tag
                else:
                    yield ("equal", 0, len(a), 0, len(b))
                    return

            else:
                # Check if the two changed tags are neighbors (or check if same index when tagCountChange is 0).
                iLastDiff = next((i for i, (oldTag, newTag) in enumerate(zip(reversed(a), reversed(b))) if oldTag != newTag), -1)
                if iFirstDiff + iLastDiff == min(len(a), len(b)) - 1:
                    op = ("replace", iFirstDiff, len(a)-iLastDiff, iFirstDiff, len(b)-iLastDiff)

                # TODO: Check for deletion of neighboring duplicate tags: "tag, tag, tag" -> delete any via bubbles, and SequenceMatcher will always delete last one.
                #       When there are more tags around, it may delete any duplicate.
                #       It's impossible to determine through string processing which duplicate tag was deleted from a sequence.
                #       It only matters for duplicates that were manually entered next to another duplicate.
                #       Generally, deleting the last duplicate is the right thing to do, because it's the one with the fewest files.

        if op is not None:
            yield ("equal", 0, op[1], 0, op[3])
            yield op
            yield ("equal", op[2], len(a), op[4], len(b))
        else:
            matcher = SequenceMatcher(None, a, b, autojunk=False)
            yield from matcher.get_opcodes()

    def onCaptionEdited(self, captionText: str):
        a = self._tags
        b = [tag.strip() for tag in captionText.split(self.separator.strip())] # Include empty, but always stripped

        # Detect pairs of delete+insert as moves
        deletedTags: dict[str, list[int]] = defaultdict(list)  # References items in 'a'
        insertedTags: dict[str, list[int]] = defaultdict(list) # References placeholder indexes in 'newTagList'

        newTagList: list[TagData | None] = list()

        # NOTE: Big changes with more than one change means paste
        for op, i1, i2, j1, j2 in self._getOpCodes(a, b):
            if op == "equal":
                logger.debug("Op Equal:   (i1=%s, i2=%s, lenA=%s),  (j1=%s, j2=%s, lenB=%s)", i1, i2, i2-i1, j1, j2, j2-j1)
                newTagList.extend(a[i1:i2]) # Can be empty list
                continue

            self._edited = True

            match op:
                case "replace":
                    oldTags = a[i1:i2]
                    newTags = b[j1:j2]

                    logger.debug("Op Replace: %s => %s", oldTags, newTags)

                    if len(oldTags) == 1 and len(newTags) == 2:
                        if self._opSplit(newTagList, oldTags, newTags, i1):
                            continue
                    elif len(oldTags) == 2 and len(newTags) == 1:
                        if self._opMerge(newTagList, oldTags, newTags):
                            continue

                    # TODO: Detect move, when a tag is replaced with another existing tag. And it's not a duplicate.
                    #       Or not?
                    # 'blabla, red tree, monster'  =>  'monster, red tree'
                    # Replace: 'blabla' => 'monster'
                    # Delete:  'monster'

                    self._opReplace(newTagList, oldTags, newTags)

                case "delete":
                    logger.debug("Op Delete:  %s", a[i1:i2])
                    for i in range(i1, i2):
                        tagText = self._tags[i].tag
                        deletedTags[tagText].append(i)

                case "insert":
                    newTags = b[j1:j2]
                    logger.debug("Op Insert:  %s  between  %s  (i1 = %s)", newTags, a[i1-1:i1+1], i1)
                    for tagText in newTags:
                        tagIndex = len(newTagList)
                        insertedTags[tagText].append(tagIndex)
                        newTagList.append(None) # Add empty placeholder

        # Try swapping moved tags. _opMove consumes entries from 'deletedTags' and 'insertedTags'.
        # NOTE: It is not necessarily the moved tag which is detected as deleted/inserted:
        #       When two neighboring tags are swapped, it will detect the new left tag as moved.
        self._opMove(newTagList, deletedTags, insertedTags)

        self._opDelete(deletedTags)
        self._opInsert(newTagList, insertedTags)

        # Handle empty caption: Ensure all files have at least one empty tag.
        # When writing text, this empty tag is modified in all files.
        if len(newTagList) == 0:
            newTagList.append(self._createTag("", self._files))
        elif len(newTagList) == 1 and not newTagList[0].tag:
            self._appendTagFiles(self._files, newTagList[0])

        self._tags = newTagList
        self._splitTagFiles.clear()

        assert len(newTagList) == len(b)
        assert all(tag.tag == tagText for tag, tagText in zip(newTagList, b))


    # Handle insertion of separator (after writing in the middle of text) by splitting a tag.
    # Make new tag for the left side of comma. Add this tag to the same files.
    # Update the right side.
    def _opSplit(self, newTagList: list[TagData | None], oldTags: list[TagData], newTags: list[str], oldIndex: int) -> bool:
        oldTag = oldTags[0]
        newTextLeft = newTags[0]
        newTextRight = newTags[1]

        middle = oldTag.tag.removeprefix(newTextLeft).removesuffix(newTextRight)
        if middle and not middle.isspace():
            return False

        logger.debug("  Comma inserted, split: '%s' => '%s', '%s'   -   middle: '%s'", oldTag, newTextLeft, newTextRight, middle)

        # Add tag to same files as oldTag. When the comma is removed again, this operation is undone without further effects.
        tag = self._createTag(newTextLeft, oldTag.files.values())
        newTagList.append(tag)

        self._updateTag(oldTag, newTextRight)
        newTagList.append(oldTag)

        # Sort new tag before old tag
        tagOrder = oldIndex / (len(self._tags)-1) if len(self._tags) > 1 else 0.0
        extraOrder = ((tag, tagOrder-self.ORDER_OFFSET), (oldTag, tagOrder+self.ORDER_OFFSET))
        for file in tag.files.values():
            file.sortFilesRel(extraOrder)

        return True


    # Handle removal of separator by merging tags: Keep one, remove the other.
    # It doesn't matter which one is kept/removed: They are adjacent and the files are transferred.
    # The resulting tag will be present in all files which had one of the original tags.
    def _opMerge(self, newTagList: list[TagData | None], oldTags: list[TagData], newTags: list[str]) -> bool:
        oldLeft = oldTags[0]  # Keep
        oldRight = oldTags[1] # Delete
        newText = newTags[0]

        middle = newText.removeprefix(oldLeft.tag).removesuffix(oldRight.tag)
        if middle and not middle.isspace():
            return False

        logger.debug(f"  Comma removed, merge: '%s', '%s => %s   -   middle: '%s'", oldLeft.tag, oldRight.tag, newText, middle)

        self._appendTagFiles(oldRight.files.values(), oldLeft)
        self._deleteTag(oldRight)

        self._updateTag(oldLeft, newText)
        newTagList.append(oldLeft)
        return True


    def _opReplace(self, newTagList: list[TagData | None], oldTags: list[TagData], newTags: list[str]):
        # Can replace multiple with multiple.
        # Replace can also mean: Multiple tags removed with some extra separators left

        # Replace text
        for oldTag, newText in zip(oldTags, newTags):
            self._updateTag(oldTag, newText)
            newTagList.append(oldTag)

        iExtra = min(len(oldTags), len(newTags))

        # Add new tags
        for newText in newTags[iExtra:]:
            newTagList.append( self._createTag(newText, self._files) )

        # Remove old tags
        for oldTag in oldTags[iExtra:]:
            self._deleteTag(oldTag)


    def _opMove(self, newTagList: list[TagData | None], deletedTags: dict[str, list[int]], insertedTags: dict[str, list[int]]):
        fileTagsNeedSorting: dict[FileTags, set[TagData]] = defaultdict(set)
        movedTagOrder: dict[TagData, float] = dict()

        movedTags = deletedTags.keys() & insertedTags.keys()
        for tagText in movedTags:
            deleteIndexes = deletedTags.pop(tagText)
            insertIndexes = insertedTags.pop(tagText)

            for iDel, iIns in zip(deleteIndexes, insertIndexes):
                tag = self._tags[iDel]
                logger.debug("  Move: '%s' (%s) => (%s)", tag, iDel, iIns)
                assert newTagList[iIns] is None
                newTagList[iIns] = tag

                for file in tag.files.values():
                    fileTagsNeedSorting[file].add(tag)

                tagOrder = iIns / (len(newTagList)-1) if len(newTagList) > 1 else 0.0
                tagOrder += self.ORDER_OFFSET if iIns > iDel else -self.ORDER_OFFSET
                movedTagOrder[tag] = tagOrder

            iExtra = min(len(deleteIndexes), len(insertIndexes))

            # Handle additional deletes
            extraDeletes = deleteIndexes[iExtra:]
            logger.debug("    Additional deletes: %s", extraDeletes)
            for iDel in extraDeletes:
                self._deleteTag(self._tags[iDel])

            # Handle additional inserts
            extraInserts = insertIndexes[iExtra:]
            logger.debug("    Additional inserts: %s", extraInserts)
            for iIns in extraInserts:
                assert newTagList[iIns] is None
                newTagList[iIns] = self._createTag(tagText, self._files)

        # Reorder tags in files
        for file, movedTags in fileTagsNeedSorting.items():
            file.sortFilesRel((tag, movedTagOrder[tag]) for tag in movedTags)


    def _opDelete(self, deletedTags: dict[str, list[int]]):
        for deleteIndexes in deletedTags.values():
            for iDel in deleteIndexes:
                self._deleteTag(self._tags[iDel])

    def _opInsert(self, newTagList: list[TagData | None], insertedTags: dict[str, list[int]]):
        for tagText, insertIndexes in insertedTags.items():
            for iIns in insertIndexes:
                assert newTagList[iIns] is None
                newTagList[iIns] = self._createTag(tagText, self._files)


    def _createTag(self, tagText: str, files: Iterable[FileTags]) -> TagData:
        logger.debug(">> Create Tag: '%s'", tagText)
        assert len(tagText) == len(tagText.strip())

        tag = TagData(tagText)
        self._tagData[tagText].append(tag)

        for file in files:
            tag.files[file.file] = file
            file.appendTag(tag)

        return tag

    def _updateTag(self, tag: TagData, newText: str):
        logger.debug(">> Update Tag: '%s' => '%s'", tag.tag, newText)
        assert len(newText) == len(newText.strip())

        self._removeTagFromMap(tag)

        tag.tag = newText
        self._tagData[newText].append(tag)

    def _deleteTag(self, tag: TagData):
        logger.debug(">> Delete Tag: '%s'", tag)

        for file in tag.files.values():
            file.removeTag(tag)

        self._removeTagFromMap(tag)

    def _removeTagFromMap(self, tag: TagData):
        tagText = tag.tag
        tagList = self._tagData.get(tagText)

        if tagList is None:
            logger.warning(f"_removeTagFromMap: No mapping for tag '{tagText}'")
            return
        if not tagList:
            logger.warning(f"_removeTagFromMap: Tag '{tagText}' mapped to empty list")
            return

        for i, t in enumerate(tagList):
            if t is tag:
                del tagList[i]
                break
        else:
            logger.warning(f"_removeTagFromMap: Tag '{tagText}' not found in list")

        if not tagList:
            del self._tagData[tagText]

    def _appendTagFiles(self, files: Iterable[FileTags], dest: TagData):
        for file in files:
            if file.file not in dest.files:
                dest.files[file.file] = file
                file.appendTag(dest)
