"""Committed media must be backed by the actual graded scene and real renders."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from PIL import Image

HERE = Path(__file__).resolve().parent
MEDIA = HERE / "media"

spec = importlib.util.spec_from_file_location("studio_compose", MEDIA / "compose.py")
compose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compose)
capture_spec = importlib.util.spec_from_file_location("studio_media_capture", MEDIA / "capture.py")
capture = importlib.util.module_from_spec(capture_spec)
capture_spec.loader.exec_module(capture)


class MediaTests(unittest.TestCase):
    def test_render_reattaches_without_relaunching(self):
        replies = ["", RuntimeError("gateway is restarting"),
                   RuntimeError("sbx exec timed out"),
                   json.dumps({"done": True, "code": 0, "log": "MEDIA_DONE"})]
        with patch.object(capture.runner, "sbx", side_effect=replies) as remote, \
                patch.object(capture.time, "sleep"):
            capture.render_step("sandbox-test", "render-command")
        self.assertEqual(remote.call_count, 4)
        self.assertEqual(sum("nohup" in call.args[-1] for call in remote.call_args_list), 1)

    def test_render_probe_recovery_is_bounded(self):
        replies = [""] + [RuntimeError("gateway is restarting") for _ in range(4)]
        with patch.object(capture.runner, "sbx", side_effect=replies) as remote, \
                patch.object(capture.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "gateway is restarting"):
                capture.render_step("sandbox-test", "render-command")
        self.assertEqual(remote.call_count, 5)

    def test_render_does_not_retry_permanent_errors_or_launch(self):
        for replies in ([RuntimeError("gateway is restarting")],
                        ["", RuntimeError("sandbox not found")]):
            with self.subTest(replies=len(replies)), \
                    patch.object(capture.runner, "sbx", side_effect=replies) as remote, \
                    patch.object(capture.time, "sleep") as sleep:
                with self.assertRaises(RuntimeError):
                    capture.render_step("sandbox-test", "render-command")
                self.assertEqual(remote.call_count, len(replies))
                sleep.assert_not_called()

    def test_hashes_and_scene_provenance(self):
        manifest = json.loads((MEDIA / "MANIFEST.json").read_text())
        self.assertEqual({row["file"] for row in manifest["files"]},
                         {"result.png", "loop.png", "demo.mp4"})
        for row in manifest["files"]:
            path = MEDIA / row["file"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])
        for name, digest in manifest["source_sha256"].items():
            self.assertEqual(hashlib.sha256((HERE / name).read_bytes()).hexdigest(), digest)
        self.assertEqual(manifest["render"]["resolution"], [1920, 1080])
        poses = manifest["render_frames"][:-1]
        self.assertEqual(len(poses), 48)
        self.assertEqual([r["frame"] for r in poses], [1 + i / 4 for i in range(48)])
        self.assertEqual([r["pose"] for r in poses], list(range(1, 49)))
        self.assertEqual([r["file"] for r in poses],
                         [f"frame-{i:02}.png" for i in range(1, 49)])
        for i, row in enumerate(poses):
            self.assertAlmostEqual(row["angle_radians"], 2 * math.pi * i / 48, places=5)
        self.assertEqual(manifest["render_frames"][-1]["file"], "unlinked.png")
        self.assertEqual(manifest["turntable"]["judge_frames"], 12)
        self.assertEqual(manifest["turntable"]["poses_per_second"], 24)
        self.assertTrue(all(r["seconds"] > 0 for r in manifest["render_frames"]))
        transfers = {Path(r["name"]).name: r for r in json.loads(
            (MEDIA / "data/transfers.json").read_text())
            if r["name"].startswith("media/source/")}
        required = {row["file"] for row in manifest["render_frames"]}
        self.assertTrue(required <= set(transfers),
                        f"missing frame transfers: {sorted(required - set(transfers))}")
        for row in manifest["render_frames"]:
            self.assertEqual(row["sha256"], transfers[row["file"]]["sha256"])

    def test_phone_caption_cap_height_and_bounds(self):
        face = compose.font(64)
        _, top, _, bottom = face.getbbox("H")
        self.assertGreaterEqual(bottom - top, 0.04 * 1080)
        image = Image.new("RGB", (1920, 1080))
        draw = compose.ImageDraw.Draw(image)
        compose.text(draw, (20, 20), "PASS")
        with self.assertRaisesRegex(ValueError, "caption outside frame"):
            compose.text(draw, (1800, 20), "THIS CAPTION MUST NOT BE CLIPPED")

    def test_real_pose_playback_cadence(self):
        indices = [compose.pose_index(i) for i in range(180)]
        self.assertEqual(len(set(indices[:60])), 48)
        self.assertEqual(indices[:60], indices[60:120])
        self.assertEqual(indices[:60], indices[120:])
        self.assertTrue(all((b-a) % 48 in (0, 1)
                            for a, b in zip(indices, indices[1:])))

    def test_phone_proof_pages_cover_every_measured_case(self):
        data = json.loads((MEDIA / "data/selftest.json").read_text())
        self.assertEqual(set(compose.FAILURE_LABELS), set(data["mutants"]))
        for start in (0, 5):
            self.assertEqual(compose.kill_matrix(data, start).size, (1920, 1080))
        for size in (76, 96):
            _, top, _, bottom = compose.font(size).getbbox("H")
            self.assertGreaterEqual(bottom - top, 0.05 * 1080)

    def test_measured_proof(self):
        data = json.loads((MEDIA / "data/selftest.json").read_text())
        self.assertTrue(data["pass"])
        self.assertTrue(data["deterministic"])
        self.assertEqual(data["killed"], data["total"])
        spec = importlib.util.spec_from_file_location(
            "studio_media_mutants", HERE / "judge/mutants.py")
        mutants = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mutants)
        self.assertEqual(set(data["mutants"]), set(mutants.MUTANTS))
        self.assertEqual(data["total"], len(mutants.MUTANTS))
        self.assertEqual(len(data["good"]["gates"]), 5)
        for verdict in data["mutants"].values():
            self.assertFalse(verdict["pass"])
            self.assertNotIn("error", verdict)
            self.assertTrue(verdict["judge_unchanged"])
            self.assertTrue(any(not g["pass"] for g in verdict["gates"].values()))

    def test_figures_resolution_and_dpi(self):
        for name in ("result.png", "loop.png"):
            with Image.open(MEDIA / name) as image:
                self.assertEqual(image.size, (1920, 1080))
                self.assertAlmostEqual(image.info["dpi"][0], 200, places=1)

    def test_video_is_exact_master_format(self):
        probe = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_format", "-show_streams",
            "-of", "json", str(MEDIA / "demo.mp4")]))
        video = next(row for row in probe["streams"] if row["codec_type"] == "video")
        self.assertEqual((video["width"], video["height"]), (1920, 1080))
        self.assertEqual(video["r_frame_rate"], "30/1")
        self.assertEqual(video["codec_name"], "h264")
        self.assertEqual(video["pix_fmt"], "yuv420p")
        self.assertEqual(float(probe["format"]["duration"]), 32)
        self.assertLessEqual((MEDIA / "demo.mp4").stat().st_size, 8_000_000)


if __name__ == "__main__":
    unittest.main()
