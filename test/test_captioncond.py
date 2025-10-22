import sys, os
sys.path.append( os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) )

import unittest
from caption.caption_conditionals import *


class CaptionFilterTest(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def assertCondResult(self, result: ConditionResult, expectedTags: list[str]):
        if expectedTags:
            self.assertTrue(result[0])
            if result[1] is None:
                self.fail(f"Resulting tags is None, expected: {expectedTags}")
            self.assertListEqual(result[1], expectedTags)
        else:
            self.assertFalse(result[0])
            self.assertIsNone(result[1])

    def assertCondFalse(self, result: ConditionResult):
        self.assertFalse(result[0])
        self.assertIsNone(result[1])


    def testCondAllTagsPresent(self):
        cond = createCondAllTagsPresent(["tag1, tag2"])

        result = cond(["tag0", "tag2", "tag1", "tag3", "tag2"])
        self.assertCondResult(result, ["tag2", "tag1"])

        result = cond(["tag0", "tag1", "tag1", "tag3"])
        self.assertCondFalse(result)

        cond = createCondAllTagsPresent([""])
        result = cond(["tag1"])
        self.assertCondFalse(result)


    def testCondAnyWordsPresent(self):
        cond = createCondAnyWordsPresent(["shirt, tank top, pants"])

        result = cond(["black boots", "red shirt"])
        self.assertCondResult(result, ["shirt"])

        result = cond(["black boots", "blue tank top", "red shirt"])
        self.assertCondResult(result, ["tank top"])

        result = cond(["black boots", "pants with holes", "blue tank top"])
        self.assertCondResult(result, ["pants"])

        result = cond(["_shirt", "tank top_", "tank_top", "_pants_"])
        self.assertCondResult(result, [])

        result = cond(["boots", "sandals", "socks"])
        self.assertCondResult(result, [])

    def testCondAnyWordsPresentEmpty(self):
        cond = createCondAnyWordsPresent([""])

        result = cond(["boots", "shirt"])
        self.assertCondResult(result, [])

        result = cond([])
        self.assertCondResult(result, [])


    def testActReplaceWords(self):
        varParser = ConditionVariableParser({"A": ["shirt"]})

        action = createActionReplaceWords(["tank top, shirt, jacket", "{{A}},{{A}},{{A}}"])
        tags = action(varParser, ["red tank top top tank tank top", "blue print shirt", "jacket black market"])
        self.assertListEqual(tags, ["red shirt top tank shirt", "blue print shirt", "shirt black market"])

        action = createActionReplaceWords(["tank top, shirt, jacket", "test,test,test"])
        tags = action(varParser, ["_tank top", "tank top_", " shirt", "jacket ", "jacket tank top shirt"])
        self.assertListEqual(tags, ["_tank top", "tank top_", " test", "test ", "test test test"])

        action = createActionReplaceWords(["{{A}}", "red pants"])
        tags = action(varParser, ["tank top", "shirt", "jacket"])
        self.assertListEqual(tags, ["tank top", "red pants", "jacket"])

        action = createActionReplaceWords(["", "{{A}}"])
        tags = action(varParser, ["tank top", "shirt", "jacket"])
        self.assertListEqual(tags, ["tank top", "shirt", "jacket"])

        action = createActionReplaceWords(["", ""])
        tags = action(varParser, [])
        self.assertListEqual(tags, [])

    def testActReplaceLastWords(self):
        varParser = ConditionVariableParser({"A": ["shirt"]})

        action = createActionReplaceLastWords(["pants, tank top", "shorts,{{A}}"])
        tags = action(varParser, ["black pants", "pants holder", "white tank top", "tank top stack"])
        self.assertListEqual(tags, ["black shorts", "pants holder", "white shirt", "tank top stack"])

        # No space
        action = createActionReplaceLastWords(["pants, tank top", "test,test"])
        tags = action(varParser, ["blackpants", "pantsholder", "whitetank top"])
        self.assertListEqual(tags, ["blackpants", "pantsholder", "whitetank top"])

        # Multiple prefix words
        action = createActionReplaceLastWords(["pants, tank top", "shorts,{{A}}"])
        tags = action(varParser, ["very long black pants", "pants long pants", "white frilled tank top", "tank top tank top"])
        self.assertListEqual(tags, ["very long black shorts", "pants long shorts", "white frilled shirt", "tank top shirt"])

        # Only one word
        action = createActionReplaceLastWords(["pants, tank top", "shorts,{{A}}"])
        tags = action(varParser, ["pants", "something", "tank top"])
        self.assertListEqual(tags, ["shorts", "something", "shirt"])

        # Missing params
        action = createActionReplaceLastWords(["", ""])
        tags = action(varParser, ["pants", "tank top"])
        self.assertListEqual(tags, ["pants", "tank top"])

        action = createActionReplaceLastWords(["pants, tank top", "test"])
        tags = action(varParser, ["pants", "tank top"])
        self.assertListEqual(tags, ["test", "tank top"])

        action = createActionReplaceLastWords(["pants", "test1,test2"])
        tags = action(varParser, ["pants", "tank top"])
        self.assertListEqual(tags, ["test1", "tank top"])

        # Replace to empty
        action = createActionReplaceLastWords(["pants, tank top", ","])
        tags = action(varParser, ["pants", "tank top"])
        self.assertListEqual(tags, ["", ""])

        # Empty input
        action = createActionReplaceLastWords(["pants", "test"])
        tags = action(varParser, [])
        self.assertListEqual(tags, [])



if __name__ == '__main__':
    unittest.main(verbosity=2)
