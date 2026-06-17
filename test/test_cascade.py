import sys, os
sys.path.append( os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) )

import unittest, tempfile, random
from typing import Iterable
from lib.cascade import CascadeGraph, CascadeUpdate, CascadeNode, CycleError, CascadeGraphCache, CASCADE_FOLDER_FILE
from lib.captionfile import CaptionFile


def nodeKeys(nodes: Iterable[CascadeNode]) -> list[str]:
    return [n.key for n in nodes]

def printNodes(msg: str, nodes: Iterable[CascadeNode]):
    print(f"{msg}: " + ", ".join(nodeKeys(nodes)))


def shuffleDict(src: dict) -> dict:
    items = list(src.items())
    random.shuffle(items)
    return dict(items)

def createGraph(templates: dict[str, str]) -> CascadeGraph:
    return CascadeGraph(shuffleDict(templates))

def sortGraph(graph: CascadeGraph, startKey: str) -> dict[str, int]:
    startNode = graph.nodes[startKey]
    upstreamNodes, _ = CascadeUpdate()._collectUpstreamNodes(startNode, CaptionFile(""))
    upstreamNodes.add(startNode)

    graph.resetState()

    order = graph.topologicalSortMultiStart(upstreamNodes)
    return {n.key: i for i, n in enumerate(order)}



