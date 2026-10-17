import json

import httpx
import pytest

from sbx import cli


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "k-templates-secret")
    for name in ("SBX_API_KEY", "E2B_DOMAIN", "E2B_API_URL"):
        monkeypatch.delenv(name, raising=False)
    calls = []
    replies = [httpx.Response(200, json=[])]

    def get(url, **kwargs):
        calls.append((url, kwargs))
        reply = replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(cli.httpx, "get", get)
    return calls, replies


def test_templates_prints_cpu_aliases_one_per_line(api, capsys):
    calls, replies = api
    replies[0] = httpx.Response(200, json=[
        {"templateID": "tpl-1", "aliases": ["base", "default"]},
        {"templateID": "tpl-2", "aliases": ["agent-full:standard"]},
        {"templateID": "gpu-default", "aliases": ["gpu"], "accel": {}},
        {"templateID": "tpl-3", "aliases": []},
    ])
    try:
        rc = cli.main(["templates"])
    except SystemExit as exc:
        rc = exc.code
    assert rc == 0, "sbx templates must list CPU aliases"
    output = capsys.readouterr()
    assert output.out == "base\ndefault\nagent-full:standard\ntpl-3\n"
    assert output.err == ""
    assert calls == [("https://api.sbx.agent-next.com/templates", {
        "headers": {"X-API-Key": "k-templates-secret"}, "timeout": 30,
    })]


@pytest.mark.parametrize("api_url, expected", [
    (None, "https://api.custom.example/templates"),
    ("https://override.example/api/", "https://override.example/api/templates"),
])
def test_templates_uses_account_api_base_and_fallback_key(api, monkeypatch, api_url, expected):
    calls, _ = api
    monkeypatch.delenv("E2B_API_KEY")
    monkeypatch.setenv("SBX_API_KEY", "k-fallback-secret")
    monkeypatch.setenv("E2B_DOMAIN", "custom.example")
    if api_url:
        monkeypatch.setenv("E2B_API_URL", api_url)
    assert cli.main(["templates"]) == 0
    assert calls == [(expected, {
        "headers": {"X-API-Key": "k-fallback-secret"}, "timeout": 30,
    })]


def test_templates_json_preserves_raw_list(api, capsys):
    _, replies = api
    payload = [
        {"templateID": "tpl-1", "aliases": ["base"], "public": True},
        {"templateID": "gpu-default", "aliases": ["gpu"], "accel": {}},
    ]
    replies[0] = httpx.Response(200, json=payload)
    assert cli.main(["templates", "--json"]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == payload
    assert output.err == ""


@pytest.mark.parametrize("json_mode", [False, True])
def test_templates_empty_list_succeeds(api, capsys, json_mode):
    assert cli.main(["templates"] + (["--json"] if json_mode else [])) == 0
    output = capsys.readouterr()
    assert output.out == ("[]\n" if json_mode else "")
    assert output.err == ""


def test_templates_requires_key_before_http(api, monkeypatch, capsys):
    monkeypatch.delenv("E2B_API_KEY")
    assert cli.main(["templates"]) == 2
    output = capsys.readouterr()
    assert output.out == "" and "no API key" in output.err
    assert api[0] == []


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_templates_http_errors_are_handled_without_echoing_body(api, capsys, status):
    api[1][0] = httpx.Response(status, text="body includes k-templates-secret")
    assert cli.main(["templates"]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert str(status) in output.err and output.err.startswith("sbx: ")
    assert "k-templates-secret" not in output.err and "body includes" not in output.err


@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize("payload", [None, {}, {"templates": []}, "base", 0])
def test_templates_rejects_non_list_response(api, capsys, payload, json_mode):
    api[1][0] = httpx.Response(200, content=json.dumps(payload))
    assert cli.main(["templates"] + (["--json"] if json_mode else [])) == 2
    output = capsys.readouterr()
    assert output.out == "" and "invalid template list" in output.err


@pytest.mark.parametrize("entry", [
    None, "base", {}, {"aliases": "base"}, {"aliases": [1]},
    {"aliases": [""]}, {"aliases": ["base\nextra"]}, {"aliases": ["base\x1b[31m"]},
    {"aliases": ["base alias"]}, {"templateID": 42},
])
def test_templates_rejects_bad_entries_without_partial_output(api, capsys, entry):
    api[1][0] = httpx.Response(200, json=[{"aliases": ["base"]}, entry])
    assert cli.main(["templates"]) == 2
    output = capsys.readouterr()
    assert output.out == "" and "invalid template" in output.err


def test_templates_rejects_invalid_json(api, capsys):
    api[1][0] = httpx.Response(200, text="<html>bad gateway</html>")
    assert cli.main(["templates"]) == 2
    output = capsys.readouterr()
    assert output.out == "" and "returned invalid JSON" in output.err


@pytest.mark.parametrize("error", [httpx.ConnectError, RuntimeError])
def test_templates_unexpected_errors_exit_one_and_scrub_key(api, capsys, error):
    api[1][0] = error("failure for k-templates-secret")
    assert cli.main(["templates"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert error.__name__ in output.err and "[redacted]" in output.err
    assert "k-templates-secret" not in output.err
