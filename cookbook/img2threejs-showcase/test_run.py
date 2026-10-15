"""Offline checks of run.py's shard bookkeeping (no sandbox, no network).

Needs the sbx CLI package installed, like run.py: python3 -m unittest test_run
"""
import inspect
import itertools
import os
import re
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

    def test_patience_extends_the_polling_deadline(self):
        # every poll after the start reads twice the base deadline: only patience >= 3 keeps polling
        clock = lambda: itertools.chain([0], itertools.repeat(run.DEADLINE_S * 2))
        with mock.patch.object(run.time, "monotonic", side_effect=clock()):
            self.assertEqual(self.shard(fetch_rc=0, patience=3), "done", "polling stopped at the unscaled deadline")
        with mock.patch.object(run.time, "monotonic", side_effect=clock()):
            self.assertNotEqual(self.shard(fetch_rc=0, patience=1), "done", "polling ran past the deadline")

    def test_uploaded_renderer_scales_its_waits_by_patience(self):
        self.shard(fetch_rc=0, patience=3)
        js = next(c.args[1] for c in self.sbx.files.write.call_args_list if c.args[0].endswith("render_all.cjs"))
        consts = "\n".join(re.findall(r"^const (?:PATIENCE|OVERLAY_MS|SHOT_MS|TARGET_MS) = .*$", js, re.M))
        waits = lambda p: subprocess.run(
            ["node", "-e", consts + "\nconsole.log(JSON.stringify([OVERLAY_MS, SHOT_MS, TARGET_MS]))"],
            env={**os.environ, "PATIENCE": str(p)}, capture_output=True, text=True, check=True).stdout
        self.assertEqual([3 * w for w in eval(waits(1))], eval(waits(3)), "renderer waits do not scale with PATIENCE")

    def test_patience_below_one_is_rejected_before_any_sandbox(self):
        create = mock.Mock()
        with mock.patch.object(sys, "argv", ["run.py", "--patience", "0"]), \
                mock.patch.object(run, "Sandbox", mock.Mock(create=create)), \
                mock.patch.dict(os.environ, {"SBX_API_KEY": "<FAKE>"}), \
                self.assertRaises(SystemExit):
            run.main()
        create.assert_not_called()

    def test_clean_run_is_done_and_sandbox_killed(self):
        self.assertEqual(self.shard(fetch_rc=0), "done")
        self.assertTrue(FakeSandbox.killed)


if __name__ == "__main__":
    unittest.main()
