"""Evidence and format checks, including negative controls that must fail."""

import ast
import copy
import hashlib
import inspect
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
        visual = render.visual_model(xml)
        visual.geom_size[1, 0] += .1
        with self.assertRaisesRegex(AssertionError, "physics geom_size"):
            render.assert_physics(original, visual)

    def test_camera_orbit_changes_view_without_changing_pose(self):
        replay = render.Replay()
        try:
            first = np.asarray(replay.frame(200, azimuth=100))
            second = np.asarray(replay.frame(200, azimuth=130))
            self.assertGreater(np.mean(np.abs(first.astype(float) - second)), 5,
                               "Native 3D orbit must change the rendered view")
            np.testing.assert_array_equal(replay.data.qpos, replay.expected[200])
            render.assert_physics(replay.original, replay.model)
            replay.states[200, 7] += .01
            with self.assertRaisesRegex(AssertionError, "rendered-state mismatch"):
                replay.frame(200, azimuth=160)
        finally:
            replay.close()

    def test_grid_instances_real_poses_in_one_perspective_scene(self):
        self.assertIn("side", inspect.signature(render.Replay.frame).parameters,
                      "Scale shot must render spatial instances, not a flat repeated tile")
        replay = render.Replay()
        try:
            replay.frame(200)
            original = replay.renderer.scene
            count = original.ngeom
            geoms = [i for i in range(count)
                     if original.geoms[i].type != render.mujoco.mjtGeom.mjGEOM_PLANE]
            positions = np.array([original.geoms[i].pos.copy() for i in geoms])
            first = replay.frame(0, side=4, azimuth=115)
            second = replay.frame(200, side=4, azimuth=115)
            self.assertNotEqual(first.tobytes(), second.tobytes(),
                                "Grid must animate the real arm and falling boxes")
            view = replay.renderer.scene
            self.assertEqual(view.ngeom, count + 15 * len(geoms))
            self.assertGreaterEqual(replay.renderer._mjr_context.shadowClip, 12,
                                    "Shadow coverage must include display instances")
            np.testing.assert_allclose(
                [view.geoms[i].pos for i in geoms], positions + [-2.775, -2.775, 0],
                atol=1e-6)
            for instance in range(1, 16):
                row, col = divmod(instance, 4)
                offset = np.array([col * 1.85 - 2.775, row * 1.85 - 2.775, 0])
                for j, i in enumerate(geoms):
                    dest = view.geoms[count + (instance - 1) * len(geoms) + j]
                    np.testing.assert_allclose(dest.pos, positions[j] + offset, atol=1e-6)
                    np.testing.assert_array_equal(dest.mat, view.geoms[i].mat)
            np.testing.assert_array_equal(replay.data.qpos, replay.expected[200])
            replay.states[200, 7] += .01
            with self.assertRaisesRegex(AssertionError, "rendered-state mismatch"):
                replay.frame(200, side=8)
        finally:
            replay.close()

    def test_comparison_uses_recorded_gpu_states_and_measured_bars(self):
        self.assertIn("gpu", inspect.signature(render.Replay.frame).parameters,
                      "Comparison must render the retained GPU trajectory")
        replay = render.Replay()
        try:
            recorded = np.asarray(replay.report["good"]["world0_traj"]["traj"])
            image = render.comparison(replay, 200, 1)
            self.assertEqual(image.size, (1920, 1080))
            np.testing.assert_array_equal(replay.data.qpos, recorded[50])
            pixels = np.asarray(image)
            np.testing.assert_array_equal(pixels[965, 80], [255, 193, 123])
            np.testing.assert_array_equal(pixels[965, 200], [43, 58, 77])
            np.testing.assert_array_equal(pixels[965, 1800], [101, 216, 236])
            replay.gpu_states[50, 7] += .01
            with self.assertRaisesRegex(AssertionError, "rendered-state mismatch"):
                render.comparison(replay, 200, 1)
        finally:
            replay.close()

    def test_plain_english_rejections_cover_every_real_mutant(self):
        self.assertTrue(hasattr(render, "BROKEN"),
                        "Proof must explain rejected configs in plain English")
        self.assertEqual({name for name, _ in render.BROKEN},
                         set(evidence.load_report()["mutants"]))
        for name, plain in render.BROKEN:
            self.assertNotIn("_", plain)
            self.assertNotEqual(name, plain)

    def test_sweep_is_the_early_hook_and_task_is_three_seconds(self):
        self.assertTrue(hasattr(render, "SHOT_CUTS"),
                        "World sweep must immediately follow the two-second result")
        self.assertEqual(render.SHOT_CUTS[:6], (2, 4, 6, 8, 10, 12))
        self.assertEqual(render.SHOT_CUTS[6], 15,
                         "Reach/drop/settle must take only three seconds")
        self.assertEqual(render.SWEEP_SIDES, (1, 2, 4, 8, 16))

    def test_visual_variants_are_real_seeded_cpu_physics_not_measurements(self):
        self.assertTrue(hasattr(render, "visual_replay"),
                        "Labelled visual worlds need real perturbed-start simulations")
        xml = (HERE / "data/model.xml").read_text().strip()
        states = render.visual_replay(xml, 800)
        self.assertEqual(states.shape, (256, 801, 63))
        self.assertFalse(states.flags.writeable)
        self.assertEqual(len(np.unique(states[:, 0], axis=0)), 256)
        model = render.mujoco.MjModel.from_xml_string(xml)
        self.assertLessEqual(np.abs(states[:, 0, :7] - model.qpos0[:7]).max(), .12)
        for box in range(8):
            start = 7 + 7 * box
            delta = states[:, 0, start:start + 3] - model.qpos0[start:start + 3]
            self.assertTrue((np.abs(delta) <= [.025, .025, .08]).all())
            np.testing.assert_allclose(
                np.linalg.norm(states[:, 0, start + 3:start + 7], axis=1), 1)
        data = render.mujoco.MjData(model)
        data.ctrl[:] = render.scene.ARM_TARGET
        data.qpos[:] = states[37, 0]
        for index in range(801):
            np.testing.assert_array_equal(data.qpos, states[37, index])
            if index < 800:
                render.mujoco.mj_step(model, data)
        # Recompute a small prefix with a fresh RNG, not merely a cache hit.
        prefix = render.visual_replay(xml, 800, count=2)
        np.testing.assert_array_equal(prefix, states[:2])
        metadata = json.loads((HERE / "data/visual-replay.json").read_text())
        self.assertFalse(metadata["measured"])
        self.assertEqual(metadata["on_screen_label"], "visual replay, perturbed starts")
        self.assertEqual(metadata["qpos_sha256"], hashlib.sha256(states.tobytes()).hexdigest())

    def test_perturbed_grid_renders_each_worlds_own_pose(self):
        self.assertIn("perturbed", inspect.signature(render.Replay.frame).parameters,
                      "Scale grid must render distinct simulated starts")
        replay = render.Replay()
        try:
            image = replay.frame(200, side=4, azimuth=115, perturbed=True)
            xml = (HERE / "data/model.xml").read_text().strip()
            states = render.visual_replay(xml, 800)
            view = replay.renderer.scene
            # All copies retain their source geom id. Remove only the display translation.
            originals = [i for i in range(replay.model.ngeom)
                         if replay.model.geom_type[i] != render.mujoco.mjtGeom.mjGEOM_PLANE]
            copies = [g for g in view.geoms[:view.ngeom]
                      if g.type != render.mujoco.mjtGeom.mjGEOM_PLANE]
            self.assertEqual(len(copies), 16 * len(originals))
            data = render.mujoco.MjData(replay.original)
            for world in range(16):
                data.qpos[:] = states[world, 200]
                render.mujoco.mj_forward(replay.original, data)
                row, col = divmod(world, 4)
                offset = np.array([col * 1.85 - 2.775, row * 1.85 - 2.775, 0])
                for geom in copies[world * len(originals):(world + 1) * len(originals)]:
                    np.testing.assert_allclose(geom.pos, data.geom_xpos[geom.objid] + offset,
                                               atol=1e-6)
                    np.testing.assert_allclose(geom.mat.ravel(), data.geom_xmat[geom.objid],
                                               atol=1e-6)
            self.assertLess((np.asarray(image).min(axis=2) > 245).mean(), .01,
                            "Scale floor must not blow out to white")
            with self.assertRaisesRegex(AssertionError, "not GPU recordings"):
                replay.frame(200, gpu=True, perturbed=True)
        finally:
            replay.close()

    def test_video_provenance_is_large_plain_and_proof_has_status_marks(self):
        replay = render.Replay()
        try:
            with mock.patch.object(render, "label", wraps=render.label) as labels:
                render.hud(Image.new("RGB", (1920, 1080)), "Title", "Detail",
                           "Result", "Source")
                render.comparison(replay, 200, 1)
                image = render.proof(replay, 200, 0, 1)
                render.proof(replay, 400, 1, 1)
            for call in labels.call_args_list:
                text, size = call.args[2:4]
                self.assertGreaterEqual(size, 60, f"Phone-unreadable video text: {text}")
                self.assertNotIn("_", text)
                self.assertNotIn("judge", text.lower())
            pixels = np.asarray(image)
            for row in range(4):
                np.testing.assert_array_equal(pixels[293 + row * 144, 87], [255, 133, 133])
            np.testing.assert_array_equal(pixels[969, 76], [166, 237, 176])
        finally:
            replay.close()

    def test_hud_animates_without_inventing_live_measurements(self):
        self.assertTrue(hasattr(render, "animate_hud"),
                        "Moving simulator frames must also have an animated HUD")
        first = Image.new("RGB", (1920, 1080))
        second = first.copy()
        render.animate_hud(first, .1)
        render.animate_hud(second, .8)
        self.assertNotEqual(first.tobytes(), second.tobytes())

    def test_primary_caption_cap_height_and_bright_scene_contrast(self):
        box = render.font(60, True).getbbox("H")
        self.assertGreaterEqual(box[3] - box[1], render.H * .04)
        image = render.hud(Image.new("RGB", (render.W, render.H), "white"),
                           "Primary caption", "Provenance", "Measured result", "Source")
        pixels = np.asarray(image)
        self.assertLess(pixels[915, 1800].mean(), 50,
                        "Footer needs a dark backing even over a white studio floor")
        self.assertLess(pixels[125, 1800].mean(), 50,
                        "Secondary caption needs contrast over a white scene")

    def test_cookbook_video_gate(self):
        gate = HERE.parents[1] / "tools/video_gate.py"
        checked = subprocess.run([sys.executable, str(gate), str(HERE / "demo.mp4")],
                                 capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertEqual(json.loads(checked.stdout),
                         json.loads((HERE / "video-gate.json").read_text()))

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
                         ("h264", 1920, 1080, "30/1", "yuv420p", 900))
        self.assertEqual(float(probe["format"]["duration"]), 30)
        self.assertLess(int(probe["format"]["size"]), 8_000_000)
        self.assertIn(b"qp=0", (HERE / "master/demo.mp4").read_bytes()[:10000])
        raw = (HERE / "demo.mp4").read_bytes()
        self.assertLess(raw.index(b"moov"), raw.index(b"mdat"))

    def test_label_clipping_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, "Clipped label"):
            render.label(Image.new("RGB", (100, 100)), (90, 0), "must not clip", 32)


if __name__ == "__main__":
    unittest.main()
