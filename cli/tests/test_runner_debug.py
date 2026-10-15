import json
import threading
from types import SimpleNamespace

import httpx
import pytest

from sbx import cli, runners
from sbx.runner_debug import FailedJobs


def job(jid=123, conclusion="failure"):
    return {
        "id": jid, "html_url": f"https://github.com/acme/app/actions/runs/9/job/{jid}",
        "repo": "acme/app", "head_sha": "a" * 40, "conclusion": conclusion,
        "runner_name": "sbx-test", "status": "completed",
    }


class Sandbox:
    made = []
    deleted = []
    error = None

    @classmethod
    def create(cls, template, **kwargs):
        sbx = cls()
        sbx.sandbox_id = "debug-1"
        sbx.files = SimpleNamespace(write=lambda *a: None)
        sbx.commands = SimpleNamespace(run=sbx.run)
        sbx.template, sbx.kwargs = template, kwargs
        sbx.killed, sbx.snapshots, sbx.executed = 0, 0, []
        cls.made.append(sbx)
        return sbx

    def run(self, command, **kwargs):
        self.executed.append((command, kwargs))
        return SimpleNamespace(pid=42, wait=lambda: SimpleNamespace(exit_code=0),
                               stdout="preserved\n", stderr="", exit_code=0)

    def create_snapshot(self):
        self.snapshots += 1
        assert self.killed == 0
        if self.error:
            raise self.error
        return SimpleNamespace(snapshot_id=f"snap-{len(self.made)}")

    @classmethod
    def delete_snapshot(cls, sid):
        cls.deleted.append(sid)
        return True

    def kill(self):
        self.killed += 1


@pytest.fixture
def setup(tmp_path, monkeypatch):
    Sandbox.made, Sandbox.deleted, Sandbox.error = [], [], None
    monkeypatch.setenv("E2B_API_KEY", "<FAKE>")
    monkeypatch.setattr(cli, "_sandbox_cls", lambda: Sandbox)
    return FailedJobs(tmp_path, Sandbox)


def boot(store, conclusion="failure", maximum=5):
    gh = SimpleNamespace(jit=lambda *a: "<FAKE>",
                         job=lambda name, repos: job(conclusion=conclusion))
    runners.sandbox_boot(
        gh, Sandbox, snapshot="base", labels=["sbx"], group_id=1,
        job_timeout_s=60, idle_ttl_s=60, failed_jobs=store, keep_failed=maximum,
        repos=["acme/app"],
    )(runners.Slot("sbx-test", 0))
    return Sandbox.made[-1]


def test_failed_job_snapshots_before_kill_and_emits_metadata(setup, capsys):
    sbx = boot(setup)
    assert (sbx.snapshots, sbx.killed) == (1, 1)
    event = next(json.loads(line) for line in capsys.readouterr().out.splitlines()
                 if json.loads(line)["event"] == "kept_failed")
    assert {k: event[k] for k in ("job_id", "job_url", "repo", "sha", "snapshot_id")} == {
        "job_id": 123, "job_url": job()["html_url"], "repo": "acme/app",
        "sha": "a" * 40, "snapshot_id": "snap-1",
    }
    assert setup.find("123")["snapshot_id"] == "snap-1"


@pytest.mark.parametrize("conclusion", ["success", "cancelled", "timed_out", "neutral"])
def test_non_failed_job_does_not_snapshot(setup, conclusion, capsys):
    sbx = boot(setup, conclusion)
    assert (sbx.snapshots, sbx.killed, setup.list()) == (0, 1, [])
    assert "kept_failed" not in capsys.readouterr().out


def test_cap_evicts_oldest_and_persists_across_processes(setup):
    for jid in (1, 2, 3):
        sbx = Sandbox.create("base")
        setup.keep(sbx, job(jid), "sbx-test", maximum=2)
    assert Sandbox.deleted == ["snap-1"]
    again = FailedJobs(setup.directory, Sandbox)
    assert [r["job_id"] for r in again.list()] == [2, 3]
    assert again.find(job(2)["html_url"])["snapshot_id"] == "snap-2"


