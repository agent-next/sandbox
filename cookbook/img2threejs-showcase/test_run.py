"""Offline checks of run.py's shard bookkeeping (no sandbox, no network).

Needs the sbx CLI package installed, like run.py: python3 -m unittest test_run
"""
import inspect
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run  # noqa: E402


class FakeSandbox:
    sandbox_id = "sbx-test"
    killed = False

    def __init__(self):
        self.files = mock.Mock()
        self.commands = mock.Mock()
        self.commands.run.return_value = types.SimpleNamespace(stdout="done")

    def kill(self):
        FakeSandbox.killed = True


class RunShardTest(unittest.TestCase):
    def shard(self, fetch_rc, **kw):
        FakeSandbox.killed = False
        self.created = {}

        def create(template, timeout):
            self.created["timeout"] = timeout
            return self.sbx

        self.sbx = FakeSandbox()
        fetched = subprocess.CompletedProcess([], fetch_rc, stdout="", stderr="boom" if fetch_rc else "ok")
        with tempfile.TemporaryDirectory() as out, \
                mock.patch.object(run, "Sandbox", mock.Mock(create=create)), \
                mock.patch.object(run.subprocess, "run", return_value=fetched), \
                mock.patch.object(run, "confirm_gone"), mock.patch.object(run.time, "sleep"):
            return run.run_shard(0, ["crown-chest"], "tpl", Path(out), keep=False, **kw)

    def test_failed_download_is_reported_and_sandbox_kept(self):
        status = self.shard(fetch_rc=1)
        self.assertTrue(status.startswith("failed:download"), f"download failure reported as {status!r}")
        self.assertFalse(FakeSandbox.killed, "sandbox killed although its results were not downloaded")

    def test_patience_scales_the_render_waits_and_sandbox_lifetime(self):
        self.assertIn("patience", inspect.signature(run.run_shard).parameters, "run_shard takes no patience")
        self.shard(fetch_rc=0, patience=3)
        launches = [c.args[0] for c in self.sbx.commands.run.call_args_list if "pipeline.sh" in c.args[0]]
        self.assertTrue(launches and "PATIENCE=3 " in launches[0], f"pipeline launched without PATIENCE=3: {launches}")
        self.assertEqual(self.created["timeout"], run.DEADLINE_S * 3 + 3600)

    def test_clean_run_is_done_and_sandbox_killed(self):
        self.assertEqual(self.shard(fetch_rc=0), "done")
        self.assertTrue(FakeSandbox.killed)


if __name__ == "__main__":
    unittest.main()
