"""Offline checks of run.py's shard bookkeeping (no sandbox, no network).

Needs the sbx CLI package installed, like run.py: python3 -m unittest test_run
"""
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
    def shard(self, fetch_rc):
        FakeSandbox.killed = False
        fetched = subprocess.CompletedProcess([], fetch_rc, stdout="", stderr="boom" if fetch_rc else "ok")
        with tempfile.TemporaryDirectory() as out, \
                mock.patch.object(run, "Sandbox", mock.Mock(create=lambda *a, **k: FakeSandbox())), \
                mock.patch.object(run.subprocess, "run", return_value=fetched), \
                mock.patch.object(run, "confirm_gone"), mock.patch.object(run.time, "sleep"):
            return run.run_shard(0, ["crown-chest"], "tpl", Path(out), keep=False)

    def test_failed_download_is_reported_and_sandbox_kept(self):
        status = self.shard(fetch_rc=1)
        self.assertTrue(status.startswith("failed:download"), f"download failure reported as {status!r}")
        self.assertFalse(FakeSandbox.killed, "sandbox killed although its results were not downloaded")

    def test_clean_run_is_done_and_sandbox_killed(self):
        self.assertEqual(self.shard(fetch_rc=0), "done")
        self.assertTrue(FakeSandbox.killed)


if __name__ == "__main__":
    unittest.main()
