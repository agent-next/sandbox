"""Exercise the installed E2B SDK, substituting only HTTP at the boundary."""
import json

import httpx
import pytest

from sbx import cli

TEST_KEY = "e2b_" + "0" * 40


@pytest.fixture
def sdk_http(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", TEST_KEY)
    monkeypatch.setenv("E2B_DOMAIN", "sandbox.example")
    monkeypatch.delenv("SBX_API_KEY", raising=False)
    monkeypatch.delenv("E2B_API_URL", raising=False)
    monkeypatch.delenv("E2B_DEBUG", raising=False)
    requests = []

    def send(self, request, **kwargs):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(201, request=request, json={
                "sandboxID": "contract-sandbox", "templateID": "base",
                "clientID": "contract-client", "envdVersion": "0.2.0",
                "domain": "sandbox.example",
            })
        if request.method == "DELETE":
            return httpx.Response(204, request=request)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    monkeypatch.setattr(httpx.Client, "send", send)
    return requests


def test_create_uses_real_sdk_serialization(sdk_http, capsys):
    assert cli.main(["create", "--timeout-min", "2", "--template", "base"]) == 0
    assert capsys.readouterr().out == "contract-sandbox\n"
    assert len(sdk_http) == 1
    request = sdk_http[0]
    assert request.method == "POST"
    assert request.url.host == "api.sandbox.example"
    assert request.headers["X-API-Key"] == TEST_KEY
    body = json.loads(request.content)
    assert body["templateID"] == "base"
    assert body["timeout"] == 120
    # The CLI promises a hard lifetime, so SDK create must opt into kill.
    assert body["autoPause"] is False


def test_kill_uses_real_sdk_class_method(sdk_http, capsys):
    assert cli.main(["kill", "contract-sandbox"]) == 0
    assert capsys.readouterr().out == "killed contract-sandbox\n"
    assert len(sdk_http) == 1
    request = sdk_http[0]
    assert request.method == "DELETE"
    assert request.url.host == "api.sandbox.example"
    assert request.url.path == "/sandboxes/contract-sandbox"
    assert request.headers["X-API-Key"] == TEST_KEY
