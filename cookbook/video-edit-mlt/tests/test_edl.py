import json
from pathlib import Path
import sys
import unittest

DEMO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEMO / "judge"))
import edl
import gen_sources


class Barcode(unittest.TestCase):
    def test_every_source_index(self):
        for cid in range(3):
            for frame in range(150):
                band = edl.band_row(edl.encode_code(cid, frame))*40
                self.assertEqual(edl.decode_band(band), (cid, frame))

    def test_ambiguous_band_is_not_guessed(self):
        self.assertIsNone(edl.decode_band(bytes([127])*1280*40*3))

    def test_bad_sync_is_rejected(self):
        bits = edl.encode_code(1, 42)
        bits[0] = 0
        self.assertIsNone(edl.decode_band(edl.band_row(bits)*40))

    def test_short_band_rejected(self):
        with self.assertRaises(ValueError):
            edl.decode_band(b"")

    def test_source_frame_size(self):
        self.assertEqual(len(gen_sources.frame_bytes(0, 0, [200, 40, 40])), 1280*720*3)


class Blend(unittest.TestCase):
    def test_estimator(self):
        a, b = (200, 40, 40), (40, 170, 60)
        for w in (0, .1, .5, .9, 1):
            rgb = [(1-w)*x+w*y for x, y in zip(a, b)]
            self.assertAlmostEqual(edl.blend_weight(rgb, a, b), w)

    def test_ramp_passes(self):
        self.assertEqual(edl.check_dissolve([i/24 for i in range(25)]), [])

    def test_hard_cut_and_short_ramp_fail(self):
        self.assertTrue(edl.check_dissolve([0]*12+[1]*13))
        self.assertTrue(edl.check_dissolve([min(1, i/11) for i in range(25)]))
        self.assertTrue(edl.check_dissolve([]))


class Edl(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((DEMO / "spec.json").read_text())
        self.expect = edl.expected_frames(self.spec)
        self.refs = {s["clip_id"]: s["rgb"] for s in self.spec["sources"].values()}
        self.decoded = [(x[1], x[2]) if x[0] == "cut" else None for x in self.expect]
        self.colours = [self.refs[x[1]] if x[0] == "cut" else (0, 0, 0) for x in self.expect]

    def compare(self):
        return edl.compare_edl(self.decoded, self.colours, self.expect, self.refs)

    def test_correct(self):
        self.assertEqual(len(self.expect), 225)
        self.assertEqual(self.compare(), [])

    def test_off_by_one_cut_cannot_be_ignored(self):
        self.decoded[200] = (1, 100)
        self.colours[200] = self.refs[1]
        self.assertEqual(len(self.compare()), 1)
        self.assertIn("frame 200", self.compare()[0])

    def test_wrong_in_point(self):
        self.decoded[224] = (2, 75)
        self.assertTrue(self.compare())

    def test_missing_frame(self):
        self.decoded.pop()
        self.assertTrue(self.compare())

    def test_unexpected_blend_outside_window(self):
        self.colours[20] = [120, 105, 50]
        self.assertTrue(self.compare())
