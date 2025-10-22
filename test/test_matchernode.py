import sys, os
sys.path.append( os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) )

import unittest
from caption.caption_highlight import MatcherNode


class MatcherNodeTest(unittest.TestCase):
    def setUp(self):
        self.values = {
            "long pants":           1,
            "black pants":          2,
            "denim pants":          3,
            "pants":                4,

            "long hair":            5,
            "blonde hair":          6,
            "black hair":           7,
            "hair ornament":        8,

            "red tank top":         9,
            "blue tank top":        10,
            "polka dot tank top":   11,
            "crop top":             12
        }

        self.node = MatcherNode[int]()
        for k, v in self.values.items():
            self.node.add(k, v)

    def tearDown(self):
        del self.node

    def assertMatchEqual(self, caption: str, expectedSplits: list[str], expectedMatches: dict[int, int]):
        words = caption.split(" ")

        splits = self.node.split(words)
        splits.reverse()
        self.assertListEqual(splits, expectedSplits)

        matches = self.node.match(words)

        try:
            self.assertDictEqual(matches, expectedMatches)
        except AssertionError:
            self.printMatches(words, expectedMatches, "Expected Matches")
            self.printMatches(words, matches, "Actual Matches")
            raise


    def printMatches(self, words: list[str], matches: dict, title: str):
        valToKey = lambda i: next(k for k, v in self.values.items() if v == i)

        print(f"{title}:")
        for k, v in sorted(matches.items()):
            val = valToKey(v)
            print(f"  {words[k]:12} => {val}")


    def testMatch1(self):
        caption = "long black denim pants"
        self.assertMatchEqual(caption, [
            "long pants",
            "black pants",
            "denim pants",
            "pants"
        ], {
            0: self.values["long pants"],
            1: self.values["black pants"],
            2: self.values["denim pants"],
            3: self.values["long pants"]
        })

    def testMatch2(self):
        caption = "black denim long pants"
        self.assertMatchEqual(caption, [
            "black pants",
            "denim pants",
            "long pants",
            "pants"
        ], {
            0: self.values["black pants"],
            1: self.values["denim pants"],
            2: self.values["long pants"],
            3: self.values["black pants"]
        })

    def testMatch3(self):
        caption = "black hair ornament"
        self.assertMatchEqual(caption, [
            "hair ornament"
        ], {
            1: self.values["hair ornament"],
            2: self.values["hair ornament"]
        })

    def testMatch4(self):
        caption = "very long blue hair"
        self.assertMatchEqual(caption, [
            "long hair"
        ], {
            1: self.values["long hair"],
            3: self.values["long hair"]
        })

    def testMatch5(self):
        caption = "red polka blue dot tank top"
        self.assertMatchEqual(caption, [
            "red tank top",
            "blue tank top"
        ], {
            0: self.values["red tank top"],
            2: self.values["blue tank top"],
            4: self.values["red tank top"],
            5: self.values["red tank top"],
        })


    # FIXME: Fails
    def testMatch6(self):
        caption = "red polka dot blue tank top"
        self.assertMatchEqual(caption, [
            "red tank top",
            "polka dot tank top",
            "blue tank top"
        ], {
            0: self.values["red tank top"],
            1: self.values["polka dot tank top"],
            2: self.values["polka dot tank top"],
            3: self.values["blue tank top"],
            4: self.values["red tank top"],
            5: self.values["red tank top"],
        })



if __name__ == '__main__':
    unittest.main(verbosity=2)
