"""A sandbox's first lookup can lag its create (#23).

On the live service (2026-10-14, issue #23) the first sandbox_exec after a
successful sandbox_create answered NOT_FOUND — annotated retryable: false —
while sandboxes_list showed the same sandbox running and an immediate retry
succeeded. The MCP server is hosted outside this repo, but the `sbx` CLI
drives the same connect-by-id call, so exec and cp must not report a
sandbox the service still runs as gone, and the README must say they retry.
"""

import enum
import re
import sys
import time
import types
from pathlib import Path
from unittest.mock import Mock

import pytest

from sbx import cli

REPO = Path(__file__).resolve().parents[2]
README = REPO / "cli/README.md"


class FakeResult:
    def __init__(self, stdout="", stderr="", exit_code=0):
        self.stdout, self.stderr, self.exit_code = stdout, stderr, exit_code


class FakeExit(Exception):
    pass


class NotFoundException(Exception):
    pass


class SandboxNotFoundException(NotFoundException):
    """What e2b raises when connect-by-id answers 404 (a NotFoundException,
    as the installed SDK's taxonomy has it)."""


class InvalidArgument(Exception):
    pass


class TimeoutException(Exception):
    pass


class FileType(enum.Enum):
    FILE = "file"
    DIR = "dir"


class FakeSandbox:
    # connect answers not found for the first `misses` calls, like a sandbox
    # whose registration lags behind its create
    misses = 2
    calls = []
    instance = None

    def __init__(self, sid="sbx-new"):
        self.sandbox_id = sid
        self.commands = self
        self.files = Mock()
        self.files.get_info.return_value.type = FileType.FILE
        FakeSandbox.instance = self

    @classmethod
    def connect(cls, sid):
        cls.calls.append(sid)
        if len(cls.calls) <= cls.misses:
            raise SandboxNotFoundException(f"Paused sandbox {sid} not found")
        return cls(sid)

    @classmethod
    def kill(cls, sid):
        return True

    def run(self, line, timeout=None):
        return FakeResult("hello\n", "", 0)


@pytest.fixture
def lagging_e2b(monkeypatch):
    FakeSandbox.calls = []
    FakeSandbox.misses = 2
    FakeSandbox.instance = None
    mod = types.ModuleType("e2b")
    mod.Sandbox = FakeSandbox
    mod.CommandExitException = FakeExit
    mod.SandboxNotFoundException = SandboxNotFoundException
    mod.NotFoundException = NotFoundException
    mod.InvalidArgumentException = InvalidArgument
    mod.TimeoutException = TimeoutException
    mod.FileType = FileType
    monkeypatch.setitem(sys.modules, "e2b", mod)
    monkeypatch.setenv("E2B_API_KEY", "k")
    monkeypatch.delenv("SBX_API_KEY", raising=False)
    monkeypatch.delenv("E2B_DOMAIN", raising=False)
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    return sleeps


def test_exec_retries_a_not_found_that_lags_the_create(lagging_e2b, capsys):
    assert cli.main(["exec", "sbx-new", "echo hello"]) == 0
    assert FakeSandbox.calls == ["sbx-new"] * 3
    assert capsys.readouterr().out == "hello\n"
    assert lagging_e2b  # it waited between attempts instead of polling hot


def test_exec_bounds_the_not_found_retries(lagging_e2b, capsys):
    FakeSandbox.misses = 99
    assert cli.main(["exec", "sbx-gone", "echo hi"]) == 1
    assert FakeSandbox.calls == ["sbx-gone"] * 3  # bounded, like the 503 restart retry
    err = capsys.readouterr().err
    assert "sbx-gone" in err and "not found" in err


def test_cp_retries_a_not_found_that_lags_the_create(lagging_e2b, tmp_path):
    local = tmp_path / "local.bin"
    local.write_bytes(b"data")

    assert cli.main(["cp", str(local), "sbx-new:/tmp/remote.bin"]) == 0

    assert FakeSandbox.calls == ["sbx-new"] * 3
    FakeSandbox.instance.files.write.assert_called_once_with(
        "/tmp/remote.bin", b"data", request_timeout=600
    )


def test_readme_says_exec_retries_a_just_created_sandbox():
    rows = [
        line for line in README.read_text(encoding="utf-8").splitlines()
        if line.startswith("| `sbx exec ID")
    ]
    assert rows and "retried" in rows[0], (
        "cli/README.md's exec row must say a sandbox created moments ago is "
        "retried before exec reports it gone (issue #23: the first lookup "
        "after create can answer not found for a running sandbox)"
    )
