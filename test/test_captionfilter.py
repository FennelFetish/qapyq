import sys, os
sys.path.append( os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) )

import unittest
from caption.caption_filter import CaptionRulesProcessor
from caption.caption_preset import MutualExclusivity


class BaseCaptionFilterTest(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(BaseCaptionFilterTest, self).__init__(*args, **kwargs)
        self.rulesProcessor: CaptionRulesProcessor = None

    def assertProcessedEqual(self, caption: str, expected: str):
        result = self.rulesProcessor.process(caption)
        self.assertEqual(expected, result)



class CaptionFilterTest(BaseCaptionFilterTest):
    def setUp(self):
        prefix = ""
        suffix = ""
        seperator = ", "
        removeDup = True
        sortCaptions = True
        whitelistGroups = False

        groups = [
            (["straight-on", "from side", "from behind", "standing", "sitting"], MutualExclusivity.Disabled, False),
            (["long pants", "black pants", "white pants", "denim pants", "pants"], MutualExclusivity.Disabled, True),
            (["black tank top", "white tank top", "frilled tank top", "polka dot tank top"], MutualExclusivity.Disabled, True),
            (["long hair", "dark hair", "blonde hair", "brown hair", "black hair", "hair ornament"], MutualExclusivity.Disabled, True)
        ]

        bans = ["realistic", "blurry"]

        self.rulesProcessor = CaptionRulesProcessor()
        self.rulesProcessor.setup(prefix, suffix, seperator, removeDup, sortCaptions, whitelistGroups)
        self.rulesProcessor.setBannedCaptions(bans)
        self.rulesProcessor.setCaptionGroups(groups)

    def tearDown(self):
        del self.rulesProcessor


    def test_sort(self):
        caption  = "black pants, other1, blonde hair, sitting, other2, from side"
        expected = "from side, sitting, black pants, blonde hair, other1, other2"
        self.assertProcessedEqual(caption, expected)

    def test_sort_combined(self):
        caption  = "denim pants, black pants, blonde hair, other, long pants, hair ornament, sitting, from side"
        expected = "from side, sitting, long black denim pants, blonde hair, hair ornament, other"
        self.assertProcessedEqual(caption, expected)

    def test_sort_partial(self):
        # 'short pants' is not sorted, because it has too many extra words ('short').
        caption  = "short pants, red blonde hair, standing"
        expected = "standing, red blonde hair, short pants"
        self.assertProcessedEqual(caption, expected)

    def test_combine(self):
        caption  = "white polka dot tank top, long white pants, torn pants, black frilled tank top, black denim pants"
        expected = "long black white denim pants, black white frilled polka dot tank top, torn pants"
        self.assertProcessedEqual(caption, expected)

    def test_combine_partial(self):
        # 'red blonde hair' is not combined with 'long hair', because it has extra words ('red').
        caption  = "red blonde hair, black denim pants, long hair, long pants"
        expected = "long black denim pants, long hair, red blonde hair"
        self.assertProcessedEqual(caption, expected)

    def test_ban(self):
        caption  = "black hair, realistic, white pants, blurry"
        expected = "white pants, black hair"
        self.assertProcessedEqual(caption, expected)

    def test_remove_duplicates(self):
        caption  = "black hair, white pants, black hair, white pants"
        expected = "white pants, black hair"
        self.assertProcessedEqual(caption, expected)

    def test_remove_subsets(self):
        caption  = "sitting on chair, ornament, chair, black hair, hair ornament, sitting"
        expected = "black hair, hair ornament, sitting on chair"
        self.assertProcessedEqual(caption, expected)

    def test_remove_subsets_combine(self):
        # 'long hair' is a subset of 'long red hair', but it is combined with 'black hair' before removing subsets
        caption  = "black hair, long red hair, long hair"
        expected = "long red hair, long black hair"
        self.assertProcessedEqual(caption, expected)

    def test_strip_remove_empty(self):
        caption  = ",,long hair  ,, ,   black pants,  ,"
        expected = "black pants, long hair"
        self.assertProcessedEqual(caption, expected)

    def test_empty(self):
        caption  = ""
        expected = ""
        self.assertProcessedEqual(caption, expected)



class CaptionFilterPrefixSuffixTest(BaseCaptionFilterTest):
    def setUp(self):
        prefix = "pre1, pre2, "
        suffix = ", suf1, suf2"
        seperator = ", "
        removeDup = True
        sortCaptions = True
        whitelistGroups = False

        groups = [
            (["long pants", "black pants", "white pants", "denim pants", "pants"], MutualExclusivity.Disabled, True)
        ]

        self.rulesProcessor = CaptionRulesProcessor()
        self.rulesProcessor.setup(prefix, suffix, seperator, removeDup, sortCaptions, whitelistGroups)
        self.rulesProcessor.setCaptionGroups(groups)

    def tearDown(self):
        del self.rulesProcessor


    def test_prefix_suffix(self):
        caption  = "denim pants, black pants"
        expected = "pre1, pre2, black denim pants, suf1, suf2"
        self.assertProcessedEqual(caption, expected)

    def test_sorted_prefix_suffix(self):
        caption  = "suf1, denim pants, suf2, pre2, black pants, pre1"
        expected = "pre1, pre2, black denim pants, suf1, suf2"
        self.assertProcessedEqual(caption, expected)



class CaptionFilterMutualExclusivityTest(BaseCaptionFilterTest):
    def setUp(self):
        prefix = ""
        suffix = ""
        seperator = ", "
        removeDup = True
        sortCaptions = True
        whitelistGroups = False

        groups = [
            (["blue eyes", "green eyes", "brown eyes"], MutualExclusivity.KeepFirst, False),
            (["black pants", "white pants", "blue pants"], MutualExclusivity.KeepLast, True), # Combine enabled
            (["lying", "sitting", "standing"], MutualExclusivity.Priority, False)
        ]

        self.rulesProcessor = CaptionRulesProcessor()
        self.rulesProcessor.setup(prefix, suffix, seperator, removeDup, sortCaptions, whitelistGroups)
        self.rulesProcessor.setCaptionGroups(groups)

    def tearDown(self):
        del self.rulesProcessor


    def test_keep_first(self):
        caption  = "green eyes, black pants, brown eyes, blue eyes"
        expected = "green eyes, black pants"
        self.assertProcessedEqual(caption, expected)

    def test_keep_last(self):
        caption  = "blue pants, black pants, brown eyes, white pants"
        expected = "brown eyes, white pants"
        self.assertProcessedEqual(caption, expected)

    def test_keep_priority(self):
        caption  = "sitting, white pants, standing, blue eyes, lying"
        expected = "blue eyes, white pants, standing"
        self.assertProcessedEqual(caption, expected)

    def test_keep_last_combined(self):
        # MutuallyExclusiveFilter does not modify combined tags
        caption  = "black white pants"
        expected = "black white pants"
        self.assertProcessedEqual(caption, expected)



if __name__ == '__main__':
    unittest.main(verbosity=2)
