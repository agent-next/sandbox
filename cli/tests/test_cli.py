import json
import os
import signal
import subprocess
import sys
import time
import types

import pytest

from sbx import cli


class FakeResult:
    def __init__(self, stdout="", stderr="", exit_code=0):
        self.stdout, self.stderr, self.exit_code = stdout, stderr, exit_code


class FakeExit(Exception):
    def __init__(self, stdout, stderr, exit_code):
        super().__init__("exit")
        self.stdout, self.stderr, self.exit_code = stdout, stderr, exit_code


class FakeTimeout(Exception):
    pass


class FakeNotFound(Exception):
    pass


class FakeSandbox:
    calls = []
    killed = True

    def __init__(self, sid="sbx-1"):
        self.sandbox_id = sid
        self.commands = self

    @classmethod
    def create(cls, template=None, timeout=None):
        cls.calls.append(("create", template, timeout))
        return cls()

    @classmethod
    def connect(cls, sid):
        cls.calls.append(("connect", sid))
        return cls(sid)

    @classmethod
    def kill(cls, sid):
        cls.calls.append(("kill", sid))
        return cls.killed

    def run(self, line, timeout=None):
        FakeSandbox.calls.append(("run", line, timeout))
        if line == "false":
            raise FakeExit("", "boom\n", 1)
        return FakeResult("hello\n", "", 0)


@pytest.fixture(autouse=True)
def fake_e2b(monkeypatch):
    FakeSandbox.calls = []
    FakeSandbox.killed = True
    mod = types.ModuleType("e2b")
    mod.Sandbox = FakeSandbox
    mod.CommandExitException = FakeExit
    mod.TimeoutException = FakeTimeout
    mod.SandboxNotFoundException = FakeNotFound
    monkeypatch.setitem(sys.modules, "e2b", mod)
    monkeypatch.setenv("E2B_API_KEY", "k")
    monkeypatch.delenv("E2B_DOMAIN", raising=False)
    monkeypatch.delenv("SBX_API_KEY", raising=False)
    monkeypatch.delenv("E2B_API_URL", raising=False)


def test_create_prints_id_and_converts_minutes(capsys):
    assert cli.main(["create", "--timeout-min", "2"]) == 0
    assert capsys.readouterr().out == "sbx-1\n"
    assert FakeSandbox.calls == [("create", None, 120)]


def test_exec_passes_exit_code_and_streams(capsys):
    assert cli.main(["exec", "sbx-1", "echo hello"]) == 0
    assert capsys.readouterr().out == "hello\n"
    assert cli.main(["exec", "sbx-1", "--", "false"]) == 1
    assert capsys.readouterr().err == "boom\n"


def test_exec_joins_argv_with_quoting():
    cli.main(["exec", "sbx-1", "--", "echo", "a b"])
    assert ("run", "echo 'a b'", 60) in FakeSandbox.calls


def test_kill_gone_is_not_an_error(capsys):
    FakeSandbox.killed = False
    assert cli.main(["kill", "sbx-1"]) == 0
    assert "already gone" in capsys.readouterr().err


def test_missing_key_is_a_usage_error(monkeypatch, capsys):
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    monkeypatch.delenv("SBX_API_KEY", raising=False)
    assert cli.main(["create"]) == 2
    assert "no API key" in capsys.readouterr().err


def test_sbx_api_key_is_accepted(monkeypatch):
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    monkeypatch.setenv("SBX_API_KEY", "k2")
    assert cli.main(["create"]) == 0
    assert cli.os.environ["E2B_DOMAIN"] == "sbx.agent-next.com"


def test_exec_options_before_command_are_parsed(capsys):
    assert cli.main(["exec", "sbx-1", "--timeout", "10", "echo hello"]) == 0
    assert ("run", "echo hello", 10.0) in FakeSandbox.calls


@pytest.mark.parametrize("bad", ["nan", "inf", "-1", "0"])
def test_invalid_timeouts_are_usage_errors(bad, capsys):
    assert cli.main(["create", "--timeout-min", bad]) == 2
    assert cli.main(["exec", "sbx-1", "--timeout", bad, "true"]) == 2
    assert "positive number" in capsys.readouterr().err


