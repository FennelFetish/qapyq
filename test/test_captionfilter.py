import sys, os
sys.path.append( os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) )

import unittest, itertools
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
        seperator = ", "
        removeDup = True
        sortCaptions = True
        sortNonGroup = False
        whitelistGroups = False

        groups = [
            (["straight-on", "from side", "from behind", "standing", "sitting"], MutualExclusivity.Disabled, False),
            (["long pants", "black pants", "white pants", "denim pants", "pants"], MutualExclusivity.Disabled, True), # Combine enabled
            (["black tank top", "white tank top", "frilled tank top", "polka dot tank top"], MutualExclusivity.Disabled, True), # Combine enabled
            (["long hair", "dark hair", "blonde hair", "brown hair", "black hair", "hair ornament"], MutualExclusivity.Disabled, True) # Combine enabled
        ]

        bans = ["realistic", "blurry"]

        self.rulesProcessor = CaptionRulesProcessor(seperator, removeDup, sortCaptions, sortNonGroup, whitelistGroups)
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
        prefix = "pre1, pre2"
        suffix = "suf1, suf2"
        prefixSuffixSep = True
        seperator = ", "
        removeDup = True
        sortCaptions = True
        sortNonGroup = False
        whitelistGroups = False

        groups = [
            (["long pants", "black pants", "white pants", "denim pants", "pants"], MutualExclusivity.Disabled, True) # Combine enabled
        ]

        self.rulesProcessor = CaptionRulesProcessor(seperator, removeDup, sortCaptions, sortNonGroup, whitelistGroups)
        self.rulesProcessor.setPrefixSuffix(prefix, suffix, prefixSuffixSep, prefixSuffixSep)
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

    # TODO:
    # def test_partial_prefix_suffix(self):
    #     caption  = "denim pants, pre2, suf1, black pants"
    #     expected = "pre1, pre2, black denim pants, suf1, suf2"
    #     self.assertProcessedEqual(caption, expected)


    def test_single_add_prefix(self):
        self.rulesProcessor.setPrefixSuffix("add", "", False, False)
        self.assertProcessedEqual("", "add")
        self.assertProcessedEqual("add", "add")

    def test_single_add_suffix(self):
        self.rulesProcessor.setPrefixSuffix("", "add", False, False)
        self.assertProcessedEqual("", "add")
        self.assertProcessedEqual("add", "add")

    def test_single_add_both(self):
        self.rulesProcessor.setPrefixSuffix("add", "add", False, False)
        self.assertProcessedEqual("", "add")
        self.assertProcessedEqual("add", "add")

    def test_prefix_suffix_exist(self):
        self.rulesProcessor.setPrefixSuffix("pre", "suf", False, False)
        self.assertProcessedEqual("", "presuf")
        self.assertProcessedEqual("pre", "presuf")
        self.assertProcessedEqual("suf", "presuf")
        self.assertProcessedEqual("presuf", "presuf")
        self.assertProcessedEqual("pre, suf", "pre, suf")
        self.assertProcessedEqual("pre, mid, suf", "pre, mid, suf")


    def test_single_add_prefix_sep(self):
        self.rulesProcessor.setPrefixSuffix("add", "", True, True)
        self.assertProcessedEqual("", "add")
        self.assertProcessedEqual("add", "add")

    def test_single_add_suffix_sep(self):
        self.rulesProcessor.setPrefixSuffix("", "add", True, True)
        self.assertProcessedEqual("", "add")
        self.assertProcessedEqual("add", "add")

    def test_single_add_both_sep(self):
        self.rulesProcessor.setPrefixSuffix("add", "add", True, True)
        self.assertProcessedEqual("", "add")
        self.assertProcessedEqual("add", "add")

    def test_prefix_suffix_exist_sep(self):
        self.rulesProcessor.setPrefixSuffix("pre", "suf", True, True)
        self.assertProcessedEqual("", "pre, suf")
        self.assertProcessedEqual("pre", "pre, suf")
        self.assertProcessedEqual("suf", "pre, suf")
        self.assertProcessedEqual("pre, suf", "pre, suf")



