#!/usr/bin/env python3
"""Unit test for run.py's `sbx` CLI argv (no network, no sandbox).

The acceptance run failed because run.py sent

    sbx exec <id> bash -lc '<line>'

without the `--` separator, so the CLI's argparse read `-lc` as one of
its own options and refused the line ("unrecognized arguments"). This
test builds the exact argv run.py now sends and parses it with the
installed CLI's OWN argparse (sbx.cli.build_parser), so a CLI/run.py
drift in either direction fails here instead of in production.

Run from the demo directory with the real CLI installed:

    pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
    python3 test_run.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import shlex
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load_run():
    spec = importlib.util.spec_from_file_location(
        "nanousd_render_run", os.path.join(HERE, "run.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_cli():
    from sbx import cli  # the installed real CLI, the one `sbx exec` runs

    return cli


# the shell lines run.py sends, including its quoting headaches
SAMPLE_CMDS = [
    "set -eo pipefail; rm -rf sandbox && git clone --depth 1 -b main "
    "https://github.com/agent-next/sandbox sandbox 2>&1 | tail -2",
    "set -o pipefail; cd ~/sandbox/cookbook/nanousd-render && "
    "bash judge/selftest.sh --json /tmp/selftest.json 2>&1 | tail -25",
    "cat /tmp/verdict.json 2>/dev/null | head -60; "
    "echo '--- selftest.json'; cat /tmp/selftest.json 2>/dev/null | head -40",
]


class ExecArgvTest(unittest.TestCase):
    def setUp(self):
        self.run = load_run()
        self.cli = load_cli()

    def argv(self, cmd):
        return self.run.exec_argv("sbx", "sbx-demo-0000", cmd, 1800)

    def test_argv_has_double_dash_before_the_command_words(self):
        argv = self.argv("true")
        self.assertEqual(argv[:2], ["sbx", "exec"])
        self.assertIn("--", argv)
        self.assertEqual(argv[argv.index("--") + 1:], ["bash", "-lc", "true"])

    def test_real_cli_argparse_parses_the_argv(self):
        """The exact argv run.py sends must parse with the real CLI's own
        parser into the sandbox id, timeout and command words we mean."""
        for cmd in SAMPLE_CMDS:
            with self.subTest(cmd=cmd[:40]):
                args = self.cli.build_parser().parse_args(self.argv(cmd)[1:])
                self.assertEqual(args.sandbox_id, "sbx-demo-0000")
                self.assertEqual(args.timeout, 1800.0)
                self.assertEqual(args.command, ["bash", "-lc", cmd])

    def test_the_shell_line_the_cli_would_run(self):
        """cmd_exec() joins the command words with shlex.join; the sandbox
        must receive `bash -lc <line>`, with our line safely quoted."""
        for cmd in SAMPLE_CMDS:
            with self.subTest(cmd=cmd[:40]):
                args = self.cli.build_parser().parse_args(self.argv(cmd)[1:])
                command = args.command
                if command and command[0] == "--":
                    command = command[1:]
                line = command[0] if len(command) == 1 else shlex.join(command)
                self.assertEqual(
                    line,
                    shlex.join(["bash", "-lc", cmd]),
                    "the CLI should run `bash -lc <line>`",
                )

    def test_old_argv_without_double_dash_is_rejected(self):
        """The pre-fix argv (no `--`) is what argparse rejected in the
        acceptance run; it must still be rejected, never silently
        mis-parsed."""
        for cmd in SAMPLE_CMDS:
            with self.subTest(cmd=cmd[:40]):
                broken = ["exec", "sbx-demo-0000", "bash", "-lc", cmd]
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    with self.assertRaises(SystemExit) as raised:
                        self.cli.build_parser().parse_args(broken)
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("unrecognized arguments", err.getvalue())

    def test_exec_step_timeouts_cover_their_steps(self):
        """Every exec_in call site names a timeout; without one the step is
        capped at the CLI's 60 s default, far under the toolchain build."""
        used = [name for name in dir(self.run)
                if name.startswith("TIMEOUT_") and name.endswith("_S")]
        self.assertGreaterEqual(len(used), 5)
        for name in used:
            with self.subTest(timeout=name):
                self.assertGreaterEqual(getattr(self.run, name), 60.0)
        # the pinned build measured ~14-16 min on 2 vCPU
        self.assertGreaterEqual(self.run.TIMEOUT_SETUP_S, 900)


class CliHelpTest(unittest.TestCase):
    def test_sbx_exec_help_documents_the_separator(self):
        """The installed CLI's own help tells the caller to use `--`; if
        that contract moves, run.py's argv must be revisited."""
        proc = subprocess.run(["sbx", "exec", "--help"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--", proc.stdout)
        self.assertIn("one string is run as a shell line", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