def test_tiny_lifetime_rounds_up_to_one_second():
    cli.main(["create", "--timeout-min", "0.001"])
    assert FakeSandbox.calls == [("create", None, 1)]


def test_errors_never_print_the_key(monkeypatch, capsys):
    secret = "k-very-secret-value"
    monkeypatch.setenv("E2B_API_KEY", secret)

    def boom(*a, **k):
        raise RuntimeError(f"auth failed for {secret}")

    monkeypatch.setattr(FakeSandbox, "create", classmethod(boom))
    assert cli.main(["create"]) == 1
    err = capsys.readouterr().err
    assert secret not in err and "[redacted]" in err


def test_list_error_shows_status_only(monkeypatch, capsys):
    secret = "k-very-secret-value"
    monkeypatch.setenv("E2B_API_KEY", secret)

    class Resp:
        status_code = 500
        text = f"echo {secret}"

    monkeypatch.setattr(cli.httpx, "get", lambda *a, **k: Resp())
    assert cli.main(["list"]) == 2
    err = capsys.readouterr().err
    assert secret not in err and "HTTP 500" in err


@pytest.mark.parametrize("name", ["E2B_API_KEY", "SBX_API_KEY"])
def test_parser_errors_and_command_output_are_scrubbed(name, monkeypatch, capsys):
    secret = "k-very-secret-value"
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    monkeypatch.setenv(name, secret)
    with pytest.raises(SystemExit) as exc:
        cli.main(["create", "--timeout-min", secret])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert secret not in err and "[redacted]" in err

    monkeypatch.setattr(FakeSandbox, "run", lambda self, line, timeout=None: FakeResult(f"{secret}\n", f"{secret}\n", 0))
    assert cli.main(["exec", "sbx-1", "echo hi"]) == 0
    out = capsys.readouterr()
    assert secret not in out.out + out.err


def test_exec_separator_form_keeps_command_options():
    cli.main(["exec", "sbx-1", "--timeout", "30", "--", "ls", "-l", "/tmp"])
    assert ("run", "ls -l /tmp", 30.0) in FakeSandbox.calls


def test_exec_timeout_names_the_flag_and_value(monkeypatch, capsys):
    def slow(self, line, timeout=None):
        raise FakeTimeout(
            "Request timed out: This error is likely due to exceeding 'timeout' "
            "or 'request_timeout' when making the request."
        )

    monkeypatch.setattr(FakeSandbox, "run", slow)
    assert cli.main(["exec", "sbx-1", "--timeout", "2", "sleep 10"]) == 1
    err = capsys.readouterr().err
    assert "--timeout 2" in err
    assert "still be running" in err
    # The old text addressed SDK callers, not CLI users; the raw SDK text and
    # the command line (which may hold secrets) must not be echoed.
    assert "request_timeout" not in err
    assert "sleep" not in err


def test_exec_missing_sandbox_names_the_id_without_sdk_wording(monkeypatch, capsys):
    # A realistic key length, so _scrub's redaction does not collide with
    # ordinary words in the message (the autouse fixture uses "k").
    monkeypatch.setenv("E2B_API_KEY", "k-very-secret-value")

    def missing(cls, sid):
        raise FakeNotFound(f"Paused sandbox {sid} not found")

    monkeypatch.setattr(FakeSandbox, "connect", classmethod(missing))
    assert cli.main(["exec", "sbx-gone", "echo hi"]) == 1
    err = capsys.readouterr().err
    assert "sbx-gone" in err
    assert "not found" in err
    assert "killed, expired, or the id is wrong" in err
    # The SDK claims the sandbox was "Paused" even for ids that never existed.
    assert "Paused" not in err
    assert "echo" not in err