def test_snapshot_error_is_logged_and_sandbox_still_killed(setup, capsys):
    Sandbox.error = RuntimeError("snapshot unavailable")
    sbx = boot(setup)
    assert sbx.killed == 1 and setup.list() == []
    out = capsys.readouterr().out
    assert '"event": "keep_failed_error"' in out and "snapshot unavailable" in out
    assert '"event": "killed"' in out


def test_job_lookup_error_does_not_hold_pool_capacity(setup, capsys):
    def fail(*a):
        raise RuntimeError("GitHub unavailable")

    gh = SimpleNamespace(jit=lambda *a: "<FAKE>", job=fail)
    runners.sandbox_boot(gh, Sandbox, snapshot="base", labels=["sbx"], group_id=1,
                         job_timeout_s=60, idle_ttl_s=60, failed_jobs=setup,
                         keep_failed=5, repos=["acme/app"])(runners.Slot("sbx-test", 0))
    assert Sandbox.made[-1].killed == 1 and setup.list() == []
    assert '"event": "keep_failed_error"' in capsys.readouterr().out


def test_debug_restores_and_executes_preserved_machine(setup, monkeypatch, capsys):
    setup.keep(Sandbox.create("base"), job(), "sbx-test", maximum=5)
    monkeypatch.setattr(cli, "_failed_jobs", lambda *a: setup)
    assert cli.main(["runners", "debug", job()["html_url"], "--exec", "cat /tmp/proof"]) == 0
    sbx = Sandbox.made[-1]
    assert sbx.template == "snap-1"
    assert sbx.kwargs["lifecycle"] == {"on_timeout": "kill"}
    assert sbx.executed == [("cat /tmp/proof", {"timeout": 60})]
    out = capsys.readouterr().out
    assert "debug-1\n" in out and "sbx exec debug-1" in out
    assert "sbx kill debug-1" in out and "preserved\n" in out


def test_debug_list_delete_and_missing_job(setup, monkeypatch, capsys):
    setup.keep(Sandbox.create("base"), job(), "sbx-test", maximum=5)
    capsys.readouterr()
    monkeypatch.setattr(cli, "_failed_jobs", lambda *a: setup)
    assert cli.main(["runners", "debug", "--list"]) == 0
    assert json.loads(capsys.readouterr().out)["job_id"] == 123
    assert cli.main(["runners", "debug", "--delete", "123"]) == 0
    assert Sandbox.deleted == ["snap-1"] and setup.list() == []
    assert cli.main(["runners", "debug", "123"]) == 2
    assert "no retained snapshot" in capsys.readouterr().err


def test_github_matches_runner_across_run_and_job_pages():
    calls = []

    def handler(req):
        calls.append(str(req.url))
        if req.url.path.endswith("/runs"):
            page = int(req.url.params["page"])
            runs = [{"id": n, "head_sha": "a" * 40} for n in range(100)] if page == 1 else [{"id": 999}]
            return httpx.Response(200, json={"workflow_runs": runs})
        rid = int(req.url.path.split("/")[-2])
        page = int(req.url.params["page"])
        if rid == 999:
            jobs = [{"runner_name": "other"}] * 100 if page == 1 else [job()]
        else:
            jobs = []
        return httpx.Response(200, json={"jobs": jobs})

    gh = runners.GitHub("<FAKE>", "repos/acme/app", client=httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)))
    assert gh.job("sbx-test", ["acme/app"]) == job()
    assert any("filter=all" in call and "page=2" in call for call in calls)


def test_github_waits_for_terminal_conclusion(monkeypatch):
    responses = [job(conclusion=None), job()]
    monkeypatch.setattr(runners.time, "sleep", lambda s: None)

    def handler(req):
        if req.url.path.endswith("/runs"):
            return httpx.Response(200, json={"workflow_runs": [{"id": 9}]})
        return httpx.Response(200, json={"jobs": [responses.pop(0)]})

    gh = runners.GitHub("<FAKE>", "repos/acme/app", client=httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)))
    assert gh.job("sbx-test", ["acme/app"])["conclusion"] == "failure"
    assert responses == []


