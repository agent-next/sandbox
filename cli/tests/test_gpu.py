import json

import httpx
import pytest

from sbx import cli


class Api:
    """Scripted gateway: maps (method, path) to a list of replies."""

    def __init__(self):
        self.routes = {}
        self.calls = []

    def on(self, method, path, status=200, body=None, headers=None):
        self.routes.setdefault((method, path), []).append((status, body, headers or {}))

    def __call__(self, method, url, headers=None, json=None, timeout=None, **_):
        path = url.split("api.sbx.agent-next.com", 1)[1]
        self.calls.append((method, path, headers, json, timeout))
        replies = self.routes.get((method, path))
        assert replies, f"unscripted {method} {path}"
        status, body, hdrs = replies.pop(0) if len(replies) > 1 else replies[0]
        return httpx.Response(status, json=body, headers=hdrs, request=httpx.Request(method, url))


@pytest.fixture
def api(monkeypatch):
    fake = Api()
    monkeypatch.setattr(httpx, "request", fake)
    monkeypatch.setenv("E2B_API_KEY", "k-secret")
    monkeypatch.delenv("E2B_DOMAIN", raising=False)
    monkeypatch.delenv("E2B_API_URL", raising=False)
    return fake


def test_create_default_body_and_prints_id(api, capsys):
    api.on("POST", "/sandboxes", 201, {"sandboxID": "gl-1a-1", "phase": "resident"})
    assert cli.main(["gpu", "create"]) == 0
    assert capsys.readouterr().out == "gl-1a-1\n"
    method, path, headers, body, _ = api.calls[0]
    assert headers["X-API-Key"] == "k-secret"
    assert body == {"accel": {}}


def test_create_options(api, capsys):
    api.on("POST", "/sandboxes", 201, {"sandboxID": "gl-1a-1"})
    assert cli.main(["gpu", "create", "--vram", "4", "--template", "mujoco", "--class", "nvidia.5090"]) == 0
    assert api.calls[0][3] == {"accel": {"vram_gb": 4.0, "template": "mujoco", "class": "nvidia.5090"}}


