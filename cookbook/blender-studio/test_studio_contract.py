"""Fast tests: restrictive artifact protocol and failure/cleanup contracts."""
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


artifact = load("studio_artifact", HERE / "judge/artifact.py")
mutants = load("studio_mutants", HERE / "judge/mutants.py")
runner = load("studio_runner", HERE / "run.py")


class ContractTests(unittest.TestCase):
    def check_text(self, text):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "scene.py"
            path.write_text(text)
            return artifact.read_settings(path)

    def test_good(self):
        self.assertEqual(artifact.read_settings(HERE / "examples/good/scene.py")["period"], 12)

    def test_cannot_execute_or_rewrite_judge(self):
        good = (HERE / "examples/good/scene.py").read_text()
        for attack in ("\nopen('judge/grade.py','w').write('PASS')",
                       "\nimport os", "\nprint({'pass': True})",
                       "\nbuild_scene = lambda x: None"):
            with self.subTest(attack=attack):
                with self.assertRaises(ValueError):
                    self.check_text(good + attack)

    def test_extra_missing_duplicate_nonfinite_and_type(self):
        good = (HERE / "examples/good/scene.py").read_text()
        for text in (
            good.replace('"period": 12,', '"period": 12, "period": 12,'),
            good.replace('"period": 12,', ''),
            good.replace('"period": 12,', '"period": True,'),
            good.replace('"period": 12,', '"period": 12.0,'),
            good.replace('"hero_x": 0.0,', '"hero_x": 1e999,'),
            good.replace('"hero_x": 0.0,', '"hero_x": float("nan"),'),
            good.replace('"rim_link": True,', '"rim_link": 1,'),
            good.replace('"period": 12,', '"script": "claim", "period": 12,'),
        ):
            with self.subTest(text=text):
                with self.assertRaises((ValueError, TypeError)):
                    self.check_text(text)

    def test_mutants_change_one_setting(self):
        good = HERE / "examples/good/scene.py"
        original = artifact.read_settings(good)
        with tempfile.TemporaryDirectory() as temp:
            paths = mutants.generate(good, Path(temp))
            self.assertGreaterEqual(len(paths), 5)
            for name, path in paths.items():
                changed = artifact.read_settings(path)
                self.assertEqual(sum(original[k] != changed[k] for k in original), 1, name)

    def test_snapshot_excludes_keys_outputs_and_media(self):
        command = runner.snapshot()
        self.assertNotIn("SBX_API_KEY", command)
        self.assertNotIn("media/demo.mp4", command)
        self.assertNotIn("outputs-", command)
        self.assertIn("source snapshot sha256=", command)

    def test_failure_always_kills_and_lists(self):
        calls = []
        def fake(*args):
            calls.append(args)
            return "sandbox-test" if args[0] == "create" else ""
        with patch.object(runner, "sbx", side_effect=fake), \
             patch.object(runner, "remote_step", side_effect=RuntimeError("failed step")), \
             patch.object(runner.shutil, "which", return_value="sbx"), \
             patch.dict(runner.os.environ, {"SBX_API_KEY": "<your key>"}), \
             patch.object(sys, "argv", ["run.py"]):
            self.assertEqual(runner.main(), 1)
        self.assertIn(("create", "--template", "blender", "--timeout-min", "30"), calls)
        self.assertIn(("kill", "sandbox-test"), calls)
        self.assertIn(("list",), calls)

    def test_create_chatter_before_id_still_kills(self):
        calls = []
        def fake(*args):
            calls.append(args)
            return "notice: newer sbx available\nsandbox-test" if args[0] == "create" else ""
        with patch.object(runner, "sbx", side_effect=fake), \
             patch.object(runner, "remote_step", side_effect=RuntimeError("failed step")), \
             patch.object(runner.shutil, "which", return_value="sbx"), \
             patch.dict(runner.os.environ, {"SBX_API_KEY": "<your key>"}), \
             patch.object(sys, "argv", ["run.py"]):
            self.assertEqual(runner.main(), 1)
        self.assertIn(("kill", "sandbox-test"), calls)

    def test_cleanup_fails_when_id_still_listed(self):
        with patch.object(runner, "sbx", return_value="sandbox-test active"), \
             patch.object(runner.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "sandbox-test"):
                runner.cleanup("sandbox-test")

    def test_cleanup_requires_successful_inventory(self):
        with patch.object(runner, "sbx", side_effect=RuntimeError("transport down")), \
             patch.object(runner.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "cleanup unconfirmed"):
                runner.cleanup("sandbox-test")

    def test_lost_create_reply_warns_before_retry(self):
        errors = io.StringIO()
        with patch.object(runner, "sbx", side_effect=TimeoutError("lost create reply")), \
             patch.object(runner.shutil, "which", return_value="sbx"), \
             patch.dict(runner.os.environ, {"SBX_API_KEY": "<your key>"}), \
             patch.object(sys, "argv", ["run.py"]), contextlib.redirect_stderr(errors):
            self.assertEqual(runner.main(), 1)
        self.assertIn("sandbox alive", errors.getvalue())
        self.assertIn("inspect sbx list before retrying", errors.getvalue())

    def test_completion_marker_is_published_atomically(self):
        def fake(*args):
            if args[-1].startswith("nohup"):
                self.assertIn(".exit.tmp; mv ", args[-1])
                return ""
            return json.dumps({"done": True, "code": 0, "log": "step complete"})
        with patch.object(runner, "sbx", side_effect=fake):
            self.assertEqual(runner.remote_step(
                "sandbox-test", "fixture", "true", 10), "step complete")


if __name__ == "__main__":
    unittest.main()