class CascadeTest(unittest.TestCase):
    def assertNodeKeys(self, nodes: Iterable[CascadeNode], *expectedKeys: str):
        actualKeys = set(n.key for n in nodes)
        self.assertSetEqual(actualKeys, set(expectedKeys))

    def assertUpstreamNodes(self, graph: CascadeGraph, captionFile: CaptionFile, changedNode: CascadeNode, *expectedKeys: str):
        upstreamNodes, _ = CascadeUpdate()._collectUpstreamNodes(changedNode, captionFile)
        self.assertNodeKeys(upstreamNodes, *expectedKeys)
        graph.resetState()

    def assertMissingNodes(self, graph: CascadeGraph, captionFile: CaptionFile, changedNode: CascadeNode, *expectedKeys: str):
        _, missingNodes = CascadeUpdate()._collectUpstreamNodes(changedNode, captionFile)
        self.assertNodeKeys(missingNodes, *expectedKeys)
        graph.resetState()

    def assertTextFile(self, imgPath: str, expectedText: str):
        txtPath = os.path.splitext(imgPath)[0] + ".txt"
        with open(txtPath, "rt") as file:
            actualText = file.read()
        self.assertEqual(actualText, expectedText)

    def assertCascadeUpdate(self, templates: dict[str, str], changedKey: str, changedValue: str, expectedTags: dict[str, str], expectedText: str):
        keyType, keyName = changedKey.split(".")

        with tempfile.TemporaryDirectory(prefix="qapyq_test_cascade_") as tempdir:
            imgPath = os.path.join(tempdir, "test.jpg")

            captionFile = CaptionFile(imgPath)
            captionFile.addTags(keyName, changedValue)

            update = CascadeUpdate()
            update._cache = CascadeGraphCache()
            update._cache.addEntry(tempdir, templates)

            print()
            update.saveCascade(imgPath, captionFile, keyType, keyName)

            self.assertDictEqual(captionFile.tags, expectedTags)
            self.assertTextFile(imgPath, expectedText)



    TEMPLATES_DIAMOND = {
        "tags.A":       "{{tags.0}}A",
        "tags.B":       "{{tags.0}}B",
        "tags.up":      "up",
        "text":         "{{tags.A}} {{tags.B}} {{tags.up}}",
    }

    def testRenderDiamond(self):
        expectedText = "tagA tagB up"
        expectedTags = {
            "0": "tag",
            "A": "tagA",
            "B": "tagB",
        }

        self.assertCascadeUpdate(self.TEMPLATES_DIAMOND, "tags.0", "tag", expectedTags, expectedText)

    def testGraphDiamond(self):
        graph = createGraph(self.TEMPLATES_DIAMOND)
        nodes = graph.nodes

        self.assertNodeKeys(nodes.values(), "tags.0", "tags.A", "tags.B", "tags.up", "text")

        self.assertNodeKeys(nodes["tags.0"].inNodes)
        self.assertNodeKeys(nodes["tags.0"].outNodes, "tags.A", "tags.B")

        self.assertNodeKeys(nodes["tags.A"].inNodes, "tags.0")
        self.assertNodeKeys(nodes["tags.A"].outNodes, "text")

        self.assertNodeKeys(nodes["tags.B"].inNodes, "tags.0")
        self.assertNodeKeys(nodes["tags.B"].outNodes, "text")

        self.assertNodeKeys(nodes["tags.up"].inNodes)
        self.assertNodeKeys(nodes["tags.up"].outNodes, "text")

        self.assertNodeKeys(nodes["text"].inNodes, "tags.A", "tags.B", "tags.up")
        self.assertNodeKeys(nodes["text"].outNodes)

        self.assertFalse(graph.getFirstCycle())

    def testSortDiamond(self):
        graph = createGraph(self.TEMPLATES_DIAMOND)
        index = sortGraph(graph, "tags.0")

        self.assertLess(index["tags.0"], index["tags.A"])
        self.assertLess(index["tags.0"], index["tags.B"])

        self.assertLess(index["tags.A"], index["text"])
        self.assertLess(index["tags.B"], index["text"])
        self.assertLess(index["tags.up"], index["text"])

    def testUpstreamDiamond(self):
        graph = createGraph(self.TEMPLATES_DIAMOND)
        self.assertUpstreamNodes(graph, CaptionFile(""), graph.nodes["tags.0"], "tags.up")



    TEMPLATES_CROSS = {
        "tags.A":       "{{tags.0}}A",
        "tags.B":       "{{tags.0}}B",
        "tags.Xup":     "Xup",
        "tags.Yup":     "Yup",
        "tags.X":       "{{tags.A}}+{{tags.B}}+{{tags.Xup}}",
        "tags.Y":       "{{tags.B}}-{{tags.A}}-{{tags.Yup}}",
        "tags.up":      "up",
        "text":         "{{tags.X}} {{tags.Y}} {{tags.up}}"
    }

    def testRenderCross(self):
        expectedText = "tagA+tagB+Xup tagB-tagA-Yup up"
        expectedTags = {
            "0": "tag",
            "A": "tagA",
            "B": "tagB",
            "X": "tagA+tagB+Xup",
            "Y": "tagB-tagA-Yup",
        }

        self.assertCascadeUpdate(self.TEMPLATES_CROSS, "tags.0", "tag", expectedTags, expectedText)

    def testGraphCross(self):
        graph = createGraph(self.TEMPLATES_CROSS)
        nodes = graph.nodes

        self.assertNodeKeys(nodes.values(), "tags.0", "tags.A", "tags.B", "tags.Xup", "tags.Yup", "tags.X", "tags.Y", "tags.up", "text")

        self.assertNodeKeys(nodes["tags.0"].inNodes)
        self.assertNodeKeys(nodes["tags.0"].outNodes, "tags.A", "tags.B")

        self.assertNodeKeys(nodes["tags.A"].inNodes, "tags.0")
        self.assertNodeKeys(nodes["tags.A"].outNodes, "tags.X", "tags.Y")

        self.assertNodeKeys(nodes["tags.B"].inNodes, "tags.0")
        self.assertNodeKeys(nodes["tags.B"].outNodes, "tags.X", "tags.Y")

        self.assertNodeKeys(nodes["tags.Xup"].inNodes)
        self.assertNodeKeys(nodes["tags.Xup"].outNodes, "tags.X")

        self.assertNodeKeys(nodes["tags.Yup"].inNodes)
        self.assertNodeKeys(nodes["tags.Yup"].outNodes, "tags.Y")

        self.assertNodeKeys(nodes["tags.X"].inNodes, "tags.A", "tags.B", "tags.Xup")
        self.assertNodeKeys(nodes["tags.X"].outNodes, "text")

        self.assertNodeKeys(nodes["tags.Y"].inNodes, "tags.A", "tags.B", "tags.Yup")
        self.assertNodeKeys(nodes["tags.Y"].outNodes, "text")

        self.assertNodeKeys(nodes["tags.up"].inNodes)
        self.assertNodeKeys(nodes["tags.up"].outNodes, "text")

        self.assertNodeKeys(nodes["text"].inNodes, "tags.X", "tags.Y", "tags.up")
        self.assertNodeKeys(nodes["text"].outNodes)

        self.assertFalse(graph.getFirstCycle())

    def testSortCross(self):
        graph = createGraph(self.TEMPLATES_CROSS)
        index = sortGraph(graph, "tags.0")

        self.assertLess(index["tags.0"], index["tags.A"])
        self.assertLess(index["tags.0"], index["tags.B"])

        self.assertLess(index["tags.A"], index["tags.X"])
        self.assertLess(index["tags.A"], index["tags.Y"])

        self.assertLess(index["tags.B"], index["tags.X"])
        self.assertLess(index["tags.B"], index["tags.Y"])

        self.assertLess(index["tags.Xup"], index["tags.X"])
        self.assertLess(index["tags.Yup"], index["tags.Y"])

        self.assertLess(index["tags.X"], index["text"])
        self.assertLess(index["tags.Y"], index["text"])
        self.assertLess(index["tags.up"], index["text"])

    def testUpstreamCross(self):
        graph = createGraph(self.TEMPLATES_CROSS)
        self.assertUpstreamNodes(graph, CaptionFile(""), graph.nodes["tags.0"], "tags.Xup", "tags.Yup", "tags.up")



    TEMPLATES_UPSTREAM_DIAMOND = {
        "tags.up4":     "up4",
        "tags.up3A":    "{{tags.up4}}A",
        "tags.up3B":    "{{tags.up4}}B",
        "tags.up2":     "{{tags.up3A}}-{{tags.up3B}}",
        "tags.up1":     "{{tags.up2}}",
        "text":         "{{tags.0}} {{tags.up1}}",
    }

    def testRenderUpstreamDiamond(self):
        expectedText = "tag up4A-up4B"
        expectedTags = {
            "0": "tag"
        }

        self.assertCascadeUpdate(self.TEMPLATES_UPSTREAM_DIAMOND, "tags.0", "tag", expectedTags, expectedText)

    def testGraphUpstreamDiamond(self):
        graph = createGraph(self.TEMPLATES_UPSTREAM_DIAMOND)
        nodes = graph.nodes

        self.assertNodeKeys(nodes.values(), "tags.0", "tags.up4", "tags.up3A", "tags.up3B", "tags.up2", "tags.up1", "text")

        self.assertNodeKeys(nodes["tags.0"].inNodes)
        self.assertNodeKeys(nodes["tags.0"].outNodes, "text")

        self.assertNodeKeys(nodes["tags.up4"].inNodes)
        self.assertNodeKeys(nodes["tags.up4"].outNodes, "tags.up3A", "tags.up3B")

        self.assertNodeKeys(nodes["tags.up3A"].inNodes, "tags.up4")
        self.assertNodeKeys(nodes["tags.up3A"].outNodes, "tags.up2")

        self.assertNodeKeys(nodes["tags.up3B"].inNodes, "tags.up4")
        self.assertNodeKeys(nodes["tags.up3B"].outNodes, "tags.up2")

        self.assertNodeKeys(nodes["tags.up2"].inNodes, "tags.up3A", "tags.up3B")
        self.assertNodeKeys(nodes["tags.up2"].outNodes, "tags.up1")

        self.assertNodeKeys(nodes["tags.up1"].inNodes, "tags.up2")
        self.assertNodeKeys(nodes["tags.up1"].outNodes, "text")

        self.assertNodeKeys(nodes["text"].inNodes, "tags.0", "tags.up1")
        self.assertNodeKeys(nodes["text"].outNodes)

        self.assertFalse(graph.getFirstCycle())

    def testSortUpstreamDiamond(self):
        graph = createGraph(self.TEMPLATES_UPSTREAM_DIAMOND)
        index = sortGraph(graph, "tags.0")

        self.assertLess(index["tags.0"], index["text"])

        self.assertLess(index["tags.up4"], index["tags.up3A"])
        self.assertLess(index["tags.up4"], index["tags.up3B"])

        self.assertLess(index["tags.up3A"], index["tags.up2"])
        self.assertLess(index["tags.up3B"], index["tags.up2"])

        self.assertLess(index["tags.up2"], index["tags.up1"])

        self.assertLess(index["tags.up1"], index["text"])

    def testUpstreamUpstreamDiamond(self):
        graph = createGraph(self.TEMPLATES_UPSTREAM_DIAMOND)

        captionFile = CaptionFile("")

        # Test with all values missing
        self.assertUpstreamNodes(graph, captionFile, graph.nodes["tags.0"], "tags.up1", "tags.up2", "tags.up3A", "tags.up3B", "tags.up4")

        # Test with some values present - these block upstream resolution
        captionFile.tags = {
            "up3A": "up3A"
        }
        self.assertUpstreamNodes(graph, captionFile, graph.nodes["tags.0"], "tags.up1", "tags.up2", "tags.up3B", "tags.up4")

        captionFile.tags = {
            "up3B": "up3B"
        }
        self.assertUpstreamNodes(graph, captionFile, graph.nodes["tags.0"], "tags.up1", "tags.up2", "tags.up3A", "tags.up4")

        captionFile.tags = {
            "up3B": "up3B",
            "up4": "up4"
        }
        self.assertUpstreamNodes(graph, captionFile, graph.nodes["tags.0"], "tags.up1", "tags.up2", "tags.up3A")

        captionFile.tags = {
            "up3A": "up3A",
            "up3B": "up3B"
        }
        self.assertUpstreamNodes(graph, captionFile, graph.nodes["tags.0"], "tags.up1", "tags.up2")

        captionFile.tags = {
            "up2": "up2"
        }
        self.assertUpstreamNodes(graph, captionFile, graph.nodes["tags.0"], "tags.up1")

        captionFile.tags = {
            "up3A": "up3A",
            "up3B": "up3B",
            "up2": "up2",
        }
        self.assertUpstreamNodes(graph, captionFile, graph.nodes["tags.0"], "tags.up1")

        captionFile.tags = {
            "up1": "up1"
        }
        self.assertUpstreamNodes(graph, captionFile, graph.nodes["tags.0"])  # No upstream nodes



    TEMPLATES_CYCLE = {
        "tags.A":       "{{tags.0}} {{tags.B}}",
        "tags.B":       "{{tags.0}} {{tags.A}}",
    }

    def testRenderCycle(self):
        expectedText = "should not exist"
        expectedTags = {
            "0": "tag"
        }

        try:
            self.assertCascadeUpdate(self.TEMPLATES_CYCLE, "tags.0", "tag", expectedTags, expectedText)
            self.fail("Text file written even though cycle exists")
        except FileNotFoundError:
            pass

    def testGraphCycle(self):
        graph = createGraph(self.TEMPLATES_CYCLE)
        nodes = graph.nodes

        self.assertNodeKeys(nodes.values(), "tags.0", "tags.A", "tags.B")

        self.assertNodeKeys(nodes["tags.0"].inNodes)
        self.assertNodeKeys(nodes["tags.0"].outNodes, "tags.A", "tags.B")

        self.assertNodeKeys(nodes["tags.A"].inNodes, "tags.0", "tags.B")
        self.assertNodeKeys(nodes["tags.A"].outNodes, "tags.B")

        self.assertNodeKeys(nodes["tags.B"].inNodes, "tags.0", "tags.A")
        self.assertNodeKeys(nodes["tags.B"].outNodes, "tags.A")

        self.assertTrue(graph.getFirstCycle())

    def testSortCycle(self):
        graph = createGraph(self.TEMPLATES_CYCLE)

        try:
            sortGraph(graph, "tags.0")
            self.fail("No CycleError raised")
        except CycleError as ex:
            self.assertNodeKeys(ex.path, "tags.0", "tags.A", "tags.B")

    def testUpstreamCycle(self):
        graph = createGraph(self.TEMPLATES_CYCLE)
        self.assertUpstreamNodes(graph, CaptionFile(""), graph.nodes["tags.0"])  # No upstream nodes



    TEMPLATES_FUNC = {
        "tags.up":      "up1, up2, up3",
        "tags.A":       "{{tags.0#join:tags.up#reverse#join:tags.miss}}",
        "tags.B":       "{{tags.up#upper#replacevar:UP:tags.0}}",
        "text":         "{{tags.A#join:tags.B#reverse#join:tags.0#join:tags.up}}"
    }

    def testRenderFunc(self):
        expectedText = "tag3, tag2, tag1, tag, up1, up2, up3, tag, up1, up2, up3"
        expectedTags = {
            "0": "tag",
            "A": "up3, up2, up1, tag",
            "B": "tag1, tag2, tag3",
        }

        self.assertCascadeUpdate(self.TEMPLATES_FUNC, "tags.0", "tag", expectedTags, expectedText)

    def testGraphFunc(self):
        graph = createGraph(self.TEMPLATES_FUNC)
        nodes = graph.nodes

        self.assertNodeKeys(nodes.values(), "tags.0", "tags.up", "tags.A", "tags.B", "tags.miss", "text")

        self.assertNodeKeys(nodes["tags.0"].inNodes)
        self.assertNodeKeys(nodes["tags.0"].outNodes, "tags.A", "tags.B", "text")

        self.assertNodeKeys(nodes["tags.up"].inNodes)
        self.assertNodeKeys(nodes["tags.up"].outNodes, "tags.A", "tags.B", "text")

        self.assertNodeKeys(nodes["tags.A"].inNodes, "tags.up", "tags.0", "tags.miss")
        self.assertNodeKeys(nodes["tags.A"].outNodes, "text")

        self.assertNodeKeys(nodes["tags.B"].inNodes, "tags.up", "tags.0")
        self.assertNodeKeys(nodes["tags.B"].outNodes, "text")

        self.assertNodeKeys(nodes["tags.miss"].inNodes)
        self.assertNodeKeys(nodes["tags.miss"].outNodes, "tags.A")

        self.assertNodeKeys(nodes["text"].inNodes, "tags.A", "tags.B", "tags.0", "tags.up")
        self.assertNodeKeys(nodes["text"].outNodes)

        self.assertFalse(graph.getFirstCycle())

    def testSortFunc(self):
        graph = createGraph(self.TEMPLATES_FUNC)
        index = sortGraph(graph, "tags.0")

        self.assertLess(index["tags.0"], index["tags.A"])
        self.assertLess(index["tags.0"], index["tags.B"])
        self.assertLess(index["tags.0"], index["text"])

        self.assertLess(index["tags.up"], index["tags.A"])
        self.assertLess(index["tags.up"], index["tags.B"])
        self.assertLess(index["tags.up"], index["text"])

        self.assertLess(index["tags.A"], index["text"])
        self.assertLess(index["tags.B"], index["text"])

        self.assertIsNone(index.get("tags.miss"))

    def testUpstreamFunc(self):
        graph = createGraph(self.TEMPLATES_FUNC)
        self.assertUpstreamNodes(graph, CaptionFile(""), graph.nodes["tags.0"], "tags.up")
        self.assertMissingNodes(graph, CaptionFile(""), graph.nodes["tags.0"], "tags.miss")



    TEMPLATES_SUBEXPR = {
        "tags.up":      "up",
        "tags.A":       "{{static:abc#append:[tags.0]#append:[static:def]}}",
        "tags.B":       "{{static:[tags.up#upper]#join:tags.0}}",
        "text":         "{{tags.A#append:[tags.B#lower]#append:[tags.miss#shuffle]}}"
    }

    def testRenderSubexpr(self):
        expectedText = "abc, tag, def, up, tag"
        expectedTags = {
            "0": "tag",
            "A": "abc, tag, def",
            "B": "UP, tag"
        }

        self.assertCascadeUpdate(self.TEMPLATES_SUBEXPR, "tags.0", "tag", expectedTags, expectedText)

    def testGraphSubexpr(self):
        graph = createGraph(self.TEMPLATES_SUBEXPR)
        nodes = graph.nodes

        self.assertNodeKeys(nodes.values(), "tags.0", "tags.up", "tags.A", "tags.B", "tags.miss", "text")

        self.assertNodeKeys(nodes["tags.0"].inNodes)
        self.assertNodeKeys(nodes["tags.0"].outNodes, "tags.A", "tags.B")

        self.assertNodeKeys(nodes["tags.up"].inNodes)
        self.assertNodeKeys(nodes["tags.up"].outNodes, "tags.B")

        self.assertNodeKeys(nodes["tags.A"].inNodes, "tags.0")
        self.assertNodeKeys(nodes["tags.A"].outNodes, "text")

        self.assertNodeKeys(nodes["tags.B"].inNodes, "tags.0", "tags.up")
        self.assertNodeKeys(nodes["tags.B"].outNodes, "text")

        self.assertNodeKeys(nodes["tags.miss"].inNodes)
        self.assertNodeKeys(nodes["tags.miss"].outNodes, "text")

        self.assertNodeKeys(nodes["text"].inNodes, "tags.A", "tags.B", "tags.miss")
        self.assertNodeKeys(nodes["text"].outNodes)

    def testSortSubexpr(self):
        graph = createGraph(self.TEMPLATES_SUBEXPR)
        index = sortGraph(graph, "tags.0")

        self.assertLess(index["tags.0"], index["tags.A"])
        self.assertLess(index["tags.0"], index["tags.B"])

        self.assertLess(index["tags.up"], index["tags.B"])

        self.assertLess(index["tags.A"], index["text"])
        self.assertLess(index["tags.B"], index["text"])

        self.assertIsNone(index.get("tags.miss"))

    def testUpstreamSubexpr(self):
        graph = createGraph(self.TEMPLATES_SUBEXPR)
        self.assertUpstreamNodes(graph, CaptionFile(""), graph.nodes["tags.0"], "tags.up")
        self.assertMissingNodes(graph, CaptionFile(""), graph.nodes["tags.0"], "tags.miss")



    TEMPLATES_FOLDER_1 = {
        "tags.A":       "{{tags.0#upper}}-1",
        "tags.name":    "default-name",
        "text":         "{{tags.name}} {{tags.A}} {{tags.B}}",
    }

    TEMPLATES_FOLDER_2 = {
        "tags.B":       "{{tags.1#upper}}-2",
        "tags.C":       "{{tags.2#upper}}-2",
    }

    TEMPLATES_FOLDER_3 = {
        "tags.A":       "{{tags.0#upper}}-3",
        "tags.B":       "{{tags.1#upper}}-3",
        "text":         "{{tags.name}} {{tags.A}} {{tags.B}} {{tags.C}}",
    }

    def testCacheAccumulate(self):
        with tempfile.TemporaryDirectory(prefix="qapyq_test_cascade_") as tempdir:
            os.makedirs(os.path.join(tempdir, "1", "2", "3"))

            # Write folder templates
            captionFile = CaptionFile(os.path.join(tempdir, "1", CASCADE_FOLDER_FILE))
            captionFile.cascade = shuffleDict(self.TEMPLATES_FOLDER_1)
            captionFile.saveToJson()

            captionFile = CaptionFile(os.path.join(tempdir, "1", "2", CASCADE_FOLDER_FILE))
            captionFile.cascade = shuffleDict(self.TEMPLATES_FOLDER_2)
            captionFile.saveToJson()

            captionFile = CaptionFile(os.path.join(tempdir, "1", "2", "3", CASCADE_FOLDER_FILE))
            captionFile.cascade = shuffleDict(self.TEMPLATES_FOLDER_3)
            captionFile.saveToJson()

            del captionFile

            update = CascadeUpdate()
            self.assertIsNone(update._cache)
            update.enableCache()
            assert update._cache is not None
            print()

            def assertFileText(path: str, expectedText: str, extraTags: dict = {}, extraTemplates: dict = {}) -> CaptionFile:
                captionFile = CaptionFile(path)
                captionFile.cascade.update(extraTemplates)
                if extraTemplates:
                    captionFile.saveToJson()

                captionFile.addTags("0", "tag0") # Only cascade this 'tags.0' key
                captionFile.addTags("1", "tag1")
                captionFile.addTags("2", "tag2")
                captionFile.tags.update(extraTags)
                update.saveCascade(path, captionFile, "tags", "0")
                self.assertTextFile(path, expectedText)
                return captionFile

            # 1 file in top folder
            file0 = os.path.join(tempdir, "file_0.json")
            try:
                assertFileText(file0, "should not exist")  # No templates defined -> No text file written
                self.fail("File should not exist")
            except FileNotFoundError:
                pass

            expectedCache = update._cache.templateCache.copy()  # Add folders above 'tempdir' if there are any.
            expectedCache.update({                              # Only set expectations for '/tmp', '/tmp/tempdir' and below.
                os.path.dirname(tempdir): {},
                tempdir: {}
            })
            self.assertDictEqual(update._cache.templateCache, expectedCache)

            # 1 file in folder-1
            file1 = os.path.join(tempdir, "1", "file_1.json")
            assertFileText(file1, "default-name TAG0-1")

            expectedCache[os.path.dirname(file1)] = self.TEMPLATES_FOLDER_1.copy()
            self.assertDictEqual(update._cache.templateCache, expectedCache)

            # 1 file in folder-2
            file2 = os.path.join(tempdir, "1", "2", "file_2.json")
            assertFileText(file2, "default-name TAG0-1 TAG1-2")

            expectedCache[os.path.dirname(file2)] = {
                "tags.A":       "{{tags.0#upper}}-1",
                "tags.B":       "{{tags.1#upper}}-2",
                "tags.C":       "{{tags.2#upper}}-2",
                "tags.name":    "default-name",
                "text":         "{{tags.name}} {{tags.A}} {{tags.B}}",
            }
            self.assertDictEqual(update._cache.templateCache, expectedCache)

            # 4 files in folder-3
            file3_1 = os.path.join(tempdir, "1", "2", "3", "file_3_1.json")
            assertFileText(file3_1, "default-name TAG0-3 TAG1-3 TAG2-2")

            file3_2 = os.path.join(tempdir, "1", "2", "3", "file_3_2.json")
            assertFileText(file3_2, "special-name TAG0-3 TAG1-3 TAG2-2", extraTags={
                "name": "special-name"
            })

            file3_3 = os.path.join(tempdir, "1", "2", "3", "file_3_3.json")
            assertFileText(file3_3, "template-name TAG0-file TAG1-3 TAG2-2", extraTemplates={
                "tags.name": "template-name",
                "tags.A":    "{{tags.0#upper}}-file"
            })

            update.enableCache()  # Reset cache - reload whole hierarchy
            self.assertDictEqual(update._cache.templateCache, {})

            file3_4 = os.path.join(tempdir, "1", "2", "3", "file_3_4.json")
            captionFile = assertFileText(file3_4, "special-name-2 TAG0-FILE TAG1-3 TAG2-2",
                extraTags={
                    "name": "special-name-2"
                },
                extraTemplates={
                    "tags.name": "unused",
                    "tags.A":    "{{tags.0#upper}}-FILE"
                }
            )

            self.assertDictEqual(captionFile.tags, {
                "0":    "tag0",
                "1":    "tag1",
                "2":    "tag2",
                "name": "special-name-2",
                "A":    "TAG0-FILE",
                # "B": "TAG1-3",  # Not cascaded
                # "C": "TAG2-2",  # Not cascaded
            })

            graph = update._cache.getGraph(file3_4)
            self.assertUpstreamNodes(graph, captionFile, graph.nodes["tags.0"], "tags.B", "tags.C")

            expectedCache[os.path.dirname(file3_1)] = {
                "tags.A":       "{{tags.0#upper}}-3",
                "tags.B":       "{{tags.1#upper}}-3",
                "tags.C":       "{{tags.2#upper}}-2",
                "tags.name":    "default-name",
                "text":         "{{tags.name}} {{tags.A}} {{tags.B}} {{tags.C}}",
            }
            self.assertDictEqual(update._cache.templateCache, expectedCache)



if __name__ == '__main__':
    unittest.main(verbosity=2)
