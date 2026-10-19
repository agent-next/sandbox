import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("demo_run", Path(__file__).resolve().parents[1]/"run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def done(rc=0, out="", err=""):
    return subprocess.CompletedProcess("sbx", rc, out, err)


class Cleanup(unittest.TestCase):
    def call_main(self, listing):
        sid = "test-sandbox"

        def fake(*args, **kwargs):
            return done(out=sid) if args[0] == "create" else listing if args[0] == "list" else done()
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(run, "sbx", side_effect=fake), \
             mock.patch.object(run, "detached", return_value=done(out=json.dumps({"passed": True, "gates": {}}))), \
             mock.patch.object(run.shutil, "which", return_value="/bin/sbx"), \
             mock.patch.dict(run.os.environ, {"SBX_API_KEY": "test"}), \
             mock.patch.object(run.time, "sleep"), \
             mock.patch.object(sys, "argv", ["run.py"]), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = run.main()
        return rc, out.getvalue(), err.getvalue()

    def test_failed_list_is_not_cleanup(self):
        rc, out, err = self.call_main(done(1, err="503"))
        self.assertNotEqual(rc, 0)
        self.assertNotIn("confirmed gone:", out)
        self.assertIn("test-sandbox", err)

    def test_list_still_contains_id(self):
        self.assertNotEqual(self.call_main(done(out="test-sandbox"))[0], 0)

    def test_confirmed_cleanup(self):
        self.assertEqual(self.call_main(done(out="other-sandbox"))[0], 0)

    def test_lost_step_log_is_failure(self):
        def fake(*args, **kwargs):
            if args[-1].startswith("if ["):
                return done(out="0")
            if args[-1].startswith("cat "):
                return done(1, err="503")
            return done()
        with mock.patch.object(run, "sbx", side_effect=fake), mock.patch.object(run.time, "sleep"):
            self.assertNotEqual(run.detached("test", "grade", "true", 60).returncode, 0)
