"""Run via make_media.sh or the media/.tools judge interpreter after generation."""

import ast
import json
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image

from collect import read_selftest
import manifest
import render

HERE = Path(__file__).resolve().parent


def reject_plotting(source):
    """The banned module name is split so the repository contains no reference."""
    forbidden = "mat" + "plotlib"
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        assert all(n.split(".")[0] != forbidden for n in names), "Forbidden plotting import"
    assert forbidden not in source.lower(), "Forbidden plotting dependency"


class EvidenceTests(unittest.TestCase):
    def test_no_plotting_import_or_dependency(self):
        forbidden = "mat" + "plotlib"
        for path in render.DEMO.rglob("*"):
            if not path.is_file() or any(part.startswith(".") or part in
                                        ("work", "master", "__pycache__")
                                        for part in path.relative_to(render.DEMO).parts):
                continue
            if path.suffix in (".py", ".sh", ".txt", ".json", ".md"):
                if path.suffix == ".py":
                    reject_plotting(path.read_text())
                else:
                    self.assertNotIn(forbidden, path.read_text().lower(), str(path))
        for source in (f"import {forbidden}", f"from {forbidden}.pyplot import figure"):
            with self.assertRaisesRegex(AssertionError, "Forbidden plotting import"):
                reject_plotting(source)

    def test_retained_csvs_match_full_judge(self):
        render.grade.SPEC_DT = render.SPEC["timestep_s"]
        for name, scene in render.SCENES.items():
            rows = render.grade.parse_traj(HERE / "data" / scene["output"])
            self.assertEqual(render.grade.csv_shape(name, rows, scene), [])
            self.assertEqual(render.grade.analyze(
                name, rows, render.ORACLE[name], render.SPEC), render.METRIC[name])
        self.assertNotIn("mode", render.VERDICT["gates"]["run"])
        self.assertTrue(render.VERDICT["judge_intact"])

    def test_agreement_uses_each_incline_angle(self):
        for name in ("incline_stick", "incline_slide"):
            scene = render.SCENES[name]
            th = math.radians(scene["plane"]["tilt_deg"])
            # Exactly one metre down this scene's slope must project to one.
            artifact = {"x": [0, math.cos(th)], "z": [0, -math.sin(th)]}
            reference = {"x": [0, 0], "z": [0, 0]}
            dev = render.grade.agreement_metric(name, artifact, reference, scene)
            self.assertAlmostEqual(dev, 1, places=12,
                                   msg=f"{name}: agreement must use its own angle")
            # A normal-only offset must not register as downhill travel.
            normal = {"x": [0, math.sin(th)], "z": [0, math.cos(th)]}
            self.assertAlmostEqual(render.grade.agreement_metric(
                name, normal, reference, scene), 0, places=12)

    def test_csv_shape_reads_scene_timestep_s(self):
        scene = dict(render.SCENES["drop"], duration_s=1, timestep_s=.02)
        rows = {c: [i * .02 if c == "t" else 0.0 for i in range(51)]
                for c in scene["columns"]}
        with mock.patch.object(render.grade, "SPEC_DT", .001, create=True):
            self.assertEqual(render.grade.csv_shape("drop", rows, scene), [],
                             "scene timestep_s must override global timestep")
            rows = {c: [i * .001 if c == "t" else 0.0 for i in range(1001)]
                    for c in scene["columns"]}
            self.assertTrue(render.grade.csv_shape("drop", rows, scene),
                            "wrong row count at scene timestep_s must fail")

    def test_every_state_replayed_and_mismatch_rejected(self):
        for name in render.SCENES:
            replay = render.Replay(name)
            stored = np.load(HERE / "data" / f"state_{name}.npy", allow_pickle=False)
            np.testing.assert_array_equal(replay.states, stored)
            index = len(replay.states) // 2
            replay.frame(index)
            replay.states[index, 2 if name == "drop" else 0] += .01
            with self.assertRaisesRegex(AssertionError, "rendered-state mismatch"):
                replay.frame(index)
            replay.close()
        with self.assertRaisesRegex(AssertionError, "rendered-state mismatch"):
            render.assert_state([0.0], [1e-8], "negative control")

    def test_selftest_parser_rejects_missing_or_surviving_mutants(self):
        text = (HERE / "data/selftest.txt").read_text()
        mutants = read_selftest(HERE / "data/selftest.txt")
        self.assertEqual(len(mutants), 8)
        variants = [
            text.replace("known-good: PASS", "known-good: FAIL"),
            text.replace(f"mutant {mutants[0][0]}: killed", f"mutant {mutants[0][0]}: SURVIVED"),
            text.replace("8/8 = 100%", "7/8 = 88%"),
            text.replace("determinism: OK", "determinism: FAILED"),
        ]
        with tempfile.TemporaryDirectory(dir=HERE / "work") as temp:
            path = Path(temp) / "selftest.txt"
            for invalid in variants:
                path.write_text(invalid)
                with self.assertRaises(AssertionError):
                    read_selftest(path)

    def test_required_files_hashes_and_missing_file_rejection(self):
        recorded = json.loads((HERE / "MANIFEST.json").read_text())
        self.assertEqual({e["file"] for e in recorded["files"]},
                         {"demo.mp4", "result.png", "loop.png"})
        manifest.validate_files(HERE, recorded)
        for path, digest in recorded["source_sha256"].items():
            self.assertTrue((render.DEMO / path).is_file(), f"Missing source {path}")
            self.assertEqual(manifest.digest(render.DEMO / path), digest, path)
        with tempfile.TemporaryDirectory(dir=HERE / "work") as temp:
            with self.assertRaisesRegex(AssertionError, "Missing media file"):
                manifest.validate_files(Path(temp), recorded)
        for name in ("result.png", "loop.png"):
            with Image.open(HERE / name) as image:
                self.assertEqual(image.width, 2400)
                self.assertAlmostEqual(image.info["dpi"][0], 200, places=1)

    def test_video_format_and_lossless_master(self):
        probe = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json",
            str(HERE / "demo.mp4")]))
        stream = probe["streams"][0]
        self.assertEqual((stream["codec_name"], stream["width"], stream["height"],
                          stream["r_frame_rate"], stream["pix_fmt"]),
                         ("h264", 1920, 1080, "30/1", "yuv420p"))
        self.assertTrue(20 <= float(probe["format"]["duration"]) <= 60)
        self.assertLess(int(probe["format"]["size"]), 8_000_000)
        self.assertIn(b"qp=0", (HERE / "master/demo.mp4").read_bytes()[:10000])
        raw = (HERE / "demo.mp4").read_bytes()
        self.assertLess(raw.index(b"moov"), raw.index(b"mdat"))


if __name__ == "__main__":
    unittest.main()
