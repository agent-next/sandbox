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


def test_runner_sandbox_create_uses_real_sdk_serialization(sdk_http, capsys):
    from sbx import runners

    gh = type("GH", (), {"jit": lambda self, *a: "unused"})()
    boot = runners.sandbox_boot(gh, cli._sandbox_cls(), snapshot="snap-1", labels=["self-hosted", "sbx"],
                                group_id=1, job_timeout_s=600, idle_ttl_s=60)
    boot(runners.Slot("sbx-abc", 0.0, retiring=True))  # retired during create: no runner starts
    create, kill = sdk_http
    body = json.loads(create.content)
    assert (create.method, kill.method) == ("POST", "DELETE")
    assert body["templateID"] == "snap-1" and body["timeout"] == 960
    assert body["metadata"] == {"sbx-runner": "sbx-abc"}
    assert body["autoPause"] is False  # on_timeout kill: a runner sandbox never lingers paused
    assert kill.url.path == "/sandboxes/contract-sandbox"


def test_runner_reattach_uses_the_sdk_connect_and_its_error_taxonomy():
    """sandbox_boot reattaches by pid and tells an exited runner (NotFound) from a gone sandbox (Timeout)."""
    import inspect

    import e2b
    from e2b.sandbox_sync.commands.command import Commands

    assert list(inspect.signature(Commands.connect).parameters)[:3] == ["self", "pid", "timeout"]
    assert issubclass(e2b.SandboxNotFoundException, e2b.NotFoundException)
    assert not issubclass(e2b.TimeoutException, e2b.NotFoundException)


def test_failed_job_snapshot_and_debug_restore_use_real_sdk(monkeypatch, tmp_path, capsys):
    from sbx.runner_debug import FailedJobs

    monkeypatch.setenv("E2B_API_KEY", TEST_KEY)
    monkeypatch.setenv("E2B_DOMAIN", "sandbox.example")
    monkeypatch.delenv("E2B_API_URL", raising=False)
    requests = []

    def send(self, request, **kwargs):
        requests.append(request)
        if request.url.path.endswith("/snapshots"):
            return httpx.Response(201, request=request, json={"snapshotID": "snap-failed", "names": []})
        if request.method == "DELETE":
            return httpx.Response(204, request=request)
        return httpx.Response(201, request=request, json={
            "sandboxID": "debug-sandbox", "templateID": "base",
            "clientID": "contract-client", "envdVersion": "0.2.0", "domain": "sandbox.example",
        })

    monkeypatch.setattr(httpx.Client, "send", send)
    sandbox_cls = cli._sandbox_cls()
    sbx = sandbox_cls.create("base")
    store = FailedJobs(tmp_path, sandbox_cls)
    store.keep(sbx, {"id": 7, "html_url": "https://github.com/acme/app/actions/runs/1/job/7",
                     "repo": "acme/app", "head_sha": "a" * 40}, "sbx-test", maximum=5)
    monkeypatch.setattr(cli, "_failed_jobs", lambda *a: store)
    assert cli.main(["runners", "debug", "7"]) == 0
    assert cli.main(["runners", "debug", "--delete", "7"]) == 0
    create, snapshot, restore, delete = requests
    assert snapshot.method == "POST" and snapshot.url.path == "/sandboxes/debug-sandbox/snapshots"
    assert json.loads(restore.content)["templateID"] == "snap-failed"
    assert json.loads(restore.content)["autoPause"] is False
    assert delete.method == "DELETE" and delete.url.path == "/templates/snap-failed"
