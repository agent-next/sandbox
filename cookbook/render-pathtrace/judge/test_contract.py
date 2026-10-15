"""Fast validation and runner regression tests, executed inside the sandbox."""

import copy
import base64
import importlib.util
import json
from pathlib import Path
import unittest
import subprocess
import tempfile
from unittest.mock import Mock, patch

import numpy as np

from grade import g1, g3, g4, masks, save_outputs, validate
from driver import Renderer
import grade as judge

HERE = Path(__file__).resolve().parent
GOOD = json.loads((HERE.parent / "examples/good/scene.json").read_text())
spec = importlib.util.spec_from_file_location("runner", HERE.parent / "run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ContractTests(unittest.TestCase):
    def test_good(self):
        validate(GOOD)

    def test_gpu_resolution_and_sample_budgets(self):
        for resolution, spp in (([1024, 1024], 128), ([512, 512], 512)):
            scene = copy.deepcopy(GOOD)
            scene.update(resolution=resolution, spp=spp)
            with self.assertRaises(AssertionError):
                validate(scene)

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

    def test_software_adapter_architecture_not_vendor_label(self):
        image = np.ones((64, 64, 4), dtype="<f4")
        result = {"backend": "webgpu", "adapter": "google",
                  "adapter_info": {"architecture": "swiftshader"},
                  "samples": 32, "width": 64, "height": 64,
                  "data": base64.b64encode(image.tobytes()).decode()}
        renderer = Renderer("cpu")
        renderer.page = Mock()
        renderer.page.evaluate.return_value = result
        scene = copy.deepcopy(GOOD)
        scene["resolution"] = [64, 64]
        self.assertTrue(np.array_equal(renderer.render(scene, 32, 17), image))
        result["adapter_info"] = {"architecture": "hardware"}
        with self.assertRaisesRegex(AssertionError, "not SwiftShader"):
            renderer.render(scene, 32, 17)

    def test_gpu_rejects_software_or_unidentified_adapter(self):
        image = np.ones((64, 64, 4), dtype="<f4")
        renderer = Renderer("gpu")
        renderer.page = Mock()
        result = {"backend": "webgpu", "adapter": "nvidia",
                  "adapter_info": {"vendor": "nvidia", "architecture": "blackwell"},
                  "samples": 32, "width": 64, "height": 64,
                  "data": base64.b64encode(image.tobytes()).decode()}
        renderer.page.evaluate.return_value = result
        scene = copy.deepcopy(GOOD)
        scene["resolution"] = [64, 64]
        self.assertTrue(np.array_equal(renderer.render(scene, 32, 17), image))
        for info in (None, {"vendor": "google", "architecture": "swiftshader"},
                     {"vendor": "nvidia", "architecture": "swiftshader"}):
            result["adapter_info"] = info
            with self.assertRaises(AssertionError):
                renderer.render(scene, 32, 17)

    def test_saved_hdr_and_preview(self):
        image = np.full((2, 3, 4), 0.5, dtype="<f4")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "studio.npy"
            save_outputs(path, image)
            self.assertTrue(np.array_equal(np.load(path), image))
            summary = json.loads(path.with_suffix(".json").read_text())
            self.assertEqual(summary["rgb_mean"], [0.5, 0.5, 0.5])
            self.assertEqual(summary["shape"], [2, 3, 4])
            self.assertTrue(path.with_suffix(".png").read_bytes().startswith(b"\x89PNG"))

    def test_process_deadline_fails_closed(self):
        process = Mock(pid=123)
        process.communicate.side_effect = [
            subprocess.TimeoutExpired("fixture", 595), ("", "")
        ]
        with patch.object(judge.subprocess, "Popen", return_value=process), \
             patch.object(judge, "kill_owned_tree") as kill, \
             patch("sys.argv", ["grade.py", str(HERE.parent / "examples/good/scene.json")]):
            self.assertEqual(judge.main(), 1)
            kill.assert_called_once_with(123)

    def test_runner_cleanup_on_step_failure(self):
        calls = []

        def sbx(*args):
            calls.append(args)
            return "sandbox-test" if args[0] == "create" else ""

        with patch.object(runner, "sbx", side_effect=sbx), \
             patch.object(runner, "remote_step", side_effect=RuntimeError("step failed")), \
             patch.object(runner.shutil, "which", return_value="/usr/bin/sbx"), \
             patch.dict(runner.os.environ, {"SBX_API_KEY": "<your key>"}), \
             patch("sys.argv", ["run.py", "--backend", "cpu"]):
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
             patch("sys.argv", ["run.py", "--backend", "cpu"]):
            self.assertEqual(runner.main(), 1)


if __name__ == "__main__":
    unittest.main()
