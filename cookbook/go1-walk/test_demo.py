"""Regression tests, with generated arrays and no GPU/API calls."""

import base64
import copy
import hashlib
import importlib.util
import io
import json
import os
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
import mutants

MUTANT_NAMES = ("ppo-step0", "short-training", "reward-flipped", "random-init",
                "zero-output", "negated-output", "shuffled-output", "noisy-weights",
                "clipped-output", "weak-output", "torque-heavy")


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
    def test_lost_exec_reply_recovers_without_repeating_work(self):
        lease = grade.Lease("test-only")
        lease.id = "gl-test"
        executions = []
        requests = 0
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "executions"
            code = (f"from pathlib import Path\np = Path({str(marker)!r})\n"
                    "p.write_text(p.read_text() + 'x' if p.exists() else 'x')\n"
                    "report['value'] = 42\n")

            def request(key, method, path, body, timeout):
                nonlocal requests
                requests += 1
                if 2 <= requests <= 8:
                    return 409, {"message": "original job is still running"}
                scope = {"report": {}}
                exec(body["code"], scope)
                executions.append(body["code"])
                if len(executions) == 1:
                    raise TimeoutError("reply lost after execution")
                return 200, {"result": {"ok": True, "report": scope["report"]}}

            with patch.dict(os.environ, {"HOME": tmp}), \
                    patch.object(grade, "request", side_effect=request), \
                    patch.object(grade.time, "sleep"), patch("sys.stderr", io.StringIO()):
                try:
                    result = lease.exec(code, 120)
                except (Exception, SystemExit) as exc:
                    self.fail(f"a lost exec reply must recover its saved result: {exc}")
            self.assertEqual(result["report"]["value"], 42,
                             "a lost exec reply must recover its saved result")
            self.assertEqual(marker.read_text(), "x",
                             "recovering a lost reply must never repeat training")
            self.assertEqual(executions[0], executions[1],
                             "recovery must use the same execution token")
            self.assertEqual(requests, 9,
                             "recovery must wait for the original job, not stop after six busy replies")

    def test_interrupted_exec_is_never_repeated(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"HOME": tmp}):
            root = Path(tmp) / ".go1-exec-results"
            root.mkdir()
            (root / "test.started").touch()
            code = grade.ONCE.replace("__TOKEN__", repr("test")).replace(
                "__CODE__", repr("report['should_not_run'] = True"))
            scope = {"report": {}}
            exec(code, scope)
            result = scope["report"]["go1_cached_result"]
            self.assertFalse(result["ok"])
            self.assertNotIn("should_not_run", result["report"],
                             "an interrupted execution must not run a second time")

    def test_failed_exec_is_cached_not_retried_as_success(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"HOME": tmp}):
            code = grade.ONCE.replace("__TOKEN__", repr("test")).replace(
                "__CODE__", repr("raise ValueError('real job failure')"))
            for _ in range(2):
                scope = {"report": {}}
                exec(code, scope)
                result = scope["report"]["go1_cached_result"]
                self.assertFalse(result["ok"])
                self.assertIn("ValueError: real job failure", result["stderr"])

    def test_read_transport_failure_is_retried(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.status, response.read.return_value = 200, b'{}'
        with patch.object(grade, "urlopen", side_effect=[TimeoutError(), response]) as call, \
                patch.object(grade.time, "sleep"):
            self.assertEqual(grade.request("test-only", "GET", "/sandboxes/gl-test"),
                             (200, {}))
        self.assertEqual(call.call_count, 2)

    def test_failed_good_grade_is_retained_for_the_loop_log(self):
        lease = Mock()
        lease.exec.return_value = {"ok": True, "report": {
            "rc": 0, "names": list(MUTANT_NAMES)}}
        verdict = {"ok": False, "measured": {"mean_forward_mps": .4},
                   "gates": {"g1_forward_speed": {"pass": False, "value": .4}}}
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("policy.npz", "step0.npz", "short.npz", "reward-flipped.npz"):
                (Path(tmp) / name).write_bytes(b"test")
            output = Path(tmp) / "selftest.json"
            with patch.object(grade, "grade_on_lease", return_value={
                    "rc": 1, "verdict": verdict}), patch("sys.stdout", io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "known-good artifact did not pass"):
                    selftest.selftest_on_lease(lease, tmp, str(output))
            self.assertTrue(output.is_file(),
                            "a failed good grade must remain available for the loop log")
            recorded = json.loads(output.read_text())
            self.assertEqual(recorded["good_run1"], verdict)
            self.assertFalse(recorded["ok"])

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
        self.assertEqual(lease.exec.call_count, 7)

    def test_mutants_change_artifacts_not_judge_conditions(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(sys, "argv", ["mutants.py", str(HERE / "examples/good"), tmp]), \
                patch("sys.stdout", io.StringIO()) as output:
            mutants.main()
            self.assertEqual(output.getvalue().split(), list(MUTANT_NAMES))
            self.assertFalse(list(Path(tmp).rglob("args.json")),
                             "artifact mutants must not alter judge conditions")
            recorded = json.loads((HERE / "examples/good/loop.json").read_text())
            verdict = recorded["iterations"][2]["verdict"]
            fixture = Path(tmp) / "torque-heavy/policy.npz"
            self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(),
                             verdict["policy_sha256"],
                             "G3-only fixture must reuse the measured iteration-3 policy")
            self.assertEqual([g for g, row in verdict["gates"].items() if not row["pass"]],
                             ["g3_torque_saturation"])

    def run_recorded_selftest(self, change=None, names=MUTANT_NAMES):
        """Exercise the whole self-test with saved verdicts, never fake a sim."""
        test = json.loads((HERE / "media/data/selftest.json").read_text())
        history = json.loads((HERE / "examples/good/loop.json").read_text())
        aliases = {"ppo-step0": "untrained", "clipped-output": "saturating"}

        def evaluate(lease, good, seeds, episodes, steps, mass, **kw):
            self.assertEqual((episodes, steps, mass), (64, 500, 1.0),
                             "every mutant must use the good artifact's judge conditions")
            if kw.get("remote_policy"):
                name = kw["remote_policy"].split("/")[-2]
                verdict = copy.deepcopy(history["iterations"][2]["verdict"]
                    if name == "torque-heavy" else
                    test["mutants"][aliases.get(name, name)]["verdict"])
                if change:
                    change(name, verdict)
            else:
                verdict = copy.deepcopy(test["good_run1"])
            return {"rc": 0 if verdict["ok"] else 1, "verdict": verdict}

        lease = Mock()
        lease.exec.return_value = {"ok": True, "report": {"rc": 0, "names": list(names)}}
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(grade, "grade_on_lease", side_effect=evaluate), \
                patch("sys.stdout", io.StringIO()):
            output = Path(tmp) / "selftest.json"
            try:
                return selftest.selftest_on_lease(lease, str(HERE / "examples/good"), str(output))
            except RuntimeError:
                self.assertFalse(json.loads(output.read_text())["ok"])
                raise

    def test_selftest_accepts_recorded_intended_gate_kills(self):
        result = self.run_recorded_selftest()
        self.assertTrue(result["ok"])
        self.assertEqual(result["total"], len(MUTANT_NAMES))
        self.assertEqual(result["mutants"]["torque-heavy"]["failed_gates"],
                         ["g3_torque_saturation"])

    def test_selftest_rejects_unintended_gate_kills_for_every_mutant(self):
        for target in MUTANT_NAMES:
            with self.subTest(mutant=target):
                def change(name, verdict):
                    if name == target:
                        # G1 kills everything except that it is not the intended
                        # fall/torque gate, and G4 still kills the slow mutants.
                        for gate, row in verdict["gates"].items():
                            row["pass"] = gate != "g4_beats_baseline"
                        verdict["ok"] = False
                with self.assertRaisesRegex(RuntimeError, "intended gates did not fail",
                    msg=f"{target} must fail its intended gate, not just any gate"):
                    self.run_recorded_selftest(change)

    def test_torque_mutant_must_fail_only_g3(self):
        def change(name, verdict):
            if name == "torque-heavy":
                verdict["gates"]["g1_forward_speed"]["pass"] = False
        with self.assertRaisesRegex(RuntimeError, "must fail only g3"):
            self.run_recorded_selftest(change)

    def test_selftest_cannot_silently_drop_torque_coverage(self):
        with self.assertRaisesRegex(RuntimeError, "invalid mutant inventory"):
            # Inventory is checked before any result is written.
            lease = Mock()
            lease.exec.return_value = {"ok": True, "report": {
                "rc": 0, "names": list(MUTANT_NAMES[:-1])}}
            with tempfile.TemporaryDirectory() as tmp:
                selftest.selftest_on_lease(lease, str(HERE / "examples/good"),
                                          str(Path(tmp) / "selftest.json"))

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

    def test_g2_g3_and_g5_independently_reject_bad_metrics(self):
        # Unit-level evaluator faults, not measured policies or fresh grades.
        fake_torch = types.SimpleNamespace(set_num_threads=lambda n: None)
        evaluator = module("gate_eval", HERE / "judge/_eval.py", fake_torch)
        good = {"forward_mps": .8, "min_forward_mps": .7,
                "fall_rate": 0.0, "sat_frac": .1, "peak_torque_ratio": 1.0}
        baseline = {**good, "forward_mps": 0.0}
        for intended in ("g2_fall_rate", "g3_torque_saturation", "g5_determinism"):
            with self.subTest(gate=intended):
                first, repeat = dict(good), dict(good)
                if intended == "g2_fall_rate":
                    first["fall_rate"] = repeat["fall_rate"] = .1
                elif intended == "g3_torque_saturation":
                    first["sat_frac"] = repeat["sat_frac"] = .2
                else:
                    repeat["min_forward_mps"] = .6
                with patch.dict(sys.modules, {"torch": fake_torch}), \
                        patch.object(sys, "argv", ["_eval.py", "--policy",
                            str(HERE / "examples/good/policy.npz"), "--seeds", "101"]), \
                        patch.object(evaluator, "MODEL", str(HERE / "model/go1_meshless.xml")), \
                        patch.object(evaluator, "check_stack", return_value=({}, [])), \
                        patch.object(evaluator, "load_policy", return_value=(object(), [])), \
                        patch.object(evaluator, "evaluate",
                                     side_effect=[first, repeat, baseline, baseline]), \
                        patch.object(evaluator, "emit") as emit:
                    self.assertEqual(evaluator.main(), 1)
                verdict = emit.call_args.args[0]
                self.assertNotIn("error", verdict)
                self.assertEqual([g for g, row in verdict["gates"].items()
                                  if not row["pass"]], [intended],
                                 f"{intended} must reject independently of all other gates")

    def test_cleanup_accepts_404_or_dead_only_after_delayed_checks(self):
        lease = grade.Lease("test-only")
        lease.id = "gl-test"
        replies = [(204, None), (404, None), (200, {"phase": "dead"}), (404, None)]
        with patch.object(grade, "request", side_effect=replies) as request, \
                patch.object(grade.time, "sleep") as sleep, \
                patch("sys.stderr", io.StringIO()):
            lease.delete()
        self.assertEqual(request.call_count, 4)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [15, 15],
                         "cleanup needs 3 GET checks spanning at least 30 seconds")
        self.assertIsNone(lease.id)

    def test_cleanup_does_not_trust_a_transient_404(self):
        lease = grade.Lease("test-only")
        lease.id = "gl-test"
        replies = [(204, None), (404, None), (200, {"phase": "running"})]
        with patch.object(grade, "request", side_effect=
                          replies + [(200, {"phase": "running"})] * 20), \
                patch.object(grade.time, "sleep"), patch("sys.stderr", io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "cleanup unconfirmed for gl-test"):
                lease.delete()
        self.assertEqual(lease.id, "gl-test",
                         "a transient 404 must not clear the cleanup target")

    def test_cleanup_accepts_a_persistent_dead_record(self):
        lease = grade.Lease("test-only")
        lease.id = "gl-test"
        with patch.object(grade, "request", side_effect=[
                (204, None), (200, {"phase": "dead"}),
                (200, {"phase": "dead"}), (200, {"phase": "dead"})]), \
                patch.object(grade.time, "sleep") as sleep:
            lease.delete()
        self.assertIsNone(lease.id)
        self.assertEqual(sleep.call_count, 2)

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

    def test_ambiguous_create_warns_about_orphan_inventory(self):
        for reply in (TimeoutError(), (502, None), (503, {"message": "reply lost"}),
                      (201, None), ValueError("unreadable JSON")):
            with self.subTest(reply=reply):
                lease = grade.Lease("test-only")
                options = {"side_effect": reply} if isinstance(reply, Exception) else \
                          {"return_value": reply}
                with patch.object(grade, "request", **options) as request, \
                        patch("sys.stderr", io.StringIO()) as errors:
                    with self.assertRaises(SystemExit):
                        lease.__enter__()
                self.assertIn("lease may have been created", errors.getvalue(),
                              "ambiguous create must warn about an orphaned lease")
                self.assertIn("inventory", errors.getvalue())
                self.assertEqual(request.call_count, 1)

    def test_capacity_retries_every_30_seconds(self):
        lease = grade.Lease("test-only")
        with patch.object(grade, "request", side_effect=[
                (409, None), (503, {"message": "GPU plane at capacity"}),
                (201, {"sandboxID": "gl-test"})]) as request, \
                patch.object(grade.threading, "Thread"), \
                patch.object(grade.time, "sleep") as sleep, \
                patch("sys.stderr", io.StringIO()):
            lease.__enter__()
        self.assertEqual(request.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [30, 30])

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
