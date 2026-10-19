"""Stdlib unit tests for the sim-tuner judge (no GPU lease, no network).

    python3 -m unittest discover -s cookbook/sim-tuner/tests

Needs the pinned judge toolchain (mujoco 3.8.1 + numpy), i.e. the interpreter
`judge/setup.sh` installs; the engine module imports mujoco at import time.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

JUDGE = Path(__file__).resolve().parent.parent / "judge"
DEMO = JUDGE.parent
GOOD = DEMO / "examples" / "good" / "params.json"
sys.path.insert(0, str(JUDGE))

import _grade as G  # noqa: E402
import engine as E  # noqa: E402


class SetupIdempotence(unittest.TestCase):
    def test_python_313_accepts_its_pinned_numpy(self):
        source = (JUDGE / "setup.sh").read_text()
        check = source.split("import importlib.util as u", 1)[1].split("\nEOF", 1)[0]
        check = "import importlib.util as u" + check
        with patch.object(sys, "version_info", (3, 13, 5)), \
                patch.object(E.np, "__version__", "2.1.3"), \
                self.assertRaises(SystemExit) as exit:
            exec(check, {})
        self.assertEqual(exit.exception.code, 0,
                         "setup must accept the NumPy version its cp313 lock installs")


def write_params(obj_or_text):
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    if isinstance(obj_or_text, str):
        fh.write(obj_or_text)
    else:
        json.dump(obj_or_text, fh)
    fh.close()
    return fh.name


class DuplicateKeys(unittest.TestCase):
    """A strict JSON artifact has at most one binding per key."""

    def test_duplicate_key_is_rejected(self):
        path = write_params('{"mu": 0.5, "mu": 0.6, "solref_tc": 0.01, '
                            '"solref_dr": 1.0, "damping": 0.15, "armature": 0.02}')
        self.addCleanup(os.unlink, path)
        with self.assertRaises(ValueError) as cm:
            G.load_artifact(path)
        self.assertIn("mu", str(cm.exception))

    def test_duplicate_key_nested_in_a_value_is_rejected(self):
        path = write_params('{"mu": {"a": 1, "a": 2}, "solref_tc": 0.01, '
                            '"solref_dr": 1.0, "damping": 0.15, "armature": 0.02}')
        self.addCleanup(os.unlink, path)
        with self.assertRaises(ValueError):
            G.load_artifact(path)

    def test_the_good_artifact_still_loads(self):
        params = G.load_artifact(str(GOOD))
        self.assertEqual(sorted(params), sorted(E.PARAM_NAMES))


class VersionTable(unittest.TestCase):
    """The lease stack check must cover every field the SPEC pins."""

    def setUp(self):
        table = json.loads((JUDGE / "version-table.json").read_text())
        self.expected = table["gpu"]

    def test_recorded_table_matches_itself(self):
        self.assertEqual(E.check_version_table(dict(self.expected), self.expected), [])

    def test_mujoco_warp_mismatch_is_named(self):
        actual = dict(self.expected, mujoco_warp="0.0.0")
        problems = E.check_version_table(actual, self.expected)
        self.assertTrue(any("mujoco_warp" in p for p in problems), problems)

    def test_warp_mismatch_is_named(self):
        actual = dict(self.expected, warp="0.0.0")
        problems = E.check_version_table(actual, self.expected)
        self.assertTrue(any("warp" in p for p in problems), problems)

    def test_missing_mujoco_warp_is_reported(self):
        actual = {k: v for k, v in self.expected.items() if k != "mujoco_warp"}
        problems = E.check_version_table(actual, self.expected)
        self.assertTrue(any("mujoco_warp" in p for p in problems), problems)

    def test_older_mujoco_is_reported(self):
        actual = dict(self.expected, mujoco="3.7.0", mujoco_cv=[3, 7, 0])
        problems = E.check_version_table(actual, self.expected)
        self.assertTrue(any("older" in p or "mujoco" in p for p in problems), problems)


class OverallContract(unittest.TestCase):
    """pass/verdict must distinguish a complete grade from a CPU-only one."""

    def test_complete_all_gates_green_is_a_pass(self):
        self.assertEqual(G.overall([True, True, True, True], complete=True),
                         (0, True, "PASS"))

    def test_cpu_only_green_is_incomplete_not_a_pass(self):
        rc, passed, verdict = G.overall([True, True, True], complete=False)
        self.assertEqual(rc, 0)
        self.assertFalse(passed, "a CPU-only grade (G4 skipped) claimed a full pass")
        self.assertEqual(verdict, "INCOMPLETE")

    def test_failing_gate_is_a_fail(self):
        self.assertEqual(G.overall([True, False, True], complete=False),
                         (1, False, "FAIL"))


class CpuOnlyGrade(unittest.TestCase):
    """grade(gpu=False) records G4 as skipped and never claims completeness."""

    def test_cpu_only_verdict_is_incomplete_and_exit_code_is_cpu_gates(self):
        verdict, rc, _scen, lease = G.grade(str(GOOD), 7, gpu=False)
        self.assertIsNone(lease)
        self.assertEqual(rc, 0, "the good artifact must pass the CPU gates")
        self.assertFalse(verdict["pass"])
        self.assertFalse(verdict["complete"])
        self.assertEqual(verdict["verdict"], "INCOMPLETE")
        self.assertIsNone(verdict["gates"]["G4_gpu_cpu_agree"]["pass"])


class BundleContract(unittest.TestCase):
    def test_scenario_bundle_is_json_and_round_trips(self):
        scenario = E.gen_scenario(7)
        restored = E.load_scenario(json.loads(json.dumps(E.bundle_scenario(scenario))))
        self.assertEqual(restored["truth"], scenario["truth"])
        for split in ("refs_train", "refs_hold"):
            E.np.testing.assert_array_equal(restored[split], scenario[split])
        E.np.testing.assert_array_equal(restored["scale"], scenario["scale"])


class LeaseOwnership(unittest.TestCase):
    """A lease created inside grade() must be closed there when a gate raises."""

    class FakeLease:
        instances = []

        def __init__(self, key):
            self.key = key
            self.id = None
            self.create_s = 0.0
            self.exec_wall_s = []
            self.closed = False
            FakeLease = LeaseOwnership.FakeLease
            FakeLease.instances.append(self)

        def create(self):
            self.id = "gl-fake"

        def exec(self, code, timeout=None):
            raise RuntimeError("gpu exec exploded")

        def close(self):
            self.closed = True

    def test_lease_is_closed_when_the_gpu_gate_raises(self):
        LeaseOwnership.FakeLease.instances = []
        real = G.GpuLease
        old_key = os.environ.get("SBX_API_KEY")
        os.environ["SBX_API_KEY"] = "test-key-not-used"
        G.GpuLease = LeaseOwnership.FakeLease
        try:
            with self.assertRaises(RuntimeError):
                G.grade(str(GOOD), 7, gpu=True)
        finally:
            G.GpuLease = real
            if old_key is None:
                os.environ.pop("SBX_API_KEY", None)
            else:
                os.environ["SBX_API_KEY"] = old_key
        leases = LeaseOwnership.FakeLease.instances
        self.assertEqual(len(leases), 1)
        self.assertTrue(leases[0].closed,
                        "grade() leaked the lease it created when the gate raised")


class BiasedFitMutant(unittest.TestCase):
    """The former 'overfit' mutant is an honestly named deterministic bias."""

    def setUp(self):
        import mutants
        self.mutants = mutants
        self.scen = E.gen_scenario(7)

    def test_overfit_search_helper_is_gone(self):
        self.assertFalse(hasattr(self.mutants, "overfit_train"),
                         "the misleading overfit_train search helper still exists")

    def test_biased_fit_is_deterministic_within_range_and_fails_g3(self):
        a = self.mutants.biased_fit(self.scen)
        b = self.mutants.biased_fit(self.scen)
        self.assertEqual(a, b)
        for name, v in a.items():
            lo, hi = E.RANGES[name]
            self.assertTrue(lo <= v <= hi, f"{name}={v} outside [{lo}, {hi}]")
        hold = E.error_of(a, self.scen["refs_hold"], self.scen["ics_hold"], self.scen["scale"])
        self.assertGreater(hold, E.ORACLE_ABS_ERR,
                           "the biased-fit mutant survives G3")

    def test_mutant_set_is_named_honestly_and_has_18_members(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.environ.get("SIM_TUNER_SEED")
            os.environ["SIM_TUNER_SEED"] = "7"
            try:
                names = self.mutants.generate(d)
            finally:
                if old is None:
                    os.environ.pop("SIM_TUNER_SEED", None)
                else:
                    os.environ["SIM_TUNER_SEED"] = old
        self.assertEqual(len(names), 18, names)
        self.assertIn("mut_biased_fit", names)
        self.assertNotIn("mut_overfit_train", names)


class SelftestHarness(unittest.TestCase):
    """selftest.sh must not score infrastructure errors or survivors as kills."""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="st-selftest-")

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def _copy_demo(self):
        shutil.copytree(JUDGE, os.path.join(self.work, "judge"))
        shutil.copytree(DEMO / "examples", os.path.join(self.work, "examples"))
        # Generated process fixture: exercise the real shell bookkeeping without
        # leasing a GPU. Physical mutant rejection is covered separately.
        script = '''#!/usr/bin/env python3
import json, os, pathlib, sys
a = sys.argv[1:]
assert a[a.index("--seed") + 1] == os.environ.get("SIM_TUNER_SEED", "7")
target = pathlib.Path(a[0]).name == "mut_biased_fit.json"
mutant = pathlib.Path(a[0]).name.startswith("mut_")
fault = os.environ.get("SELFTEST_TEST_FAULT", "")
if target and fault == "infra":
    sys.exit(2)
if target and fault == "missing":
    sys.exit(1)
cpu = "--cpu-only" in a or (not mutant and fault == "known-good-cpu-only")
failed = mutant and not (target and fault in ("survive", "empty"))
gates = {n: {"pass": True} for n in ("G1_ranges", "G2_train", "G3_heldout")}
gates["G4_gpu_cpu_agree"] = {"pass": None if cpu else True}
if failed:
    gates["G4_gpu_cpu_agree" if target and fault == "g4-only" else "G3_heldout"]["pass"] = False
v = {"gates": gates, "pass": not failed and not cpu, "complete": not cpu,
     "verdict": "FAIL" if failed else "INCOMPLETE" if cpu else "PASS"}
pathlib.Path(a[a.index("--json") + 1]).write_text(json.dumps(v))
sys.exit(1 if failed or (target and fault == "empty") else 0)
'''
        fixture = Path(self.work) / "judge/fake_grade.py"
        fixture.write_text(script)
        (Path(self.work) / "judge/grade.sh").write_text(
            f'#!/usr/bin/env bash\nexec "{sys.executable}" "{fixture}" "$@"\n')

    def _selftest(self, fault=""):
        env = dict(os.environ, SIM_TUNER_PYTHON=sys.executable,
                   SIM_TUNER_GPU_LOCAL="1", SELFTEST_TEST_FAULT=fault)
        return subprocess.run(["bash", str(os.path.join(self.work, "judge", "selftest.sh"))],
                              cwd=self.work, env=env, capture_output=True,
                              text=True, timeout=1800)

    def test_shell_accepts_real_gate_kills(self):
        self._copy_demo()
        r = self._selftest()
        self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
        self.assertIn("kill rate: 18/18", r.stdout)

    def test_a_surviving_mutant_fails_the_self_test(self):
        self._copy_demo()
        r = self._selftest("survive")
        self.assertNotEqual(r.returncode, 0, "a surviving mutant did not fail the self-test")
        self.assertIn("NOT KILLED", r.stdout + r.stderr)

    def test_an_infrastructure_error_is_not_a_kill(self):
        self._copy_demo()
        r = self._selftest("infra")
        self.assertNotEqual(r.returncode, 0, "an infra exit-2 was counted as a kill")
        self.assertIn("rc=2", r.stdout + r.stderr)

    def test_a_cpu_only_known_good_is_not_reported_as_pass(self):
        self._copy_demo()
        r = self._selftest("known-good-cpu-only")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a full PASS", r.stderr)

    def test_missing_verdict_is_not_a_kill(self):
        self._copy_demo()
        r = self._selftest("missing")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("NOT KILLED", r.stderr)

    def test_only_gpu_failure_is_not_a_cpu_mutant_kill(self):
        self._copy_demo()
        r = self._selftest("g4-only")
        self.assertNotEqual(r.returncode, 0, "G4 alone cannot prove a CPU mutant kill")

    def test_rc_one_without_failed_gate_is_not_a_kill(self):
        self._copy_demo()
        r = self._selftest("empty")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("NOT KILLED", r.stderr)


if __name__ == "__main__":
    unittest.main()
