from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

DEMO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEMO / "judge"))
from mutants import mutate, node, INTENDED
from security import validate


class Mutants(unittest.TestCase):
    def root(self):
        return ET.parse(DEMO / "examples/good/edit.mlt").getroot()

    def test_hard_cut_removes_the_actual_compositor(self):
        root = self.root()
        before = ET.tostring(node(root, "video_track"))
        mutate(root, "hard_cut")
        self.assertFalse(any(n.get("id") == "xfade_luma" for n in root.iter()),
                         "changing luma start/end does not disable MLT's dissolve")
        self.assertEqual(ET.tostring(node(root, "video_track")), before)

    def test_all_mutants_remain_safe_xml_and_change_something(self):
        for name in INTENDED:
            root = self.root()
            before = ET.tostring(root)
            mutate(root, name)
            after = ET.tostring(root)
            with self.subTest(name=name):
                self.assertNotEqual(before, after)
                validate(after)