def test_keep_failed_parser_default_and_explicit_cap():
    parser = cli.build_parser()
    argv = ["runners", "serve", "--repo", "acme/app", "--snapshot", "base"]
    assert parser.parse_args(argv).keep_failed == 0
    assert parser.parse_args([*argv, "--keep-failed"]).keep_failed == 5
    assert parser.parse_args([*argv, "--keep-failed=2"]).keep_failed == 2


def test_index_write_failure_deletes_unindexed_snapshot(setup, monkeypatch):
    monkeypatch.setattr(setup, "_write", lambda records: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        setup.keep(Sandbox.create("base"), job(), "sbx-test", maximum=5)
    assert Sandbox.deleted == ["snap-1"]
    assert setup.list() == []


def test_eviction_error_is_logged_without_losing_snapshots_or_sandbox_capacity(setup, monkeypatch, capsys):
    setup.keep(Sandbox.create("base"), job(1), "sbx-test", maximum=1)

    def fail(sid):
        raise RuntimeError("delete unavailable")

    monkeypatch.setattr(Sandbox, "delete_snapshot", fail)
    sbx = boot(setup, maximum=1)
    assert sbx.killed == 1
    assert [r["job_id"] for r in setup.list()] == [1, 123]
    assert "delete unavailable" in capsys.readouterr().out


def test_pool_drain_cannot_kill_a_machine_being_snapshotted(setup):
    slot = runners.Slot("sbx-test", 0, finishing=True, sandbox_id="debug-1")
    killed = []
    slot.kill = lambda: killed.append(1)
    gh = SimpleNamespace(runners=lambda prefix: {}, delete=lambda rid: True)
    pool = runners.Pool(gh, lambda slot: None, warm=0, maximum=1)
    pool.slots[slot.name] = slot
    pool.drain()
    assert killed == [] and not slot.retiring
    assert pool.tick()["spawned"] == 0 and slot.name in pool.slots


def test_pool_drain_cannot_kill_snapshot_started_during_deregistration(setup, monkeypatch, capsys):
    deleting, snapshotting, release_snapshot = (threading.Event() for _ in range(3))
    slot = runners.Slot("sbx-test", 0)
    errors = []

    def delete(rid):
        deleting.set()
        assert snapshotting.wait(5)
        return True

    def wait_runner(*args, **kwargs):
        assert deleting.wait(5)
        return True

    create_snapshot = Sandbox.create_snapshot

    def snapshot(sbx):
        snapshotting.set()
        assert release_snapshot.wait(5)
        return create_snapshot(sbx)

    monkeypatch.setattr(runners, "_wait_runner", wait_runner)
    monkeypatch.setattr(Sandbox, "create_snapshot", snapshot)
    gh = SimpleNamespace(
        jit=lambda *a: "<FAKE>", job=lambda *a: job(), delete=delete,
        runners=lambda prefix: {slot.name: {"id": 1}},
    )
    boot_slot = runners.sandbox_boot(
        gh, Sandbox, snapshot="base", labels=["sbx"], group_id=1,
        job_timeout_s=60, idle_ttl_s=60, failed_jobs=setup, keep_failed=5,
    )
    pool = runners.Pool(gh, boot_slot, warm=0, maximum=1)
    pool.slots[slot.name] = slot

    def run():
        try:
            boot_slot(slot)
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    try:
        pool.drain()
        assert slot.finishing and not slot.retiring
        assert Sandbox.made[-1].killed == 0
    finally:
        release_snapshot.set()
        worker.join(5)
    assert not worker.is_alive() and errors == []
    assert setup.find("123")["snapshot_id"] == "snap-1"
    assert Sandbox.made[-1].killed == 1
    assert "keep_failed_error" not in capsys.readouterr().out


def test_runner_timeout_does_not_attempt_snapshot(setup, monkeypatch):
    from e2b import TimeoutException

    def run(self, command, **kwargs):
        def wait():
            raise TimeoutException("stream timeout")

        return SimpleNamespace(pid=42, wait=wait)

    monkeypatch.setattr(Sandbox, "run", run)
    sbx = boot(setup)
    assert (sbx.snapshots, sbx.killed, setup.list()) == (0, 1, [])


@pytest.mark.parametrize("reference", ["garbage", "0", "https://example.com/acme/app/actions/runs/9/job/123"])
def test_debug_rejects_invalid_reference_before_creating_sandbox(setup, reference):
    assert cli.main(["runners", "debug", reference]) == 2
    assert Sandbox.made == []


def test_job_url_cannot_resolve_a_different_repository(setup):
    setup.keep(Sandbox.create("base"), job(), "sbx-test", maximum=5)
    with pytest.raises(cli.SbxError, match="no retained snapshot"):
        setup.find(job()["html_url"].replace("acme/app", "other/app"))


def test_state_directory_is_scoped_to_key_and_endpoint(monkeypatch, tmp_path):
    from sbx.runner_debug import state_directory

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    paths = {state_directory(key, endpoint) for key, endpoint in
             [("<FAKE-A>", "https://api.example"), ("<FAKE-B>", "https://api.example"),
              ("<FAKE-A>", "https://other.example")]}
    assert len(paths) == 3
    assert all(p.is_relative_to(tmp_path) and "<FAKE" not in str(p) for p in paths)


def test_malformed_job_metadata_cannot_leak_a_snapshot(setup):
    sbx = Sandbox.create("base")
    incomplete = job()
    del incomplete["html_url"]
    with pytest.raises(KeyError):
        setup.keep(sbx, incomplete, "sbx-test", maximum=5)
    assert sbx.snapshots == 0 and setup.list() == []


def test_org_lookup_discovers_repositories_when_not_watched():
    paths = []

    def handler(req):
        paths.append(req.url.path)
        if req.url.path == "/orgs/acme/repos":
            return httpx.Response(200, json=[{"full_name": "acme/app"}])
        if req.url.path.endswith("/runs"):
            return httpx.Response(200, json={"workflow_runs": [{"id": 9}]})
        return httpx.Response(200, json={"jobs": [job()]})

    gh = runners.GitHub("<FAKE>", "orgs/acme", client=httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)))
    assert gh.job("sbx-test", []) == job()
    assert paths == ["/orgs/acme/repos", "/repos/acme/app/actions/runs",
                     "/repos/acme/app/actions/runs/9/jobs"]


