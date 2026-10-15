"""Run with media/.venv/bin/python -m unittest discover -s media after generation."""

import json
from pathlib import Path
import tempfile
import unittest

import matplotlib.pyplot as plt

from collect import read_selftest
import render

HERE = Path(__file__).resolve().parent


class EvidenceTests(unittest.TestCase):
    def test_retained_csvs_match_full_judge(self):
        render.grade.SPEC_DT = render.SPEC["timestep_s"]
        for name, scene in render.SCENES.items():
            rows = render.grade.parse_traj(HERE / "data" / scene["output"])
            self.assertEqual(render.grade.csv_shape(name, rows, scene), [])
            self.assertEqual(
                render.grade.analyze(name, rows, render.ORACLE[name], render.SPEC),
                render.METRIC[name])
        self.assertNotIn("mode", render.VERDICT["gates"]["run"])
        self.assertTrue(render.VERDICT["judge_intact"])

    def test_selftest_parser_rejects_missing_or_surviving_mutants(self):
        text = (HERE / "data/selftest.txt").read_text()
        mutants = read_selftest(HERE / "data/selftest.txt")
        self.assertEqual(len(mutants), 8)
        first = mutants[0][0]
        variants = [
            text.replace("known-good: PASS", "known-good: FAIL"),
            text.replace(f"mutant {first}: killed", f"mutant {first}: SURVIVED"),
            text.replace("8/8 = 100%", "7/8 = 88%"),
            text.replace("determinism: OK", "determinism: FAILED"),
        ]
        with tempfile.TemporaryDirectory(dir=HERE / "work") as temp:
            path = Path(temp) / "selftest.txt"
            for invalid in variants:
                path.write_text(invalid)
                with self.assertRaises(AssertionError):
                    read_selftest(path)

    def test_layout_guard_accepts_clear_text_and_rejects_overlap(self):
        fig = plt.figure(figsize=(6, 4))
        fig.text(.1, .6, "First label")
        moving = fig.text(.1, .3, "Second label")
        try:
            render.check_text(fig, "positive")
            moving.set_position((.1, .6))
            with self.assertRaisesRegex(AssertionError, "overlapping"):
                render.check_text(fig, "negative")
            moving.set_position((.99, .3))
            with self.assertRaisesRegex(AssertionError, "clipped"):
                render.check_text(fig, "negative")
        finally:
            plt.close(fig)

    def test_manifest_hashes_and_png_metadata(self):
        from PIL import Image
        import manifest

        recorded = json.loads((HERE / "MANIFEST.json").read_text())
        for entry in recorded["files"]:
            self.assertEqual(manifest.digest(HERE / entry["file"]), entry["sha256"])
        for name in ("result.png", "loop.png"):
            with Image.open(HERE / name) as image:
                self.assertEqual(image.width, 2400)
                self.assertAlmostEqual(image.info["dpi"][0], 200, places=1)
                self.assertNotIn("Software", image.info)
                self.assertNotIn("Creation Time", image.info)

    def test_layout_guard_ignores_ticks_outside_view(self):
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.set(xlim=(0, 1), ylim=(0, 1), xticks=[0, .5, 1, 100])
        ax.set_xlim(0, 1)
        try:
            render.check_text(fig, "undrawn tick")
        finally:
            plt.close(fig)


if __name__ == "__main__":
    unittest.main()
