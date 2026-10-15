"""Unit tests for run.py's cleanup confirmation (stdlib only).

    python3 cookbook/sim-engine-arena/test_run.py
"""
import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run  # noqa: E402


def listing(returncode, stdout):
    return subprocess.CompletedProcess(["sbx", "list"], returncode, stdout, ""), 0.1


class ConfirmGone(unittest.TestCase):
    def test_gone_when_list_succeeds_without_the_id(self):
        with mock.patch.object(run, "run", return_value=listing(0, "other-id\n")):
            run.confirm_gone("sbx-1")

    def test_still_listed_is_not_confirmed(self):
        with mock.patch.object(run, "run", return_value=listing(0, "sbx-1\n")):
            with self.assertRaises(SystemExit) as cm:
                run.confirm_gone("sbx-1")
        self.assertEqual(cm.exception.code, 2)

    def test_failed_list_is_not_confirmation(self):
        # a failed `sbx list` prints nothing: empty output must not read as "gone"
        with mock.patch.object(run, "run", return_value=listing(1, "")):
            with self.assertRaises(SystemExit) as cm:
                run.confirm_gone("sbx-1")
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
