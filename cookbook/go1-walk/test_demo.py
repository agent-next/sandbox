"""Regression tests, with generated arrays and no GPU/API calls."""

import base64
import importlib.util
import io
import json
import re
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "judge"))
import grade
import selftest


class Array(np.ndarray):
    @property
    def device(self):
        return "cpu"

    def numel(self):
        return self.size


def array(value):
    return np.asarray(value).view(Array)


def module(name, path, torch):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"torch": torch}):
        spec.loader.exec_module(result)
    return result


class RegressionTests(unittest.TestCase):
    def test_mutant_setup_does_not_bundle_all_checkpoints(self):
        lease = Mock()

        def execute(code, timeout):
            self.assertLess(len(code.encode()), 1_500_000,
                            "mutant setup must ship checkpoints in separate bounded RPCs")
            return {"ok": True, "report": {"rc": 0, "names": []}}

        lease.exec.side_effect = execute
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("policy.npz", "step0.npz", "short.npz", "reward-flipped.npz"):
                (Path(tmp) / name).write_bytes(b"x" * 750_000)
            with self.assertRaisesRegex(RuntimeError, "invalid mutant inventory"):
                selftest.selftest_on_lease(lease, tmp, str(Path(tmp) / "result.json"))
        self.assertEqual(lease.exec.call_count, 6)

    def test_checkpoint_transfer_bounds_report_size(self):
        data = b"x" * 70_000
        lease = grade.Lease("test-only")

        def execute(code, timeout):
            offset = int(re.search(r"off = (\d+)", code)[1])
            chunk = int(re.search(r"off\+(\d+)", code)[1])
            self.assertLessEqual(chunk, 65536,
                                 "checkpoint transfer must bound each report chunk to 64 KiB")
            return {"ok": True, "report": {"n": len(data),
                "chunk": base64.b64encode(data[offset:offset+chunk]).decode()}}

        with patch.object(lease, "exec", side_effect=execute) as calls:
            self.assertEqual(lease.fetch_file("~/policy.npz"), data)
        self.assertEqual(calls.call_count, 2)

    def test_checkpoint_transfer_rejects_empty_progress(self):
        lease = grade.Lease("test-only")
        with patch.object(lease, "exec", return_value={
                "ok": True, "report": {"n": 100, "chunk": ""}}), \
                patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                lease.fetch_file("~/policy.npz")

    def test_reset_writes_indexed_positions_back(self):
        env = module("reset_env", HERE / "env.py", types.SimpleNamespace())
        obj = env.Go1Batch.__new__(env.Go1Batch)
        obj.qpos = array(np.zeros((3, 19)))
        obj.qvel = array(np.ones((3, 18)))
        obj.ctrl = array(np.zeros((3, 12)))
        obj.last_act = array(np.ones((3, 12)))
        obj.cmd = array(np.zeros((3, 3)))
        obj.ep_step = array(np.ones(3))
        obj.home_q = array([0, .9, -1.8] * 4)
        obj.home_ctrl = obj.home_q.copy()
        obj.cmd_vlo, obj.cmd_vhi = .4, 1.0
        obj.cmd_ylo, obj.cmd_yhi = -.3, .3
        obj._randn = lambda *shape: np.zeros(shape)
        obj._rand = lambda *shape: np.zeros(shape)
        obj._reset_idx(array([0, 2]))
        self.assertEqual(obj.qpos[0, 2], .27,
                         "reset must write advanced-indexed qpos back to the simulation")
        self.assertEqual(obj.qpos[2, 3], 1)
        self.assertEqual(obj.qpos[1, 2], 0)
        np.testing.assert_array_equal(obj.qpos[0, 7:], obj.home_q)

    def test_train_wall_is_elapsed_not_epoch(self):
        fake = types.SimpleNamespace(
            zeros=lambda *shape, **kw: np.zeros(shape),
            arange=lambda n, **kw: array(np.arange(n)),
            save=lambda *args: None,
            cuda=types.SimpleNamespace(synchronize=lambda: None,
                max_memory_allocated=lambda: 1, max_memory_reserved=lambda: 1))
        env = module("clock_env", HERE / "env.py", fake)
        with patch.dict(sys.modules, {"env": env, "torch": fake}):
            trainer = module("clock_train", HERE / "train.py", fake)
            batch = types.SimpleNamespace(qpos=array(np.zeros((2, 19))),
                reset_all=lambda: None, step=lambda x: None,
                gen=types.SimpleNamespace(get_state=lambda: None))
            ppo = types.SimpleNamespace(actor=object(),
                rollout=lambda env: (None, None),
                update=lambda *args: 1.0, state_dict=lambda: {})
            cfg = {**trainer.DEFAULT_CFG, "num_envs": 2, "iters": 1}
            with tempfile.TemporaryDirectory() as tmp, \
                    patch.object(trainer.E, "Go1Batch", return_value=batch), \
                    patch.object(trainer, "PPO", return_value=ppo), \
                    patch.object(trainer, "save_policy"), \
                    patch.object(trainer.time, "time", side_effect=
                                 (1_790_000_000 + i * .1 for i in range(100))):
                summary = trainer.train(cfg, tmp,
                    progress_file=str(Path(tmp) / "progress.json"))
            self.assertLess(summary["train_wall_s"], 2,
                            "training wall time must be elapsed seconds, not an epoch timestamp")
            self.assertGreater(summary["steps_per_s"], 1)

    def test_determinism_ignores_only_timing(self):
        v = {"ok": True, "gates": {"g1": {"pass": True, "value": .8}},
             "timing": {"wall_s": 1}}
        same = json.loads(json.dumps(v))
        same["timing"]["wall_s"] = 2
        self.assertTrue(selftest.same_verdict(v, same))
        same["gates"]["g1"]["value"] += .000001
        self.assertFalse(selftest.same_verdict(v, same))
        same = json.loads(json.dumps(v))
        same["traces"] = {"101": "different"}
        self.assertFalse(selftest.same_verdict(v, same))

    def test_judge_errors_do_not_count_as_mutant_kills(self):
        with self.assertRaisesRegex(RuntimeError, "execution failed"):
            selftest.checked_verdict({"rc": 2, "verdict":
                {"ok": False, "error": "stack drift", "gates": {}}})

    def test_cleanup_requires_404_not_dead_phase(self):
        lease = grade.Lease("test-only")
        lease.id = "gl-test"
        replies = [(204, None), (200, {"phase": "dead"}),
                   (204, None), (404, None)]
        with patch.object(grade, "request", side_effect=replies) as request, \
                patch.object(grade.time, "sleep"), \
                patch("sys.stderr", io.StringIO()):
            lease.delete()
        self.assertEqual(request.call_count, 4)
        self.assertIsNone(lease.id)

    def test_failed_cleanup_retains_lease_id(self):
        lease = grade.Lease("test-only")
        lease.id = "gl-test"
        with patch.object(grade, "request", return_value=(503, None)), \
                patch.object(grade.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "gl-test"):
                lease.delete()
        self.assertEqual(lease.id, "gl-test")

    def test_ambiguous_post_is_not_resent(self):
        body = io.BytesIO(b'{"message":"gateway reply lost"}')
        error = HTTPError("https://api.sbx.agent-next.com/sandboxes",
                          502, "bad gateway", {}, body)
        with patch.object(grade, "urlopen", side_effect=error) as open_url, \
                patch.object(grade.time, "sleep"):
            status, _ = grade.request("test-only", "POST", "/sandboxes", {})
        self.assertEqual(status, 502)
        self.assertEqual(open_url.call_count, 1,
                         "an ambiguous POST must not be blindly resent")

    def test_invalid_id_never_becomes_a_cleanup_url(self):
        lease = grade.Lease("test-only")
        with patch.object(grade, "request", return_value=
                (201, {"sandboxID": "gl-1/../../admin"})) as request, \
                patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                lease.__enter__()
            self.assertIsNone(lease.id,
                              "an invalid lease id must never become a cleanup target")
            lease.delete()
        self.assertEqual(request.call_count, 1,
                         "cleanup must never request an unvalidated lease id")
        self.assertIsNone(lease.id)


if __name__ == "__main__":
    unittest.main()
