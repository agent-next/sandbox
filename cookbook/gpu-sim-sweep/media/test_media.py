"""Evidence and format checks, including negative controls that must fail."""

import ast
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image

import evidence
import manifest
import render

HERE = Path(__file__).resolve().parent


def reject_plotting(source, python=False):
    forbidden = "mat" + "plotlib"
    if python:
        for node in ast.walk(ast.parse(source)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert all(n.split(".")[0] != forbidden for n in names), "Forbidden plotting import"
    assert forbidden not in source.lower(), "Forbidden plotting dependency or reference"


class MediaTests(unittest.TestCase):
    def test_no_plotting_anywhere_in_demo(self):
        for path in evidence.DEMO.rglob("*"):
            if not path.is_file() or any(p.startswith(".") or p in
                                        ("work", "master", "__pycache__")
                                        for p in path.relative_to(evidence.DEMO).parts):
                continue
            if path.suffix in (".py", ".sh", ".json", ".md", ".txt", ".xml", ".log", ".lock"):
                reject_plotting(path.read_text(), path.suffix == ".py")
        forbidden = "mat" + "plotlib"
        for text, is_python in ((f"import {forbidden}", True),
                                (f"from {forbidden}.pyplot import figure", True),
                                (f"pip install {forbidden}==3.10.8", False)):
            with self.assertRaisesRegex(AssertionError, "Forbidden plotting"):
                reject_plotting(text, is_python)

    def test_native_renderer_not_drawn_geometry(self):
        source = (HERE / "render.py").read_text()
        self.assertIn("mujoco.Renderer(self.model, H, W)", source)
        self.assertIn("self.renderer.render()", source)
        self.assertIn("mjRND_SHADOW", source)
        self.assertNotIn("Poly3DCollection", source)
        self.assertIn("MUJOCO_GL=egl", (HERE / "make_media.sh").read_text())
        self.assertIn("MUJOCO_GL=osmesa", (HERE / "make_media.sh").read_text())

    def test_all_reference_states_and_recorded_gpu_samples(self):
        report = evidence.load_report()
        config, xml, expected, error = evidence.reference(report)
        stored = np.load(HERE / "data/cpu-qpos.npy", allow_pickle=False)
        np.testing.assert_array_equal(stored, expected)
        self.assertEqual(stored.shape, (801, 63))
        self.assertLessEqual(error, evidence.grade.PARITY_TOL)
        replay = render.Replay()
        try:
            for index in (0, 200, 400, 800):
                image = replay.frame(index)
                self.assertEqual(image.size, (1920, 1080))
            replay.states[400, 7] += .01
            with self.assertRaisesRegex(AssertionError, "rendered-state mismatch"):
                replay.frame(400)
        finally:
            replay.close()
        with self.assertRaisesRegex(AssertionError, "rendered-state mismatch"):
            evidence.assert_state([0.], [1e-8], "negative control")
        altered = copy.deepcopy(report)
        altered["good"]["world0_traj"]["traj"][50][7] += .2
        with self.assertRaisesRegex(AssertionError, "trajectory parity mismatch"):
            evidence.reference(altered)
        changed = stored.copy()
        changed[200, 2] += .01
        with mock.patch.object(render.np, "load", return_value=changed):
            with self.assertRaisesRegex(AssertionError, "rendered-state mismatch"):
                render.Replay()

    def test_visual_dressing_preserves_physics(self):
        report = evidence.load_report()
        _, xml, _, _ = evidence.reference(report)
        original = render.mujoco.MjModel.from_xml_string(xml)
        visual = render.visual_model(xml)
        render.assert_physics(original, visual)
        visual.geom_friction[0, 0] += .1
        with self.assertRaisesRegex(AssertionError, "physics geom_friction"):
            render.assert_physics(original, visual)

    def test_camera_orbit_changes_view_without_changing_pose(self):
        replay = render.Replay()
        try:
            first = np.asarray(replay.frame(200, azimuth=100))
            second = np.asarray(replay.frame(200, azimuth=130))
            self.assertGreater(np.mean(np.abs(first.astype(float) - second)), 5,
                               "Native 3D orbit must change the rendered view")
            np.testing.assert_array_equal(replay.data.qpos, replay.expected[200])
            replay.states[200, 7] += .01
            with self.assertRaisesRegex(AssertionError, "rendered-state mismatch"):
                replay.frame(200, azimuth=160)
        finally:
            replay.close()

    def test_tiles_advance_the_verified_reference_replay(self):
        replay = render.Replay()
        try:
            first = render.tiled_frame(replay, 0, 4, azimuth=115)
            second = render.tiled_frame(replay, 200, 4, azimuth=115)
            self.assertNotEqual(first.tobytes(), second.tobytes(),
                                "Tiles must animate the real arm and falling boxes")
            np.testing.assert_array_equal(replay.data.qpos, replay.expected[200])
            np.testing.assert_array_equal(np.asarray(second)[150:330, 320:640],
                                          np.asarray(second)[330:510, 640:960])
            np.testing.assert_array_equal(np.asarray(second)[:140], np.asarray(first)[:140])
            np.testing.assert_array_equal(np.asarray(second)[910:], np.asarray(first)[910:])
        finally:
            replay.close()

    def test_cookbook_video_gate(self):
        gate = HERE.parents[1] / "tools/video_gate.py"
        checked = subprocess.run([sys.executable, str(gate), str(HERE / "demo.mp4")],
                                 capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_report_cannot_hide_a_surviving_mutant(self):
        report = evidence.load_report()
        altered = copy.deepcopy(report)
        altered["mutants"]["low_capacity"]["failed"] = []
        with mock.patch.object(evidence.json, "loads", return_value=altered):
            with self.assertRaisesRegex(AssertionError, "Self-test incomplete"):
                evidence.load_report()
        history = json.loads((HERE / "data/loop.json").read_text())
        self.assertIn("not a chronological live agent trace", history["provenance"])
        self.assertEqual([r["report_key"] for r in history["iterations"]],
                         ["solver_iter_1", "low_capacity", "good"])

    def test_required_files_hashes_sizes_and_resolution(self):
        recorded = json.loads((HERE / "MANIFEST.json").read_text())
        manifest.validate_files(HERE, recorded)
        for name, size in (("result.png", (2400, 1950)), ("loop.png", (2400, 1600))):
            with Image.open(HERE / name) as image:
                self.assertEqual(image.size, size)
                self.assertAlmostEqual(image.info["dpi"][0], 200, places=1)
        with tempfile.TemporaryDirectory(dir=HERE / "work") as temp:
            with self.assertRaisesRegex(AssertionError, "Missing media file"):
                manifest.validate_files(Path(temp), recorded)
        altered = copy.deepcopy(recorded)
        altered["outputs"]["demo.mp4"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(AssertionError, "SHA mismatch"):
            manifest.validate_files(HERE, altered)

    def test_video_format_master_and_faststart(self):
        probe = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json",
            str(HERE / "demo.mp4")]))
        stream = probe["streams"][0]
        self.assertEqual((stream["codec_name"], stream["width"], stream["height"],
                          stream["r_frame_rate"], stream["pix_fmt"], int(stream["nb_frames"])),
                         ("h264", 1920, 1080, "30/1", "yuv420p", 780))
        self.assertEqual(float(probe["format"]["duration"]), 26)
        self.assertLess(int(probe["format"]["size"]), 8_000_000)
        self.assertIn(b"qp=0", (HERE / "master/demo.mp4").read_bytes()[:10000])
        raw = (HERE / "demo.mp4").read_bytes()
        self.assertLess(raw.index(b"moov"), raw.index(b"mdat"))

    def test_label_clipping_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, "Clipped label"):
            render.label(Image.new("RGB", (100, 100)), (90, 0), "must not clip", 32)


if __name__ == "__main__":
    unittest.main()
