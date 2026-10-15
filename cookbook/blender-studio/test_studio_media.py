"""Committed media must be backed by the actual graded scene and real renders."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

from PIL import Image

HERE = Path(__file__).resolve().parent
MEDIA = HERE / "media"

spec = importlib.util.spec_from_file_location("studio_compose", MEDIA / "compose.py")
compose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compose)


class MediaTests(unittest.TestCase):
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
        self.assertEqual([r["frame"] for r in manifest["render_frames"][:12]],
                         list(range(1, 13)))
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
        self.assertEqual(float(probe["format"]["duration"]), 30)
        self.assertLessEqual((MEDIA / "demo.mp4").stat().st_size, 8_000_000)


if __name__ == "__main__":
    unittest.main()
