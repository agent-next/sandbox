import json
import sys
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


def test_gateway_errors_drop_the_sdk_class_name(monkeypatch, capsys):
    # The gateway's message is user-facing; "SandboxException: " before it
    # is SDK noise (issue #24). Class declared with __module__ "e2b" like
    # the real SDK exceptions the handler sees.
    SandboxException = type("SandboxException", (Exception,), {"__module__": "e2b"})

    def boom(*a, **k):
        raise SandboxException("404: template 'no-such-template' not found")

    monkeypatch.setattr(FakeSandbox, "create", classmethod(boom))
    assert cli.main(["create", "--template", "no-such-template"]) == 1
    assert capsys.readouterr().err == "sbx: 404: template 'no-such-template' not found\n"


def test_non_sdk_errors_keep_the_class_name(monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("local bug")

    monkeypatch.setattr(FakeSandbox, "create", classmethod(boom))
    assert cli.main(["create"]) == 1
    assert capsys.readouterr().err == "sbx: RuntimeError: local bug\n"