@pytest.mark.parametrize("name", ["E2B_API_KEY", "SBX_API_KEY"])
def test_every_output_path_is_scrubbed(name, monkeypatch, capsys):
    secret = "k-very-secret-value"
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    monkeypatch.setenv(name, secret)

    FakeSandbox.killed = True
    cli.main(["kill", secret])
    FakeSandbox.killed = False
    cli.main(["kill", secret])
    monkeypatch.setattr(FakeSandbox, "create", classmethod(lambda cls, t=None, timeout=None: cls(secret)))
    cli.main(["create"])

    class Resp:
        status_code = 200

        def json(self):
            return [{"sandboxID": secret, "alias": secret, "startedAt": secret}]

    monkeypatch.setattr(cli.httpx, "get", lambda *a, **k: Resp())
    cli.main(["list"])
    out = capsys.readouterr()
    assert secret not in out.out + out.err
    assert "[redacted]" in out.out


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("items", [[], [
    {"sandboxID": "sbx-1", "alias": "base", "startedAt": "2026-10-12T00:00:00Z"},
    {"sandbox_id": "sbx-2", "templateID": "agent-full"},
]])
def test_list_accepts_empty_and_populated_inventory(wrapped, items, monkeypatch, capsys):
    payload = {"sandboxes": items} if wrapped else items
    monkeypatch.setattr(cli.httpx, "get", lambda *a, **kw: cli.httpx.Response(200, json=payload))
    assert cli.main(["list"]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert output.out == ("sbx-1\tbase\t2026-10-12T00:00:00Z\nsbx-2\tagent-full\t-\n" if items else "")


@pytest.mark.parametrize("payload", [
    {}, {"message": "upstream unavailable"}, {"sandboxes": None},
    {"sandboxes": {}}, None, "not a list", 0,
    [None], ["sbx-1"], [{}], [{"sandboxID": 123}], [{"sandboxID": " "}],
    [{"sandboxID": "sbx-1\nINJECTED\trow"}], [{"sandboxID": "sbx-1\x1b[31m"}],
    [{"sandboxID": "sbx 1"}], [{"sandboxID": "sbx-1", "alias": {"a": 1}}],
    [{"sandboxID": "sbx-1", "alias": "base\trow"}],
    [{"sandboxID": "sbx-1", "startedAt": "now\nrow"}],
    [{"sandboxID": "sbx-1", "alias": []}], [{"sandboxID": "sbx-1", "templateID": False}],
    [{"sandboxID": "sbx-1", "startedAt": 0}],
    [{"sandboxID": "sbx-valid"}, {"message": "bad row"}],
])
def test_list_rejects_invalid_inventory_without_partial_output(payload, monkeypatch, capsys):
    monkeypatch.setattr(cli.httpx, "get", lambda *a, **kw: cli.httpx.Response(200, content=json.dumps(payload)))
    assert cli.main(["list"]) != 0
    output = capsys.readouterr()
    assert output.out == ""
    assert "GET /sandboxes returned" in output.err


def test_list_rejects_non_json_without_echoing_body(monkeypatch, capsys):
    monkeypatch.setattr(cli.httpx, "get", lambda *a, **kw: cli.httpx.Response(200, content="<html>upstream failure</html>"))
    assert cli.main(["list"]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "sbx: GET /sandboxes returned invalid JSON\n"


RESTART_503 = '503 {"error":"gateway is restarting","code":"restarting","retry_after_s":5}'


class Restarting(Exception):
    pass


def test_kill_retries_while_the_gateway_restarts(monkeypatch, capsys):
    # a realistic key length, so _scrub's redaction does not collide with
    # ordinary words in the output (the autouse fixture uses "k")
    monkeypatch.setenv("E2B_API_KEY", "k-very-secret-value")
    calls = []

    def flaky(cls, sid):
        calls.append(sid)
        if len(calls) < 3:
            raise Restarting(RESTART_503)
        return True

    sleeps = []
    monkeypatch.setattr(FakeSandbox, "kill", classmethod(flaky))
    monkeypatch.setattr(time, "sleep", sleeps.append)
    assert cli.main(["kill", "sbx-1"]) == 0
    assert calls == ["sbx-1"] * 3
    assert sleeps == [5, 5]
    output = capsys.readouterr()
    assert output.out == "killed sbx-1\n"


def test_kill_caps_the_retry_wait(monkeypatch):
    calls = []

    def flaky(cls, sid):
        calls.append(sid)
        if len(calls) < 2:
            raise Restarting('503 {"error":"gateway is restarting","code":"restarting","retry_after_s":999}')
        return True

    sleeps = []
    monkeypatch.setattr(FakeSandbox, "kill", classmethod(flaky))
    monkeypatch.setattr(time, "sleep", sleeps.append)
    assert cli.main(["kill", "sbx-1"]) == 0
    assert sleeps == [30]


def test_kill_gives_up_after_bounded_retries(monkeypatch, capsys):
    calls = []

    def down(cls, sid):
        calls.append(sid)
        raise Restarting(RESTART_503)

    monkeypatch.setattr(FakeSandbox, "kill", classmethod(down))
    monkeypatch.setattr(time, "sleep", lambda s: None)
    assert cli.main(["kill", "sbx-1"]) == 1
    assert calls == ["sbx-1"] * 3
    assert "503" in capsys.readouterr().err


def test_kill_does_not_retry_other_failures(monkeypatch):
    calls = []

    def down(cls, sid):
        calls.append(sid)
        raise Restarting('500 {"error":"boom"}')

    monkeypatch.setattr(FakeSandbox, "kill", classmethod(down))
    monkeypatch.setattr(time, "sleep", lambda s: None)
    assert cli.main(["kill", "sbx-1"]) == 1
    assert calls == ["sbx-1"]


def test_create_and_connect_retry_the_same_shape(monkeypatch):
    create_calls = []

    def flaky_create(cls, template=None, timeout=None):
        create_calls.append(template)
        if len(create_calls) == 1:
            raise Restarting(RESTART_503)
        return cls()

    connect_calls = []

    def flaky_connect(cls, sid):
        connect_calls.append(sid)
        if len(connect_calls) == 1:
            raise Restarting(RESTART_503)
        return cls(sid)

    monkeypatch.setattr(FakeSandbox, "create", classmethod(flaky_create))
    monkeypatch.setattr(FakeSandbox, "connect", classmethod(flaky_connect))
    monkeypatch.setattr(time, "sleep", lambda s: None)
    assert cli.main(["create"]) == 0
    assert create_calls == [None, None]
    assert cli.main(["exec", "sbx-1", "true"]) == 0
    assert connect_calls == ["sbx-1", "sbx-1"]


def test_closed_pipe_exits_quietly(tmp_path):
    """`sbx exec ID cmd | head -3` must exit quietly, not dump BrokenPipeError."""
    driver = tmp_path / "driver.py"
    # a realistic key, so _scrub does not mangle the word 'BrokenPipeError'
    driver.write_text(
        "import sys, types\n"
        "mod = types.ModuleType('e2b')\n"
        "mod.CommandExitException = type('CommandExitException', (Exception,), {})\n"
        "mod.SandboxNotFoundException = type('SandboxNotFoundException', (Exception,), {})\n"
        "mod.TimeoutException = type('TimeoutException', (Exception,), {})\n"
        "class Sandbox:\n"
        "    @classmethod\n"
        "    def connect(cls, sid):\n"
        "        box = cls()\n"
        "        box.commands = box\n"
        "        return box\n"
        "    def run(self, line, timeout=None):\n"
        "        return types.SimpleNamespace(stdout='y\\n' * 200000, stderr='', exit_code=0)\n"
        "mod.Sandbox = Sandbox\n"
        "sys.modules['e2b'] = mod\n"
        "import os\n"
        "os.environ['E2B_API_KEY'] = 'k-very-secret-value'\n"
        "from sbx.cli import main\n"
        "sys.exit(main(['exec', 'sbx-1', 'true']))\n"
    )
    read_fd, write_fd = os.pipe()
    proc = subprocess.Popen(
        [sys.executable, str(driver)], stdout=write_fd, stderr=subprocess.PIPE
    )
    os.close(write_fd)
    with os.fdopen(read_fd, "rb") as reader:
        for _ in range(3):
            reader.readline()
    _, err = proc.communicate(timeout=30)
    assert b"Traceback" not in err
    assert b"BrokenPipeError" not in err
    assert b"Exception ignored" not in err
    assert proc.returncode in (-signal.SIGPIPE, 1, 141)


def test_main_keeps_sigpipe_handler():
    """SIG_DFL would kill the process on a closed pipe before `finally` cleanup
    runs (runners.build_image kills its bake sandbox there)."""
    if not hasattr(signal, "SIGPIPE"):
        pytest.skip("no SIGPIPE on this platform")
    before = signal.getsignal(signal.SIGPIPE)
    with pytest.raises(SystemExit):
        cli.main(["list", "--help"])
    assert signal.getsignal(signal.SIGPIPE) == before