class CaptionFilterMutualExclusivityTest(BaseCaptionFilterTest):
    def setUp(self):
        seperator = ", "
        removeDup = True
        sortCaptions = True
        sortNonGroup = False
        whitelistGroups = False

        groups = [
            (["blue eyes", "green eyes", "brown eyes"], MutualExclusivity.KeepFirst, False),
            (["black pants", "white pants", "blue pants"], MutualExclusivity.KeepLast, True), # Combine enabled
            (["lying", "sitting", "standing"], MutualExclusivity.Priority, False)
        ]

        self.rulesProcessor = CaptionRulesProcessor(seperator, removeDup, sortCaptions, sortNonGroup, whitelistGroups)
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



class CaptionFilterSortNonGroupTest(BaseCaptionFilterTest):
    def setUp(self):
        seperator = ", "
        removeDup = False
        sortCaptions = True
        sortNonGroup = True
        whitelistGroups = False

        groups = [
            (["GA0", "GA1", "GA2", "GA0 GA1"], MutualExclusivity.Disabled, False),
            (["GB0", "GB1", "GB2", "GB0 GB1"], MutualExclusivity.Disabled, False)
        ]

        self.rulesProcessor = CaptionRulesProcessor(seperator, removeDup, sortCaptions, sortNonGroup, whitelistGroups)
        self.rulesProcessor.setCaptionGroups(groups)

    def tearDown(self):
        del self.rulesProcessor


    def test_sort_all_permutations(self):
        caption  = "B, C,   A B, B C, C D"

        expectedA = "A, A B, B, B C, C, C D, D"
        expectedD = "D, C D, C, B C, B, A B, A"

        tags = [tag.strip() for tag in caption.split(",")]
        for perm in itertools.permutations(tags):
            joined = ", ".join(perm)
            self.assertProcessedEqual(f"A, {joined}, D", expectedA)
            self.assertProcessedEqual(f"D, {joined}, A", expectedD)

    def test_groups_first(self):
        caption  = "A, GA2, GA0 GA1, B, GA0, A B, GA1, B C, extra, C"
        expected = "GA0, GA1, GA2, GA0 GA1, A, A B, B, B C, C, extra"
        self.assertProcessedEqual(caption, expected)

    def test_stable(self):
        caption  = "5, 4, 6, 3, 7, GA0, 2, 8, 1, 9, 0, GB0"
        expected = "GA0, GB0, 5, 4, 6, 3, 7, 2, 8, 1, 9, 0"
        self.assertProcessedEqual(caption, expected)

    def test_rearrange(self):
        caption  = "B, B C, A, C, A B"
        expected = "A, A B, B, B C, C"
        self.assertProcessedEqual(caption, expected)

    def test_2components(self):
        caption  = "0, 1 2, extra, A, C, 0 1, A B, 2, B C"
        expected = "0, 0 1, 1 2, 2, extra, A, A B, B C, C"
        self.assertProcessedEqual(caption, expected)

    # TODO: This makes an interleaved pattern. Maybe break cycles in the graph?
    def test_ring(self):
        caption  = "B C, D E, A B, extra, C D, E A"
        expected = "A B, E A, B C, D E, C D, extra"
        self.assertProcessedEqual(caption, expected)

    # TODO: This fails because the order is reversed and 'C X D' / 'E X F' are swapped
    # def test_3word_star_stable(self):
    #     caption  = "A, C X D, extra, E X F, A X B"
    #     expected = "A, A X B, C X D, E X F, extra"
    #     self.assertProcessedEqual(caption, expected)

    def test_fork(self):
        caption  = "A B, C Y, X 0, C X, B C, Y 0"
        expected = "A B, B C, C X, C Y, Y 0, X 0"
        self.assertProcessedEqual(caption, expected)

    def test_edge_weight(self):
        caption  = "A B C, C D E,   C D, B C,   B C E, B D E,   A, C"
        expected = "A, A B C, B C, B C E, C, C D, C D E, B D E"
        self.assertProcessedEqual(caption, expected)

        caption  = "A B C, C D E,   C D, B C,   B D E, A B D,   A, E"
        expected = "A, A B C, A B D, B C, C D, B D E, C D E, E"
        self.assertProcessedEqual(caption, expected)

    def test_duplicates(self):
        caption  = "A, B, A, B, A"
        expected = "A, A, A, B, B"
        self.assertProcessedEqual(caption, expected)

    def test_duplicates2(self):
        caption  = "B C, A, B, A B, A, B, A"
        expected = "B C, B, B, A B, A, A, A"
        self.assertProcessedEqual(caption, expected)

    def test_empty(self):
        caption  = ""
        expected = ""
        self.assertProcessedEqual(caption, expected)



if __name__ == '__main__':
    unittest.main(verbosity=2)
