import ast
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import mujoco
import numpy as np
from PIL import Image

import render

HERE = Path(__file__).resolve().parent


class MediaTests(unittest.TestCase):
    def test_initializations_have_distinct_consistent_labels(self):
        self.assertEqual(render.policy_label("untrained"), "RANDOM INIT")
        self.assertEqual(render.mutant_label("untrained"), "PPO STEP-0")
        self.assertEqual(render.policy_label("ppo-step0"), "PPO STEP-0")

    def test_no_plotting_library_in_media(self):
        forbidden = "mat" + "plotlib"
        for path in HERE.glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                else:
                    continue
                self.assertFalse(any(m.split(".")[0] == forbidden for m in modules),
                                 f"plotting library in {path.name}")
        self.assertNotIn(forbidden, (HERE / "requirements.lock").read_text().lower())
        self.assertNotIn(forbidden, (HERE / "make_media.sh").read_text().lower())

    def test_state_check_rejects_drift(self):
        state = np.zeros(19)
        drift = state.copy()
        drift[0] = 1e-8
        with self.assertRaisesRegex(AssertionError, "differs from graded trajectory"):
            render.assert_state(drift, state, "test")
        render.assert_state(state.copy(), state, "test")

    def test_render_model_preserves_physics(self):
        model = render.visual_model()
        self.assertEqual(model.nq, 19)
        self.assertEqual(model.nu, 12)
        self.assertGreater(model.nlight, 0)
        self.assertGreater(model.ntex, 0)
        self.assertEqual(model.opt.timestep, .002)

    def test_replay_metrics_come_from_exact_scored_states(self):
        model = render.visual_model()
        for name in ("trained", "untrained"):
            for seed in (101, 202, 303):
                replay = render.Replay(model, name, seed)
                replay.data.qpos[:] = replay.qpos[0, 0]
                mujoco.mj_forward(model, replay.data)
                render.assert_state(replay.data.qpos, replay.qpos[0, 0], "initial state")
                replay.close()

    def test_replay_rejects_a_changed_checkpoint(self):
        model = render.visual_model()
        original = render.sha
        with patch.object(render, "sha", side_effect=lambda path:
                          "changed" if path.name == "policy.npz" else original(path)):
            with self.assertRaisesRegex(AssertionError, "checkpoint differs"):
                render.Replay(model, "trained", 101)

    def test_video_has_only_one_short_static_end_card(self):
        self.assertEqual(sum(count for _, count in render.SCENES), 900)
        self.assertEqual(render.SCENES[-1], ("end", 75))
        self.assertEqual({scene for scene, _ in render.SCENES[:-1]}, set(render.SHOTS))
        self.assertLessEqual(dict(render.SCENES)["train"], 90)

    def test_replay_camera_tracks_the_trunk(self):
        model = render.visual_model()
        replay = render.Replay(model, "trained", 101)
        self.assertEqual(replay.camera.type, mujoco.mjtCamera.mjCAMERA_TRACKING,
                         "video camera must track the trunk body")
        self.assertEqual(replay.camera.trackbodyid, model.body("trunk").id)
        replay.close()

    def test_every_moving_shot_advances_exact_states_without_freezing(self):
        model = render.visual_model()
        for scene, count in render.SCENES[:-1]:
            name, seed, _, _, distance = render.SHOTS[scene]
            replay = render.Replay(model, name, seed)
            self.assertEqual(replay.camera.type, mujoco.mjtCamera.mjCAMERA_TRACKING)
            self.assertEqual(replay.camera.trackbodyid, model.body("trunk").id)
            self.assertLessEqual(distance, 1.15)
            indices = [render.replay_index(scene, frame, replay.first_fall)
                       for frame in range(count)]
            self.assertTrue(all(b > a for a, b in zip(indices, indices[1:])))
            self.assertLess(max(indices), len(replay.qpos))
            self.assertTrue(all(np.max(np.abs(replay.qpos[b]-replay.qpos[a])) > 1e-9
                                for a, b in zip(indices, indices[1:])))
            if replay.first_fall is not None:
                self.assertLessEqual(max(indices), replay.first_fall)
            replay.close()

    def test_media_contract_and_checks(self):
        manifest = json.loads((HERE / "MANIFEST.json").read_text())
        video = manifest["video"]
        self.assertEqual((video["width"], video["height"], video["fps"]), (1920, 1080, 30))
        self.assertEqual(video["duration_s"], 30)
        self.assertLess(video["bytes"], 8_000_000)
        self.assertEqual(sum(manifest["render"]["state_checks"].values()), 831)
        self.assertTrue(manifest["render"]["graphics"]["renderer"])
        for name, digest in manifest["source_sha256"].items():
            self.assertEqual(hashlib.sha256((HERE.parent / name).read_bytes()).hexdigest(),
                             digest, f"changed media input: {name}")
        for name, row in manifest["files"].items():
            self.assertEqual(hashlib.sha256((HERE / name).read_bytes()).hexdigest(),
                             row["sha256"], f"stale media/source: {name}")
        for name in ("result.png", "loop.png"):
            with Image.open(HERE / name) as image:
                self.assertGreaterEqual(image.width, 1200)
                self.assertAlmostEqual(image.info["dpi"][0], 200, delta=.1)
        raw = (HERE / "demo.mp4").read_bytes()
        self.assertLess(raw.index(b"moov"), raw.index(b"mdat"))
        self.assertIn("ignored, CRF 0", video["master"])
        master = HERE / "master/demo.mp4"
        if master.exists():
            self.assertIn(b"qp=0", master.read_bytes()[:10000])


if __name__ == "__main__":
    unittest.main()