def test_create_json(api, capsys):
    reply = {"sandboxID": "gl-1a-1", "phase": "resident", "accel": {"vram_gb": 1.0}}
    api.on("POST", "/sandboxes", 201, reply)
    assert cli.main(["gpu", "create", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == reply


@pytest.mark.parametrize("bad", ["nan", "0", "-1", "inf"])
def test_create_rejects_bad_vram(api, bad, capsys):
    assert cli.main(["gpu", "create", "--vram", bad]) == 2
    assert "--vram" in capsys.readouterr().err
    assert api.calls == []


def test_create_rejects_unsafe_lease_id(api, capsys):
    api.on("POST", "/sandboxes", 201, {"sandboxID": "../x"})
    assert cli.main(["gpu", "create"]) == 2
    assert "invalid lease id" in capsys.readouterr().err


EXEC_OK = {
    "sandboxID": "gl-1a-1",
    "result": {"ok": True, "report": {"sum": 3}, "stdout": "hi\n", "stderr": "warn\n"},
    "meters": {"billed_s": 1.5},
}


def test_exec_inline_prints_stdout_and_sends_timeout(api, capsys):
    api.on("POST", "/sandboxes/gl-1a-1/exec", 200, EXEC_OK)
    assert cli.main(["gpu", "exec", "gl-1a-1", "-c", "print('hi')", "--timeout", "30"]) == 0
    out = capsys.readouterr()
    assert out.out == "hi\n" and out.err == "warn\n"
    assert api.calls[0][3] == {"code": "print('hi')", "timeout_s": 30.0}
    assert api.calls[0][4] > 30


def test_exec_code_file(api, tmp_path):
    src = tmp_path / "job.py"
    src.write_text("report['a'] = 1\n")
    api.on("POST", "/sandboxes/gl-1a-1/exec", 200, EXEC_OK)
    assert cli.main(["gpu", "exec", "gl-1a-1", "--code", str(src)]) == 0
    assert api.calls[0][3]["code"] == "report['a'] = 1\n"
    assert api.calls[0][3]["timeout_s"] == 120


def test_exec_json_prints_reply(api, capsys):
    api.on("POST", "/sandboxes/gl-1a-1/exec", 200, EXEC_OK)
    assert cli.main(["gpu", "exec", "gl-1a-1", "-c", "x", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == EXEC_OK


def test_exec_not_ok_is_nonzero(api, capsys):
    bad = {"result": {"ok": False, "stdout": "partial\n"}}
    api.on("POST", "/sandboxes/gl-1a-1/exec", 200, bad)
    assert cli.main(["gpu", "exec", "gl-1a-1", "-c", "x"]) == 1
    assert "failed" in capsys.readouterr().err


def test_exec_job_exception_409_shows_message(api, capsys):
    api.on("POST", "/sandboxes/gl-1a-1/exec", 409,
           {"code": 409, "message": "lease gl-1a-1 job 3 failed: ValueError: boom"})
    assert cli.main(["gpu", "exec", "gl-1a-1", "-c", "x"]) == 1
    err = capsys.readouterr().err
    assert "ValueError: boom" in err and err.count("\n") == 1


def test_exec_needs_code_source(api, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["gpu", "exec", "gl-1a-1"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit):
        cli.main(["gpu", "exec", "gl-1a-1", "-c", "x", "--code", "f.py"])


def test_exec_missing_file(api, capsys):
    assert cli.main(["gpu", "exec", "gl-1a-1", "--code", "/nonexistent/job.py"]) == 2
    assert "job.py" in capsys.readouterr().err


@pytest.mark.parametrize("bad", ["0", "3601", "nan"])
def test_exec_timeout_bounds(api, bad, capsys):
    assert cli.main(["gpu", "exec", "gl-1a-1", "-c", "x", "--timeout", bad]) == 2
    assert "--timeout" in capsys.readouterr().err


def test_pause_and_resume(api, capsys):
    api.on("POST", "/sandboxes/gl-1a-1/pause", 204)
    api.on("POST", "/sandboxes/gl-1a-1/resume", 200, {"sandboxID": "gl-1a-1", "phase": "resident"})
    assert cli.main(["gpu", "pause", "gl-1a-1"]) == 0
    assert capsys.readouterr().out == "paused gl-1a-1\n"
    assert cli.main(["gpu", "resume", "gl-1a-1"]) == 0
    assert capsys.readouterr().out == "resumed gl-1a-1\n"


def test_pause_json(api, capsys):
    api.on("POST", "/sandboxes/gl-1a-1/pause", 200, {"phase": "suspended"})
    assert cli.main(["gpu", "pause", "gl-1a-1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"phase": "suspended"}


def test_pause_json_empty_reply(api, capsys):
    api.on("POST", "/sandboxes/gl-1a-1/pause", 204)
    assert cli.main(["gpu", "pause", "gl-1a-1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"sandboxID": "gl-1a-1", "ok": True}


def test_kill_deletes_then_confirms_404(api, capsys):
    api.on("DELETE", "/sandboxes/gl-1a-1", 200, {"meters": {"billed_s": 2}})
    api.on("GET", "/sandboxes/gl-1a-1", 404, {"code": 404, "message": "nope"})
    assert cli.main(["gpu", "kill", "gl-1a-1"]) == 0
    assert capsys.readouterr().out == "killed gl-1a-1\n"
    assert [c[0] for c in api.calls] == ["DELETE", "GET"]


def test_kill_accepts_dead_phase(api, capsys):
    api.on("DELETE", "/sandboxes/gl-1a-1", 204)
    api.on("GET", "/sandboxes/gl-1a-1", 200, {"phase": "dead"})
    assert cli.main(["gpu", "kill", "gl-1a-1"]) == 0


def test_kill_unconfirmed_is_an_error(api, capsys):
    api.on("DELETE", "/sandboxes/gl-1a-1", 204)
    api.on("GET", "/sandboxes/gl-1a-1", 200, {"phase": "resident"})
    assert cli.main(["gpu", "kill", "gl-1a-1"]) == 2
    assert "not confirmed" in capsys.readouterr().err


def test_kill_already_gone_is_not_an_error(api, capsys):
    api.on("DELETE", "/sandboxes/gl-1a-1", 404, {"code": 404, "message": "x"})
    assert cli.main(["gpu", "kill", "gl-1a-1"]) == 0
    assert "already gone" in capsys.readouterr().err


def test_kill_json(api, capsys):
    api.on("DELETE", "/sandboxes/gl-1a-1", 200, {"meters": {"billed_s": 2}})
    api.on("GET", "/sandboxes/gl-1a-1", 404)
    assert cli.main(["gpu", "kill", "gl-1a-1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "sandboxID": "gl-1a-1", "killed": True, "meters": {"billed_s": 2},
    }


def test_templates_lists_names(api, capsys):
    api.on("GET", "/gpu/templates", 200, {"templates": [
        {"name": "default", "description": "plain CUDA"}, {"name": "mujoco"}]})
    assert cli.main(["gpu", "templates"]) == 0
    assert capsys.readouterr().out.splitlines() == ["default\tplain CUDA", "mujoco"]


def test_templates_accepts_bare_list_and_json(api, capsys):
    api.on("GET", "/gpu/templates", 200, ["default", "mujoco"])
    assert cli.main(["gpu", "templates"]) == 0
    assert capsys.readouterr().out.splitlines() == ["default", "mujoco"]
    assert cli.main(["gpu", "templates", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == ["default", "mujoco"]


INFO = {
    "sandboxID": "gl-1a-1", "templateID": "mujoco", "phase": "suspended",
    "accel": {"vram_gb": 4.0},
    "meters": {"billed_s": 12.5, "running_s": 20.0, "suspend_mode": "checkpoint"},
}


def test_info_shows_meters(api, capsys):
    api.on("GET", "/sandboxes/gl-1a-1", 200, INFO)
    assert cli.main(["gpu", "info", "gl-1a-1"]) == 0
    out = capsys.readouterr().out
    for want in ("gl-1a-1", "suspended", "mujoco", "vram_gb", "4.0", "billed_s", "12.5", "running_s"):
        assert want in out


def test_info_json(api, capsys):
    api.on("GET", "/sandboxes/gl-1a-1", 200, INFO)
    assert cli.main(["gpu", "info", "gl-1a-1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == INFO


@pytest.mark.parametrize("status,hint", [
    (401, "rejected the API key"),
    (402, "no GPU credit"),
    (403, "no GPU access"),
    (404, "not found"),
    (409, "conflict"),
    (429, "busy"),
    (503, "capacity"),
])
def test_error_mapping_one_line_with_hint(api, capsys, status, hint):
    api.on("POST", "/sandboxes", status, {"code": status, "message": "server says so"},
           headers={"Retry-After": "7"} if status in (429, 503) else None)
    assert cli.main(["gpu", "create"]) == 2
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and err.startswith("sbx: ")
    assert hint in err and str(status) in err and "server says so" in err
    if status in (429, 503):
        assert "retry in 7s" in err


def test_error_on_every_verb(api, capsys):
    api.on("POST", "/sandboxes/gl-1a-1/pause", 409, {"message": "suspend only at exec boundaries"})
    assert cli.main(["gpu", "pause", "gl-1a-1"]) == 2
    assert "exec boundaries" in capsys.readouterr().err
    api.on("GET", "/gpu/templates", 403, {"message": "tier"})
    assert cli.main(["gpu", "templates"]) == 2
    api.on("GET", "/sandboxes/gl-1a-1", 404, {"message": "nope"})
    assert cli.main(["gpu", "info", "gl-1a-1"]) == 2


def test_error_without_json_body(api, monkeypatch, capsys):
    monkeypatch.setattr(httpx, "request", lambda *a, **k: httpx.Response(
        500, text="<html>oops</html>", request=httpx.Request("GET", "https://x")))
    assert cli.main(["gpu", "info", "gl-1a-1"]) == 2
    assert "HTTP 500" in capsys.readouterr().err


def test_network_error_is_one_line(monkeypatch, api, capsys):
    def boom(*a, **k):
        raise httpx.ConnectError("no route")
    monkeypatch.setattr(httpx, "request", boom)
    assert cli.main(["gpu", "info", "gl-1a-1"]) == 2
    assert "unreachable" in capsys.readouterr().err


def test_server_message_never_leaks_key(api, capsys):
    api.on("POST", "/sandboxes", 409, {"message": "bad key k-secret"})
    cli.main(["gpu", "create"])
    err = capsys.readouterr().err
    assert "k-secret" not in err and "[redacted]" in err


def test_lease_id_is_validated_before_any_request(api, capsys):
    assert cli.main(["gpu", "info", "../etc"]) == 2
    assert "invalid lease id" in capsys.readouterr().err
    assert api.calls == []


def test_missing_key(monkeypatch, api, capsys):
    monkeypatch.delenv("E2B_API_KEY")
    monkeypatch.delenv("SBX_API_KEY", raising=False)
    assert cli.main(["gpu", "templates"]) == 2
    assert "no API key" in capsys.readouterr().err


def test_api_url_override(api, monkeypatch):
    monkeypatch.setenv("E2B_API_URL", "https://api.sbx.agent-next.com/")
    api.on("GET", "/gpu/templates", 200, [])
    assert cli.main(["gpu", "templates"]) == 0