def test_job_lookup_budget_bounds_missing_runner(monkeypatch):
    now = [0]
    monkeypatch.setattr(runners.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(runners.time, "sleep", lambda s: None)
    calls = []

    def handler(req):
        calls.append(req.url.path)
        now[0] += 31
        if req.url.path.endswith("/runs"):
            return httpx.Response(200, json={"workflow_runs": [{"id": 9}]})
        return httpx.Response(200, json={"jobs": []})

    gh = runners.GitHub("<FAKE>", "repos/acme/app", client=httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)))
    with pytest.raises(cli.SbxError, match="lookup timed out"):
        gh.job("missing", [])
    assert len(calls) == 2


def test_debug_exec_propagates_nonzero_exit_code(setup, monkeypatch, capsys):
    from e2b import CommandExitException

    setup.keep(Sandbox.create("base"), job(), "sbx-test", maximum=5)
    monkeypatch.setattr(cli, "_failed_jobs", lambda *a: setup)

    def fail(self, command, **kwargs):
        raise CommandExitException(stdout="failed output\n", stderr="failed error\n",
                                   exit_code=7, error="process exited")

    monkeypatch.setattr(Sandbox, "run", fail)
    assert cli.main(["runners", "debug", "123", "--exec", "exit 7"]) == 7
    out = capsys.readouterr()
    assert out.out.endswith("failed output\n") and out.err == "failed error\n"
