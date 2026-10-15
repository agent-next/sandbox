"""Fault-injection tests for run.py's sandbox handling (no network).

    python3 -m unittest discover -s cookbook/solidcraft-cad/tests
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import run  # noqa: E402

SID = "sbx-test-id"
VERDICT = json.dumps({"passed": True, "gates": {}})


def done(rc=0, out="", err=""):
    return subprocess.CompletedProcess("sbx", rc, out, err)


class Cleanup(unittest.TestCase):
    def main_with(self, kill, listing):
        def fake_sbx(*args, timeout=120.0):
            if args[0] == "create":
                return done(out=SID + "\n")
            if args[0] == "kill":
                return kill
            if args[0] == "list":
                return listing
            return done()
        err = io.StringIO()
        with mock.patch.object(run, "sbx", side_effect=fake_sbx), \
                mock.patch.object(run, "detached", return_value=done(out=VERDICT)), \
                mock.patch.object(run.time, "sleep"), \
                mock.patch.object(sys, "argv", ["run.py"]), \
                contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(err):
            try:
                rc = run.main()
            except SystemExit as exc:
                rc = exc.code
        return rc, out.getvalue(), err.getvalue()

    def test_failed_listing_is_not_a_confirmation(self):
        rc, out, err = self.main_with(done(1, err="503 gateway is restarting"),
                                      done(1, err="503 gateway is restarting"))
        self.assertNotEqual(rc, 0, "an unreadable sandbox list was taken as 'gone'")
        self.assertNotIn("confirmed gone", out)
        self.assertIn(SID, err)

    def test_confirmed_cleanup_exits_zero(self):
        rc, out, _ = self.main_with(done(), done(out="other-id\n"))
        self.assertEqual(rc, 0)
        self.assertIn("confirmed gone", out)


class Detached(unittest.TestCase):
    def test_unfetchable_output_is_a_failure(self):
        calls = []

        def fake_sbx(*args, timeout=120.0):
            calls.append(args)
            cmd = args[-1]
            if cmd.startswith("if [ -f"):
                return done(out="0\n")       # the step exited 0 ...
            if cmd.startswith("cat "):
                return done(1, err="503")    # ... but its output never arrives
            return done()
        with mock.patch.object(run, "sbx", side_effect=fake_sbx), mock.patch.object(run.time, "sleep"):
            p = run.detached(SID, "grade", "true", 600)
        self.assertNotEqual(p.returncode, 0, "a step whose output was lost reported success")


if __name__ == "__main__":
    unittest.main()
