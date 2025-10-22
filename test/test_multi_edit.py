import sys, os
sys.path.append( os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) )

import unittest
from caption.caption_multi_edit import CaptionMultiEdit
from lib.filelist import FileList, DataKeys


F1 = "A"
F2 = "B"
F3 = "C"

FILES = [F1, F2, F3]


class BaseMultiEditTest(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(BaseMultiEditTest, self).__init__(*args, **kwargs)
        self.filelist: FileList = None
        self.multiEdit: CaptionMultiEdit = None

    def __getitem__(self, file: str) -> str:
        text = self.filelist.getData(file, DataKeys.Caption)
        if text is not None:
            return text
        self.fail(f"File '{file}' has no cached caption")

    def __setitem__(self, file: str, caption: str):
        self.filelist.setData(file, DataKeys.Caption, caption)

    def text(self):
        return self.multiEdit.separator.join(tag.tag for tag in self.multiEdit._tags)

    def assertLoad(self, expectedText: str):
        text = self.multiEdit.loadCaptions(FILES, self.__getitem__)
        self.assertEqual(text, expectedText)

    def assertEdit(self, newText: str, expectedText: str | None = None):
        self.multiEdit.onCaptionEdited(newText)
        self.multiEdit._cacheCaptions()
        self.assertEqual(self.text(), newText if expectedText is None else expectedText)

    def assertEditState(self, file: str, expectedState: DataKeys.IconStates | None):
        editState = self.filelist.getData(file, DataKeys.CaptionState)
        if expectedState is None:
            self.assertIsNone(editState)
        else:
            self.assertEqual(editState, expectedState)

    def assertMakeFullPresence(self, index: int):
        text = self.text()
        self.multiEdit.ensureFullPresence(index)
        self.multiEdit._cacheCaptions()
        self.assertEqual(self.text(), text)



class CaptionMultiEditTest(BaseMultiEditTest):
    def setUp(self):
        self.filelist = FileList()
        self.multiEdit = CaptionMultiEdit(self.filelist)

    def tearDown(self):
        del self.multiEdit
        del self.filelist


    def testLoadNone(self):
        self[F1] = "tag1"
        self[F2] = "tag2"
        self[F3] = None

        with self.assertRaises(Exception):
            self.multiEdit.loadCaptions(FILES, lambda file: self.filelist.getData(file, DataKeys.Caption))


    def testAddTagBack(self):
        self[F1] = "tag1, tag2, tag3"
        self[F2] = "tag1, tag2"
        self[F3] = "tag2, tag3"

        self.assertLoad("tag1, tag2, tag3")
        self.assertEdit("tag1, tag2, tag3, tag4")

        self.assertEqual(self[F1], "tag1, tag2, tag3, tag4")
        self.assertEqual(self[F2], "tag1, tag2, tag4")
        self.assertEqual(self[F3], "tag2, tag3, tag4")

    def testAddTagFront(self):
        self[F1] = "tag1, tag2, tag3"
        self[F2] = "tag1, tag2"
        self[F3] = "tag2, tag3"

        self.assertLoad("tag1, tag2, tag3")
        self.assertEdit("tag4, tag1, tag2, tag3")

        self.assertEqual(self[F1], "tag1, tag2, tag3, tag4")
        self.assertEqual(self[F2], "tag1, tag2, tag4")
        self.assertEqual(self[F3], "tag2, tag3, tag4")

    def testAddTagMiddle(self):
        self[F1] = "tag1, tag2, tag3"
        self[F2] = "tag1, tag2"
        self[F3] = "tag2, tag3"

        self.assertLoad("tag1, tag2, tag3")
        self.assertEdit("tag1, tag2, tag4, tag3")

        self.assertEqual(self[F1], "tag1, tag2, tag3, tag4")
        self.assertEqual(self[F2], "tag1, tag2, tag4")
        self.assertEqual(self[F3], "tag2, tag3, tag4")


    def testRemoveTagBack(self):
        self[F1] = "tag1, tag2, tag3"
        self[F2] = "tag1, tag2"
        self[F3] = "tag2, tag3"

        self.assertLoad("tag1, tag2, tag3")
        self.assertEdit("tag1, tag2")

        self.assertEqual(self[F1], "tag1, tag2")
        self.assertEqual(self[F2], "tag1, tag2")
        self.assertEqual(self[F3], "tag2")

    def testRemoveTagFront(self):
        self[F1] = "tag1, tag2, tag3"
        self[F2] = "tag1, tag2"
        self[F3] = "tag2, tag3"

        self.assertLoad("tag1, tag2, tag3")
        self.assertEdit("tag2, tag3")

        self.assertEqual(self[F1], "tag2, tag3")
        self.assertEqual(self[F2], "tag2")
        self.assertEqual(self[F3], "tag2, tag3")

    def testRemoveTagMiddle(self):
        self[F1] = "tag1, tag2, tag3"
        self[F2] = "tag1, tag2"
        self[F3] = "tag2, tag3"

        self.assertLoad("tag1, tag2, tag3")
        self.assertEdit("tag1, tag3")

        self.assertEqual(self[F1], "tag1, tag3")
        self.assertEqual(self[F2], "tag1")
        self.assertEqual(self[F3], "tag3")

    def testRemoveAll(self):
        self[F1] = "tag1, tag2, tag3"
        self[F2] = "tag1, tag2"
        self[F3] = "tag2, tag3"

        self.assertLoad("tag1, tag2, tag3")
        self.assertEdit("")

        self.assertEqual(self[F1], "")
        self.assertEqual(self[F2], "")
        self.assertEqual(self[F3], "")

        self.assertEdit("tag")

        self.assertEqual(self[F1], "tag")
        self.assertEqual(self[F2], "tag")
        self.assertEqual(self[F3], "tag")


    def testEdit(self):
        self[F1] = "tag1, tag2, tag3"
        self[F2] = "tag1, tag2"
        self[F3] = "tag2, tag3"

        self.assertLoad("tag1, tag2, tag3")
        self.assertEdit("tag1, tag2, tag4")

        self.assertEqual(self[F1], "tag1, tag2, tag4")
        self.assertEqual(self[F2], "tag1, tag2")
        self.assertEqual(self[F3], "tag2, tag4")

    def testEdit2(self):
        self[F1] = "tag1, tag2, tag3"
        self[F2] = "tag1, tag2"
        self[F3] = "tag2, tag3"

        self.assertLoad("tag1, tag2, tag3")
        self.assertEdit("tag1, tag4, tag5")

        self.assertEqual(self[F1], "tag1, tag4, tag5")
        self.assertEqual(self[F2], "tag1, tag4")
        self.assertEqual(self[F3], "tag4, tag5")


    def testSplit(self):
        self[F1] = "tag1, tag2, tag3"
        self[F2] = "tag1, tag2"
        self[F3] = "tag2, tag3"

        self.assertLoad("tag1, tag2, tag3")
        self.assertEdit("tag1, tag2, ta,g3", "tag1, tag2, ta, g3")

        self.assertEqual(self[F1], "tag1, tag2, ta, g3")
        self.assertEqual(self[F2], "tag1, tag2")
        self.assertEqual(self[F3], "tag2, ta, g3")

    def testMerge(self):
        self[F1] = "tag1, tag2, ta, g3"
        self[F2] = "tag1, tag2"
        self[F3] = "tag2, ta, g3"

        self.assertLoad("tag1, tag2, ta, g3")
        self.assertEdit("tag1, tag2, tag3")

        self.assertEqual(self[F1], "tag1, tag2, tag3")
        self.assertEqual(self[F2], "tag1, tag2")
        self.assertEqual(self[F3], "tag2, tag3")

    def testMerge2(self):
        self[F1] = "tag1, tag2, ta"
        self[F2] = "tag1, tag2"
        self[F3] = "tag2, g3"

        self.assertLoad("tag1, tag2, ta, g3")
        self.assertEdit("tag1, tag2, tag3")

        self.assertEqual(self[F1], "tag1, tag2, tag3")
        self.assertEqual(self[F2], "tag1, tag2")
        self.assertEqual(self[F3], "tag2, tag3")

    def testMergeWhitespace(self):
        self[F1] = "tag1, tag2, ta"
        self[F2] = "tag1, tag2"
        self[F3] = "tag2, g3"

        self.assertLoad("tag1, tag2, ta, g3")
        self.assertEdit("tag1, tag2, ta   g3")

        self.assertEqual(self[F1], "tag1, tag2, ta   g3")
        self.assertEqual(self[F2], "tag1, tag2")
        self.assertEqual(self[F3], "tag2, ta   g3")


    def testMove(self):
        self[F1] = "tag1, tag2, tag3"
        self[F2] = "tag1, tag2"
        self[F3] = "tag2, tag3"

        self.assertLoad("tag1, tag2, tag3")
        self.assertEdit("tag3, tag1, tag2")

        self.assertEqual(self[F1], "tag3, tag1, tag2")
        self.assertEqual(self[F2], "tag1, tag2")
        self.assertEqual(self[F3], "tag3, tag2")


    def testDuplicateEdit(self):
        self[F1] = "tag1, tag2, tag3"
        self[F2] = "tag2, tag2, tag4"
        self[F3] = "tag1, tag2, tag2, tag3, tag4"

        self.assertLoad("tag1, tag2, tag2, tag3, tag4") # tag2 x2
        self.assertEdit("tag1, tag2, tag3, tag3, tag4") # tag3 x2

        self.assertEqual(self[F1], "tag1, tag2, tag3")
        self.assertEqual(self[F2], "tag2, tag3, tag4")
        self.assertEqual(self[F3], "tag1, tag2, tag3, tag3, tag4")

    def testDuplicateEdit2(self):
        self[F1] = "tag, tag, tag"
        self[F2] = "tag, tag, tag, tag"
        self[F3] = "tag, tag, tag, tag, tag"

        self.assertLoad("tag, tag, tag, tag, tag")
        self.assertEdit("tag1, tag2, tag3, tag4, tag5")

        self.assertEqual(self[F1], "tag1, tag2, tag3")
        self.assertEqual(self[F2], "tag1, tag2, tag3, tag4")
        self.assertEqual(self[F3], "tag1, tag2, tag3, tag4, tag5")

    def testDuplicateEdit3(self):
        self[F1] = "tag, tag, tag"
        self[F2] = "tag, tag, tag, tag"
        self[F3] = "tag, tag, tag, tag, tag"

        self.assertLoad("tag, tag, tag, tag, tag")
        self.assertEdit("tag1, tag, tag, tag, tag")

        self.assertEqual(self[F1], "tag1, tag, tag")
        self.assertEqual(self[F2], "tag1, tag, tag, tag")
        self.assertEqual(self[F3], "tag1, tag, tag, tag, tag")

        self.assertEdit("tag1, tag2, tag, tag, tag")

        self.assertEqual(self[F1], "tag1, tag2, tag")
        self.assertEqual(self[F2], "tag1, tag2, tag, tag")
        self.assertEqual(self[F3], "tag1, tag2, tag, tag, tag")

        self.assertEdit("tag1, tag2, tag, tag, tag5")

        self.assertEqual(self[F1], "tag1, tag2, tag")
        self.assertEqual(self[F2], "tag1, tag2, tag, tag")
        self.assertEqual(self[F3], "tag1, tag2, tag, tag, tag5")

        self.assertEdit("tag1, tag2, tag, tag4, tag5")

        self.assertEqual(self[F1], "tag1, tag2, tag")
        self.assertEqual(self[F2], "tag1, tag2, tag, tag4")
        self.assertEqual(self[F3], "tag1, tag2, tag, tag4, tag5")

        self.assertEdit("tag1, tag2, tag3, tag4, tag5")

        self.assertEqual(self[F1], "tag1, tag2, tag3")
        self.assertEqual(self[F2], "tag1, tag2, tag3, tag4")
        self.assertEqual(self[F3], "tag1, tag2, tag3, tag4, tag5")

    def testDuplicateEdit4(self):
        self[F1] = "tag, tag, tag"
        self[F2] = "tag, tag, tag, tag"
        self[F3] = "tag, tag, tag, tag, tag"

        self.assertLoad("tag, tag, tag, tag, tag")
        self.assertEdit("tag tag, tag, tag, tag") # merge

        self.assertEqual(self[F1], "tag tag, tag")
        self.assertEqual(self[F2], "tag tag, tag, tag")
        self.assertEqual(self[F3], "tag tag, tag, tag, tag")


    def testChainEdit(self):
        self[F1] = "tag1"
        self[F2] = "tag2"
        self[F3] = "tag3"

        self.assertLoad("tag1, tag2, tag3")

        self.assertEdit("tag1, tag2, tag3, tagAdd") # Add
        self.assertEqual(self[F1], "tag1, tagAdd")
        self.assertEqual(self[F2], "tag2, tagAdd")
        self.assertEqual(self[F3], "tag3, tagAdd")

        self.assertEdit("tagAdd, tag1, tag2, tag3") # Move
        self.assertEqual(self[F1], "tagAdd, tag1")
        self.assertEqual(self[F2], "tagAdd, tag2")
        self.assertEqual(self[F3], "tagAdd, tag3")

        self.assertEdit("tagAdd, tag1 tag2, tag3") # Merge
        self.assertEqual(self[F1], "tagAdd, tag1 tag2")
        self.assertEqual(self[F2], "tagAdd, tag1 tag2")
        self.assertEqual(self[F3], "tagAdd, tag3")

        self.assertEdit("tagAdd, tagEdit, tag3") # Edit
        self.assertEqual(self[F1], "tagAdd, tagEdit")
        self.assertEqual(self[F2], "tagAdd, tagEdit")
        self.assertEqual(self[F3], "tagAdd, tag3")

        self.assertEdit("tagAdd, tag, Edit, tag3") # Split
        self.assertEqual(self[F1], "tagAdd, tag, Edit")
        self.assertEqual(self[F2], "tagAdd, tag, Edit")
        self.assertEqual(self[F3], "tagAdd, tag3")

        self.assertMakeFullPresence(1) # 'tag'
        self.assertEqual(self[F1], "tagAdd, tag, Edit")
        self.assertEqual(self[F2], "tagAdd, tag, Edit")
        self.assertEqual(self[F3], "tagAdd, tag3, tag")  # TODO: Sort new tag?

        self.assertEdit("tagAdd, tagEdit, tag3") # Merge
        self.assertEqual(self[F1], "tagAdd, tagEdit")
        self.assertEqual(self[F2], "tagAdd, tagEdit")
        self.assertEqual(self[F3], "tagAdd, tag3, tagEdit")

        self.assertEdit("tagAdd, tagAdd, tagEdit, tag3") # Add duplicate
        self.assertEqual(self[F1], "tagAdd, tagEdit, tagAdd")
        self.assertEqual(self[F2], "tagAdd, tagEdit, tagAdd")
        self.assertEqual(self[F3], "tagAdd, tag3, tagEdit, tagAdd")


    def testEditState(self):
        self[F1] = "tag1, tag2, tag3"
        self[F2] = "tag1, tag2"
        self[F3] = "tag2, tag3"

        self.assertLoad("tag1, tag2, tag3")

        self.assertFalse(self.multiEdit.isEdited)
        self.assertEditState(F1, None)
        self.assertEditState(F2, None)
        self.assertEditState(F3, None)

        self.assertEdit("tag1Edit, tag2, tag3")
        self.assertEqual(self[F1], "tag1Edit, tag2, tag3")
        self.assertEqual(self[F2], "tag1Edit, tag2")
        self.assertEqual(self[F3], "tag2, tag3")

        self.assertTrue(self.multiEdit.isEdited)
        self.assertEditState(F1, DataKeys.IconStates.Changed)
        self.assertEditState(F2, DataKeys.IconStates.Changed)
        self.assertEditState(F3, None)

        self.assertEdit("tag1Edit, tag2, tag3Edit")
        self.assertEqual(self[F1], "tag1Edit, tag2, tag3Edit")
        self.assertEqual(self[F2], "tag1Edit, tag2")
        self.assertEqual(self[F3], "tag2, tag3Edit")

        self.assertTrue(self.multiEdit.isEdited)
        self.assertEditState(F1, DataKeys.IconStates.Changed)
        self.assertEditState(F2, DataKeys.IconStates.Changed)
        self.assertEditState(F3, DataKeys.IconStates.Changed)



# TODO: Detect move, when a tag is replaced with another existing tag. And it's not a duplicate.
#       'blabla, red tree, monster'  =>  'monster, red tree'

# >> Updated Tags:
# blabla, red tree, monster

# Op Replace: [TagData('blabla')] => ['monster']
# >> Update Tag: 'blabla' => 'monster'
# Op Equal:   (i1=1, i2=2, lenA=1),  (j1=1, j2=2, lenB=1)
# Op Delete:  [TagData('monster')]
# >> Delete Tag: 'monster'

# >> Updated Tags:
# monster, red tree


if __name__ == '__main__':
    unittest.main(verbosity=2)
