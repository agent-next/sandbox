"""Fast validation and runner regression tests, executed inside the sandbox."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from grade import g1, g3, g4, masks, validate

HERE = Path(__file__).resolve().parent
GOOD = json.loads((HERE.parent / "examples/good/scene.json").read_text())
spec = importlib.util.spec_from_file_location("runner", HERE.parent / "run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ContractTests(unittest.TestCase):
    def test_good(self):
        validate(GOOD)

    def test_material_nonfinite(self):
        for value in (float("nan"), float("inf"), -0.1, 1.6):
            scene = copy.deepcopy(GOOD)
            scene["materials"]["clay"]["baseColor"][0] = value
            with self.assertRaises(AssertionError):
                validate(scene)

    def test_hidden_emission(self):
        scene = copy.deepcopy(GOOD)
        scene["materials"]["floor"]["emissionLuminance"] = 1
        with self.assertRaisesRegex(AssertionError, "undeclared"):
            validate(scene)
        scene["materials"]["floor"]["emissive"] = True
        validate(scene)

    def test_unknown_fields(self):
        scene = copy.deepcopy(GOOD)
        scene["script"] = "not executable"
        with self.assertRaisesRegex(AssertionError, "unsupported"):
            validate(scene)

    def test_furnace_oracle_positive_and_negative(self):
        class AnalyticFixture:
            def render(self, scene, spp, seed):
                image = np.ones((32, 32, 4), dtype=np.float32)
                sphere, _ = masks()
                image[sphere, :3] = scene["materials"]["test"]["baseColor"]
                return image

        self.assertTrue(g1(AnalyticFixture(), 17)["pass"])
        self.assertFalse(g1(AnalyticFixture(), 17, wrong=True)["pass"])

    def test_convergence_oracle_and_stuck_sampler(self):
        class MonteCarloFixture:
            def __init__(self, stuck=False):
                self.stuck = stuck

            def render(self, scene, spp, seed):
                error = 0 if spp == 128 else (1 if self.stuck else spp**-0.5)
                return np.full((64, 64, 4), error, dtype=np.float32)

        self.assertAlmostEqual(g3(MonteCarloFixture(), GOOD, 17)["slope"], -0.5)
        self.assertFalse(g3(MonteCarloFixture(True), GOOD, 17)["pass"])

    def test_hdr_hash_seed_control(self):
        class SeedFixture:
            def render(self, scene, spp, seed):
                return np.full((64, 64, 4), seed, dtype=np.float32)

        result, _, _ = g4(SeedFixture(), GOOD, 17)
        self.assertTrue(result["pass"])

    def test_runner_cleanup_on_step_failure(self):
        calls = []

        def sbx(*args):
            calls.append(args)
            return "sandbox-test" if args[0] == "create" else ""

        with patch.object(runner, "sbx", side_effect=sbx), \
             patch.object(runner, "remote_step", side_effect=RuntimeError("step failed")), \
             patch.object(runner.shutil, "which", return_value="/usr/bin/sbx"), \
             patch.dict(runner.os.environ, {"SBX_API_KEY": "<your key>"}), \
             patch("sys.argv", ["run.py"]):
            self.assertEqual(runner.main(), 1)
        self.assertIn(("kill", "sandbox-test"), calls)
        self.assertIn(("list",), calls)

    def test_runner_fails_unconfirmed_cleanup(self):
        def sbx(*args):
            return "sandbox-test"

        with patch.object(runner, "sbx", side_effect=sbx), \
             patch.object(runner, "remote_step",
                          return_value='{"pass":true,"backend":"webgpu","adapter":"test"}'), \
             patch.object(runner.shutil, "which", return_value="/usr/bin/sbx"), \
             patch.dict(runner.os.environ, {"SBX_API_KEY": "<your key>"}), \
             patch("sys.argv", ["run.py"]):
            self.assertEqual(runner.main(), 1)


if __name__ == "__main__":
    unittest.main()
