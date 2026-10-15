import json
import time

import httpx
import pytest

from sbx import cli, runners


_real_key_concurrency = cli._key_concurrency


@pytest.fixture(autouse=True)
def no_account_lookup(monkeypatch):
    monkeypatch.setattr(cli, "_key_concurrency", lambda key, domain: None)


class FakeGitHub:
    def __init__(self):
        self.registered = {}  # name -> {"id", "status", "busy"}
        self.deleted = []
        self.jits = []
        self.backlog = 0

    def runners(self, prefix):
        return {n: r for n, r in self.registered.items() if n.startswith(prefix)}

    def delete(self, runner_id):
        reg = next(r for r in self.registered.values() if r["id"] == runner_id)
        if reg["busy"]:
            return False
        self.deleted.append(runner_id)
        self.registered = {n: r for n, r in self.registered.items() if r["id"] != runner_id}
        return True

    def jit(self, name, labels, group_id):
        self.jits.append((name, labels, group_id))
        return "JIT-" + name

    def online(self, slot, busy=False):
        self.registered[slot.name] = {"id": len(self.registered) + 1, "name": slot.name, "status": "online", "busy": busy}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make_pool(gh, clock, **kw):
    """Pool whose slots stay 'starting' until a test marks them online via FakeGitHub."""
    return runners.Pool(
        gh,
        boot=lambda slot: None,
        clock=clock,
        spawn=lambda fn: None,
        **{"warm": 2, "maximum": 4, "scale_down_after": 60, "idle_ttl": 600, "start_ttl": 120, **kw},
    )


def live(pool):
    return sorted(pool.slots.values(), key=lambda s: s.name)


def test_spawns_warm_runners_and_counts_starting_ones_as_ready():
    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock)
    assert pool.tick()["spawned"] == 2
    assert pool.tick()["spawned"] == 0
    assert len(pool.slots) == 2


def test_busy_runner_is_replaced_to_keep_the_warm_level():
    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock)
    pool.tick()
    a, b = live(pool)
    gh.online(a, busy=True)
    gh.online(b)
    state = pool.tick()
    assert (state["busy"], state["idle"], state["spawned"]) == (1, 1, 1)
    assert len(pool.slots) == 3


def test_max_caps_live_sandboxes():
    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock, warm=2, maximum=2)
    pool.tick()
    for slot in live(pool):
        gh.online(slot, busy=True)
    assert pool.tick()["spawned"] == 0
    assert len(pool.slots) == 2


def test_backlog_scales_past_warm_up_to_max():
    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock, warm=1, maximum=4, queued=lambda: 10)
    assert pool.tick() == {"starting": 0, "idle": 0, "busy": 0, "queued": 10, "spawned": 4}


def test_finished_slots_are_dropped_and_refilled():
    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock, warm=1)
    pool.tick()
    (slot,) = live(pool)
    gh.online(slot, busy=True)
    pool.tick()  # busy -> one replacement spawned
    del gh.registered[slot.name]  # ephemeral runner deregisters after its job
    slot.done = True
    pool.tick()
    assert slot.name not in pool.slots


def test_job_finished_but_sandbox_not_yet_killed_is_not_counted_ready():
    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock, warm=1, maximum=2)
    pool.tick()
    (slot,) = live(pool)
    gh.online(slot)
    pool.tick()
    del gh.registered[slot.name]
    state = pool.tick()
    assert state["spawned"] == 1 and state["idle"] == 0


def test_idle_ttl_retires_deregisters_then_kills():
    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock, warm=1, idle_ttl=600)
    pool.tick()
    (slot,) = live(pool)
    killed = []
    slot.kill = lambda: killed.append(slot.name)
    gh.online(slot)
    pool.tick()
    clock.now += 601
    state = pool.tick()
    assert killed == [slot.name] and gh.deleted == [1]
    assert slot.retiring and state["spawned"] == 1


def test_a_runner_github_reports_busy_is_never_retired():
    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock, warm=1, idle_ttl=600)
    pool.tick()
    (slot,) = live(pool)
    gh.online(slot)
    pool.tick()
    clock.now += 601
    # GitHub assigned a job between our list and the delete: delete answers 422
    gh.registered[slot.name]["busy"] = True
    gh.runners = lambda prefix: {slot.name: {**gh.registered[slot.name], "busy": False}}
    killed = []
    slot.kill = lambda: killed.append(1)
    pool.tick()
    assert killed == [] and not slot.retiring


def test_scale_down_waits_then_trims_excess_idle_to_warm():
    gh, clock = FakeGitHub(), Clock()
    backlog = {"n": 3}
    pool = make_pool(gh, clock, warm=1, maximum=4, queued=lambda: backlog["n"])
    pool.tick()
    for slot in live(pool):
        gh.online(slot)
        slot.kill = lambda: None
    backlog["n"] = 0
    pool.tick()
    clock.now += 30
    pool.tick()
    assert not any(s.retiring for s in pool.slots.values())
    clock.now += 31
    pool.tick()
    assert sum(not s.retiring for s in pool.slots.values()) == 1


def test_start_timeout_kills_a_runner_that_never_came_online():
    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock, warm=1, start_ttl=120)
    pool.tick()
    (slot,) = live(pool)
    killed = []
    slot.kill = lambda: killed.append(1)
    clock.now += 121
    pool.tick()
    assert killed == [1] and slot.retiring


def test_drain_retires_idle_and_starting_but_not_busy():
    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock, warm=3, maximum=3)
    pool.tick()
    a, b, c = live(pool)
    gh.online(a, busy=True)
    gh.online(b)
    for s in (a, b, c):
        s.kill = lambda: None
    pool.tick()
    pool.drain()
    assert (a.retiring, b.retiring, c.retiring) == (False, True, True)


def test_boot_errors_are_reported_and_free_the_slot(capsys):
    gh, clock = FakeGitHub(), Clock()

    def boom(slot):
        raise RuntimeError("gateway down")

    pool = runners.Pool(gh, boom, warm=1, maximum=1, clock=clock, spawn=lambda fn: fn(), boot_backoff=15)
    pool.tick()
    assert all(s.done for s in pool.slots.values())
    assert "boot_error" in capsys.readouterr().out
    assert pool.tick()["spawned"] == 0  # backing off: a quota 429 would only repeat
    clock.now += 16
    pool.tick()  # the failed slot is dropped and a new one spawned
    assert len(pool.slots) == 1


@pytest.mark.parametrize("warm,maximum", [(-1, 2), (3, 2), (0, 0)])
def test_bad_pool_sizes_are_rejected(warm, maximum):
    with pytest.raises(runners.RunnerError):
        runners.Pool(FakeGitHub(), lambda s: None, warm=warm, maximum=maximum)


# --- sandbox boot ---------------------------------------------------------


class FakeHandle:
    pid = 42

    def __init__(self, error=None):
        self.error = error

    def wait(self):
        if self.error:
            raise self.error
        return type("R", (), {"exit_code": 0})()


class FakeSbx:
    made = []

    def __init__(self, error=None):
        self.sandbox_id = f"sb-{len(FakeSbx.made)}"
        self.files, self.commands = self, self
        self.written, self.ran, self.killed, self.error = {}, [], 0, error

    @classmethod
    def create(cls, template, **kw):
        sbx = cls(cls.next_error)
        sbx.create_args = (template, kw)
        cls.made.append(sbx)
        return sbx

    def write(self, path, data):
        self.written[path] = data

    def run(self, cmd, **kw):
        self.ran.append((cmd, kw))
        return FakeHandle(self.error)

    def kill(self):
        self.killed += 1

    def connect(self, pid, timeout=None):
        from e2b import NotFoundException

        raise NotFoundException(f"process with pid {pid} not found")  # what envd answers for an exited pid


@pytest.fixture
def fake_sbx():
    FakeSbx.made, FakeSbx.next_error = [], None
    return FakeSbx


def test_boot_registers_runs_one_job_and_kills(fake_sbx, capsys):
    gh = FakeGitHub()
    boot = runners.sandbox_boot(gh, fake_sbx, snapshot="snap-1", labels=["self-hosted", "sbx"],
                                group_id=3, job_timeout_s=600, idle_ttl_s=60)
    slot = runners.Slot("sbx-abc", 0.0)
    boot(slot)
    (sbx,) = fake_sbx.made
    template, kw = sbx.create_args
    assert template == "snap-1" and kw["lifecycle"] == {"on_timeout": "kill"} and kw["timeout"] == 960
    assert gh.jits == [("sbx-abc", ["self-hosted", "sbx"], 3)]
    assert sbx.written == {"/tmp/jit": "JIT-sbx-abc"}
    cmd, run_kw = sbx.ran[0]
    assert run_kw == {"background": True, "timeout": 960, "user": "root"}  # never an unbounded stream
    assert "dockerd" in cmd and "rm -f /tmp/jit" in cmd
    assert 'exec sudo -n -u user -H ./run.sh --jitconfig "$jit"' in cmd  # the job never runs as root
    assert 'echo "E2B_SANDBOX_ID=$E2B_SANDBOX_ID" >> .env' in cmd  # keeps the image's AGENT_TOOLSDIRECTORY
    assert sbx.killed == 1 and slot.sandbox_id == sbx.sandbox_id
    events = [json.loads(line)["event"] for line in capsys.readouterr().out.splitlines()]
    assert events == ["sandbox", "runner_exit", "killed"]


def test_boot_kills_the_sandbox_even_when_the_runner_fails(fake_sbx):
    fake_sbx.next_error = RuntimeError("runner crashed")
    boot = runners.sandbox_boot(FakeGitHub(), fake_sbx, snapshot="s", labels=["x"], group_id=1,
                                job_timeout_s=1, idle_ttl_s=1)
    boot(runners.Slot("sbx-1", 0.0))
    assert fake_sbx.made[0].killed == 1


def test_boot_skips_the_runner_when_retired_during_create(fake_sbx):
    slot = runners.Slot("sbx-1", 0.0, retiring=True)
    boot = runners.sandbox_boot(FakeGitHub(), fake_sbx, snapshot="s", labels=["x"], group_id=1,
                                job_timeout_s=1, idle_ttl_s=1)
    boot(slot)
    assert fake_sbx.made[0].ran == [] and fake_sbx.made[0].killed == 1


class Blip:
    """A gateway blip: the next `fails` calls raise, later ones succeed."""

    def __init__(self, fails, error):
        self.fails, self.error, self.calls = fails, error, 0

    def __call__(self, *a, **kw):
        self.calls += 1
        if self.calls <= self.fails:
            raise self.error


def blip_boot(fake_sbx, monkeypatch):
    monkeypatch.setattr(runners.time, "sleep", lambda s: None)
    return runners.sandbox_boot(FakeGitHub(), fake_sbx, snapshot="s", labels=["x"], group_id=1,
                                job_timeout_s=600, idle_ttl_s=60)


def events(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def test_a_dropped_stream_reconnects_to_the_runner_instead_of_killing_the_job(fake_sbx, monkeypatch, capsys):
    fake_sbx.next_error = httpx.ConnectError("Error reading content")
    connects = []

    def connect(self, pid, timeout=None):
        connects.append((pid, self.killed))
        return FakeHandle()

    monkeypatch.setattr(FakeSbx, "connect", connect)
    blip_boot(fake_sbx, monkeypatch)(runners.Slot("sbx-1", 0.0))
    assert connects == [(42, 0)]  # reattached before any kill
    names = [e["event"] for e in events(capsys)]
    assert names == ["sandbox", "stream_lost", "runner_exit", "killed"]


@pytest.mark.parametrize("gone", ["NotFoundException", "TimeoutException"])
def test_a_runner_gone_after_the_blip_ends_the_slot(gone, fake_sbx, monkeypatch, capsys):
    import e2b

    fake_sbx.next_error = httpx.ConnectError("Error reading content")
    # an exited process is NotFound; a killed sandbox answers Timeout ("sandbox was not found")
    blip = Blip(1, getattr(e2b, gone)("gone"))
    monkeypatch.setattr(FakeSbx, "connect", lambda self, pid, timeout=None: blip())
    blip_boot(fake_sbx, monkeypatch)(runners.Slot("sbx-1", 0.0))
    assert fake_sbx.made[0].killed == 1 and blip.calls == 1
    assert [e["event"] for e in events(capsys)][-1] == "killed"


def test_reconnect_retries_through_a_gateway_restart(fake_sbx, monkeypatch, capsys):
    from e2b import SandboxException

    fake_sbx.next_error = httpx.ConnectError("Error reading content")
    blip = Blip(3, SandboxException("503: gateway is restarting"))

    def connect(self, pid, timeout=None):
        blip()
        return FakeHandle()

    monkeypatch.setattr(FakeSbx, "connect", connect)
    blip_boot(fake_sbx, monkeypatch)(runners.Slot("sbx-1", 0.0))
    assert blip.calls == 4
    exits = [e for e in events(capsys) if e["event"] == "runner_exit"]
    assert exits == [{**exits[0], "code": 0}]


def test_a_retired_slot_does_not_reconnect(fake_sbx, monkeypatch):
    fake_sbx.next_error = httpx.ConnectError("killed under us")
    monkeypatch.setattr(FakeSbx, "connect", Blip(99, AssertionError("must not reconnect")))
    slot = runners.Slot("sbx-1", 0.0)
    real_create = FakeSbx.create.__func__

    def create(cls, template, **kw):
        slot.retiring = False
        sbx = real_create(cls, template, **kw)
        sbx.write = lambda path, data: setattr(slot, "retiring", True)  # retired while registering
        return sbx

    monkeypatch.setattr(FakeSbx, "create", classmethod(create))
    blip_boot(fake_sbx, monkeypatch)(slot)
    assert fake_sbx.made[0].killed == 1


def test_a_failed_kill_is_retried(fake_sbx, monkeypatch, capsys):
    from e2b import SandboxException

    blip = Blip(2, SandboxException("503: gateway is restarting"))
    monkeypatch.setattr(FakeSbx, "kill", lambda self: blip(), raising=True)
    blip_boot(fake_sbx, monkeypatch)(runners.Slot("sbx-1", 0.0))
    assert blip.calls == 3
    names = [e["event"] for e in events(capsys)]
    assert names.count("killed") == 1 and "kill_failed" not in names


def test_reattaching_gives_up_after_the_outage_window(fake_sbx, monkeypatch, capsys):
    fake_sbx.next_error = httpx.ConnectError("Error reading content")
    clock = Clock()
    monkeypatch.setattr(runners.time, "monotonic", clock)
    monkeypatch.setattr(runners.time, "sleep", lambda s: setattr(clock, "now", clock.now + s))
    blip = Blip(10**6, httpx.ConnectError("still down"))
    monkeypatch.setattr(FakeSbx, "connect", lambda self, pid, timeout=None: blip())
    runners.sandbox_boot(FakeGitHub(), fake_sbx, snapshot="s", labels=["x"], group_id=1,
                         job_timeout_s=3600, idle_ttl_s=60)(runners.Slot("sbx-1", 0.0))
    exits = [e for e in events(capsys) if e["event"] == "runner_exit"]
    assert exits[0]["error"] == "could not reattach to the runner"
    assert 600 <= clock.now - 1000 < 700 and fake_sbx.made[0].killed == 1


def test_a_flapping_stream_is_paced_and_bounded(fake_sbx, monkeypatch, capsys):
    clock = Clock()
    monkeypatch.setattr(runners.time, "monotonic", clock)
    monkeypatch.setattr(runners.time, "sleep", lambda s: setattr(clock, "now", clock.now + s))
    fake_sbx.next_error = httpx.ConnectError("Error reading content")
    # every reattach succeeds, and every new stream drops at once
    monkeypatch.setattr(FakeSbx, "connect", lambda self, pid, timeout=None: FakeHandle(httpx.ConnectError("again")))
    runners.sandbox_boot(FakeGitHub(), fake_sbx, snapshot="s", labels=["x"], group_id=1,
                         job_timeout_s=3600, idle_ttl_s=60)(runners.Slot("sbx-1", 0.0))
    evs = events(capsys)
    assert evs[-2] == {**evs[-2], "event": "runner_exit", "error": "could not reattach to the runner"}
    assert 600 <= clock.now - 1000 < 700 and sum(e["event"] == "stream_lost" for e in evs) < 60


def test_a_runner_that_exits_while_disconnected_is_not_an_error(fake_sbx, monkeypatch, capsys):
    fake_sbx.next_error = httpx.ConnectError("Error reading content")
    blip_boot(fake_sbx, monkeypatch)(runners.Slot("sbx-1", 0.0))  # FakeSbx.connect: pid not found
    (exit_,) = [e for e in events(capsys) if e["event"] == "runner_exit"]
    assert "error" not in exit_ and exit_["note"] == "exited while disconnected"


def test_a_slot_retired_during_the_outage_stops_reattaching_quietly(fake_sbx, monkeypatch, capsys):
    from e2b import TimeoutException

    fake_sbx.next_error = httpx.ConnectError("Error reading content")
    slot = runners.Slot("sbx-1", 0.0)

    def connect(self, pid, timeout=None):
        slot.retiring = True  # retire() killed the sandbox: connect now times out
        raise TimeoutException("The sandbox was not found")

    monkeypatch.setattr(FakeSbx, "connect", connect)
    blip_boot(fake_sbx, monkeypatch)(slot)
    assert not [e for e in events(capsys) if e["event"] == "runner_exit"]


def test_a_sandbox_gone_while_disconnected_is_an_error(fake_sbx, monkeypatch, capsys):
    from e2b import SandboxNotFoundException

    fake_sbx.next_error = httpx.ConnectError("Error reading content")
    monkeypatch.setattr(FakeSbx, "connect", Blip(1, SandboxNotFoundException("sandbox gone")))
    blip_boot(fake_sbx, monkeypatch)(runners.Slot("sbx-1", 0.0))
    (exit_,) = [e for e in events(capsys) if e["event"] == "runner_exit"]
    assert exit_["error"].startswith("SandboxNotFoundException")


def test_a_kill_that_never_succeeds_is_reported_not_claimed(fake_sbx, monkeypatch, capsys):
    from e2b import SandboxException

    blip = Blip(10**6, SandboxException("503: gateway is restarting"))
    monkeypatch.setattr(FakeSbx, "kill", lambda self: blip(), raising=True)
    blip_boot(fake_sbx, monkeypatch)(runners.Slot("sbx-1", 0.0))
    names = [e["event"] for e in events(capsys)]
    assert "killed" not in names and names[-1] == "kill_failed"
    assert 1 < blip.calls < 20


# --- GitHub client ---------------------------------------------------------


def github(handler):
    return runners.GitHub("t", "orgs/acme", client=httpx.Client(base_url="https://api.github.com",
                                                                transport=httpx.MockTransport(handler)))


def test_runners_pages_and_filters_by_prefix():
    def handler(req):
        page = int(req.url.params["page"])
        names = [f"sbx-{i}" for i in range(100)] if page == 1 else ["sbx-x", "other-1"]
        return httpx.Response(200, json={"runners": [{"id": i, "name": n} for i, n in enumerate(names)]})

    got = github(handler).runners("sbx-")
    assert len(got) == 101 and "other-1" not in got


@pytest.mark.parametrize("status,expected", [(204, True), (404, True), (422, False)])
def test_delete_reports_busy_as_false(status, expected):
    assert github(lambda req: httpx.Response(status)).delete(7) is expected


def test_delete_raises_on_other_errors():
    with pytest.raises(runners.RunnerError, match="HTTP 500"):
        github(lambda req: httpx.Response(500, text="nope")).delete(7)


def test_jit_posts_the_registration_body():
    seen = {}

    def handler(req):
        seen["path"], seen["body"] = req.url.path, json.loads(req.content)
        return httpx.Response(201, json={"encoded_jit_config": "B64"})

    assert github(handler).jit("sbx-1", ["self-hosted", "sbx"], 3) == "B64"
    assert seen == {"path": "/orgs/acme/actions/runners/generate-jitconfig",
                    "body": {"name": "sbx-1", "runner_group_id": 3, "labels": ["self-hosted", "sbx"],
                             "work_folder": "_work"}}


def test_queued_counts_only_jobs_this_pool_can_serve():
    def handler(req):
        if req.url.path.endswith("/runs"):
            runs = [{"id": 1}] if req.url.params["status"] == "in_progress" else []
            return httpx.Response(200, json={"workflow_runs": runs})
        return httpx.Response(200, json={"jobs": [
            {"status": "queued", "labels": ["self-hosted", "SBX"]},
            {"status": "queued", "labels": ["self-hosted", "sbx", "linux"]},
            {"status": "queued", "labels": ["self-hosted"]},
            {"status": "queued", "labels": ["ubuntu-latest"]},
            {"status": "in_progress", "labels": ["self-hosted", "sbx"]},
        ]})

    demand = runners.RestDemand(github(handler), ["acme/app"], ["self-hosted", "sbx"])
    assert demand.poll(lambda repo, job: pytest.fail("unexpected cancel")) == 2


# --- CLI -------------------------------------------------------------------


def test_serve_needs_exactly_one_scope(monkeypatch, capsys):
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    monkeypatch.setenv("GH_TOKEN", "gh-test-token")
    assert cli.main(["runners", "serve", "--snapshot", "s"]) == 2
    assert cli.main(["runners", "serve", "--snapshot", "s", "--org", "a", "--repo", "a/b"]) == 2
    assert "exactly one of --org or --repo" in capsys.readouterr().err


def test_serve_without_github_token_is_a_usage_error(monkeypatch, capsys):
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert cli.main(["runners", "serve", "--snapshot", "s", "--org", "a"]) == 2
    assert "no GitHub token" in capsys.readouterr().err


def test_github_token_never_reaches_the_terminal(monkeypatch, capsys):
    secret = "gh-very-secret-value"
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    monkeypatch.setenv("GH_TOKEN", secret)

    def boom(*a, **k):
        raise RuntimeError(f"bad credentials {secret}")

    monkeypatch.setattr(runners, "sweep", lambda *a: None)
    monkeypatch.setattr(runners, "serve", boom)
    assert cli.main(["runners", "serve", "--snapshot", "s", "--org", "a"]) == 1
    err = capsys.readouterr().err
    assert secret not in err and "[redacted]" in err


def test_serve_ticks_until_stopped_then_drains(capsys):
    import threading

    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock, warm=1, maximum=1)
    stop = threading.Event()
    real_tick = pool.tick

    def tick():
        state = real_tick()
        for slot in pool.slots.values():
            slot.kill = lambda s=slot: setattr(s, "done", True)
        stop.set()
        return state

    pool.tick = tick
    runners.serve(pool, interval=0, stop=stop)
    events = [json.loads(line)["event"] for line in capsys.readouterr().out.splitlines()]
    assert events[0] == "serve" and "pool" in events and events[-2:] == ["retire", "stopped"]


def test_tick_errors_do_not_stop_serving(capsys):
    import threading

    stop = threading.Event()
    pool = make_pool(FakeGitHub(), Clock())
    calls = []

    def tick():
        calls.append(1)
        if len(calls) == 2:
            stop.set()
        raise RuntimeError("github 502")

    pool.tick = tick
    runners.serve(pool, interval=0, stop=stop)
    assert len(calls) == 2 and capsys.readouterr().out.count("tick_error") == 2


def test_image_bakes_runner_and_docker_then_snapshots(fake_sbx, monkeypatch):
    monkeypatch.setattr(fake_sbx, "create_snapshot", lambda self: type("Snap", (), {"snapshot_id": "snap-9"})(),
                        raising=False)
    assert runners.build_image(fake_sbx, template=None, runner_version="2.338.0") == "snap-9"
    (sbx,) = fake_sbx.made
    script = "\n".join(cmd for cmd, _ in sbx.ran)
    assert "actions-runner-linux-x64-2.338.0.tar.gz" in script and "installdependencies.sh" in script
    assert "dockerd" in script and "docker run --rm hello-world" in script and "/etc/hosts" in script
    assert all(kw["user"] == "root" for _, kw in sbx.ran)  # a bare image has no sudo yet
    assert "lsb-release" in sbx.ran[0][0] and "python3" in sbx.ran[0][0]  # setup-python reads lsb_release
    assert "libgl1" in sbx.ran[0][0]  # a real CI run failed on a missing libGL.so.1
    assert "useradd -m -s /bin/bash user" in script and "NOPASSWD" in script and "get.docker.com" in script
    assert "chown -R user: /opt/actions-runner" in script
    # setup-python/-node find these preinstalled, as on GitHub's image
    assert "python-versions/main/versions-manifest.json" in script and "for v in 3.12 3.13" in script
    assert "nodejs.org/dist/index.json" in script and "for v in 20 22" in script
    assert "echo AGENT_TOOLSDIRECTORY=/opt/hostedtoolcache > /opt/actions-runner/.env" in script
    assert sbx.killed == 1


UBUNTU_TAG = __import__("hashlib").sha256(b"ubuntu:24.04").hexdigest()[:8]


def test_images_that_read_alike_get_different_templates():
    names = set()
    for image in ("foo/bar:1.0", "foo-bar-1-0", "Foo/Bar:1.0"):
        http, calls = template_api({})
        with pytest.raises(runners.RunnerError):  # no route: the lookup and register answer 404
            runners.ensure_template(http, image=image, size="small")
        names.add(calls[0][0])
    assert len(names) == 3


def test_a_failed_alias_lookup_is_the_error_reported():
    http, calls = template_api({"GET /templates/aliases/" + f"sbx-runner-ubuntu-24-04-{UBUNTU_TAG}-small":
                                httpx.Response(401, text="invalid API key")})
    with pytest.raises(runners.RunnerError, match="lookup failed: HTTP 401"):
        runners.ensure_template(http, image="ubuntu:24.04", size="small")
    assert len(calls) == 1  # nothing registered


def test_a_failed_cleanup_does_not_hide_the_import_error(monkeypatch):
    monkeypatch.setattr(runners.time, "sleep", lambda s: None)

    def handler(req):
        if req.method == "DELETE":
            raise httpx.ConnectError("gateway down")
        if req.url.path == "/v3/templates":
            return httpx.Response(202, json={"templateID": "tpl-1", "buildID": "bld-1"})
        if req.url.path.startswith("/v2/templates"):
            return httpx.Response(400, text="bad image")
        return httpx.Response(404)

    http = httpx.Client(base_url="https://api.example", transport=httpx.MockTransport(handler))
    with pytest.raises(runners.RunnerError, match="import failed: HTTP 400"):
        runners.ensure_template(http, image="no/such:image", size="small")


def template_api(routes):
    """Sandbox API double: routes maps 'METHOD path' to a response or a list of them (served in turn)."""
    calls = []

    def handler(req):
        key = f"{req.method} {req.url.path}"
        calls.append((key, json.loads(req.content) if req.content else None))
        resp = routes.get(key, httpx.Response(404))
        return resp.pop(0) if isinstance(resp, list) else resp

    return httpx.Client(base_url="https://api.example", transport=httpx.MockTransport(handler)), calls


def test_template_is_reused_when_the_key_already_has_it(capsys):
    alias = f"sbx-runner-ubuntu-24-04-{UBUNTU_TAG}-small"
    http, calls = template_api({f"GET /templates/aliases/{alias}": httpx.Response(200, json={})})
    assert runners.ensure_template(http, image="ubuntu:24.04", size="small") == alias
    assert [c for c, _ in calls] == [f"GET /templates/aliases/{alias}"]


def test_template_is_imported_from_the_image_and_awaited(monkeypatch):
    monkeypatch.setattr(runners.time, "sleep", lambda s: None)
    status = "/templates/tpl-1/builds/bld-1/status"
    http, calls = template_api({
        "POST /v3/templates": httpx.Response(202, json={"templateID": "tpl-1", "buildID": "bld-1"}),
        "POST /v2/templates/tpl-1/builds/bld-1": httpx.Response(202),
        f"GET {status}": [httpx.Response(200, json={"status": "building"}), httpx.Response(200, json={"status": "ready"})],
    })
    alias = runners.ensure_template(http, image="ubuntu:24.04", size="standard")
    assert alias == f"sbx-runner-ubuntu-24-04-{UBUNTU_TAG}-standard"
    assert calls[1] == ("POST /v3/templates", {"name": alias, "resourceClass": "standard"})
    assert calls[2] == ("POST /v2/templates/tpl-1/builds/bld-1", {"fromImage": "ubuntu:24.04"})
    assert [c for c, _ in calls].count(f"GET {status}") == 2


@pytest.mark.parametrize("failure", ["status", "import"])
def test_a_failed_import_deletes_the_template(failure, monkeypatch):
    monkeypatch.setattr(runners.time, "sleep", lambda s: None)
    http, calls = template_api({
        "POST /v3/templates": httpx.Response(202, json={"templateID": "tpl-1", "buildID": "bld-1"}),
        "POST /v2/templates/tpl-1/builds/bld-1": httpx.Response(400 if failure == "import" else 202, text="bad image"),
        "GET /templates/tpl-1/builds/bld-1/status": httpx.Response(200, json={"status": "error"}),
        "DELETE /templates/tpl-1": httpx.Response(204),
    })
    with pytest.raises(runners.RunnerError):
        runners.ensure_template(http, image="no/such:image", size="small")
    assert calls[-1][0] == "DELETE /templates/tpl-1"  # a broken alias would otherwise be reused


def test_image_command_bakes_from_the_ubuntu_template_by_default(monkeypatch, capsys):
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    seen = {}
    monkeypatch.setattr(runners, "latest_runner_version", lambda http: "2.338.0")
    monkeypatch.setattr(runners, "ensure_template", lambda api, **kw: seen.update(kw, base=str(api.base_url)) or "tpl-alias")
    monkeypatch.setattr(runners, "build_image", lambda cls, **kw: seen.update(built=kw) or "snap-1")
    assert cli.main(["runners", "image"]) == 0
    assert seen["image"] == "ubuntu:24.04" and seen["size"] == "small" and seen["base"].startswith("https://api.")
    assert seen["built"] == {"template": "tpl-alias", "runner_version": "2.338.0"}
    assert capsys.readouterr().out.strip().endswith("snap-1")


def test_image_command_with_a_template_skips_the_import(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    monkeypatch.setattr(runners, "latest_runner_version", lambda http: "2.338.0")
    monkeypatch.setattr(runners, "ensure_template", lambda api, **kw: pytest.fail("must not import"))
    built = {}
    monkeypatch.setattr(runners, "build_image", lambda cls, **kw: built.update(kw) or "snap-1")
    assert cli.main(["runners", "image", "--template", "mine"]) == 0
    assert built["template"] == "mine"


def test_image_kills_the_build_sandbox_on_failure(fake_sbx, monkeypatch):
    def fail(self, cmd, **kw):
        raise RuntimeError("curl: 404")

    monkeypatch.setattr(fake_sbx, "run", fail)
    with pytest.raises(RuntimeError):
        runners.build_image(fake_sbx, template=None, runner_version="0.0.0")
    assert fake_sbx.made[0].killed == 1


def test_latest_runner_version_strips_the_v():
    http = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"tag_name": "v2.338.0"})))
    assert runners.latest_runner_version(http) == "2.338.0"
    http = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(403)))
    with pytest.raises(runners.RunnerError, match="HTTP 403"):
        runners.latest_runner_version(http)


def test_backlog_is_counted_even_when_runners_are_starting():
    gh, clock = FakeGitHub(), Clock()
    calls = []
    pool = make_pool(gh, clock, warm=1, maximum=4, queued=lambda: calls.append(1) or 5)
    pool.tick()  # empty pool: count the backlog
    pool.tick()  # demand polling owns its cadence, not the pool's ready count
    assert len(calls) == 2


def test_shutdown_does_not_wait_on_retired_slots(capsys, monkeypatch):
    import threading

    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock, warm=2, maximum=2)
    stop = threading.Event()
    real_tick = pool.tick

    def tick():
        state = real_tick()
        stop.set()  # the killed sandboxes' boot threads never report done
        return state

    pool.tick = tick
    monkeypatch.setattr(runners.signal, "signal", lambda *a: None)  # serve runs off the main thread here
    done = threading.Thread(target=runners.serve, args=(pool,), kwargs={"interval": 0, "stop": stop}, daemon=True)
    done.start()
    done.join(5)
    assert not done.is_alive()
    assert capsys.readouterr().out.splitlines()[-1].endswith('"event": "stopped"}')


def test_retired_slots_are_forgotten_on_the_next_tick():
    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock, warm=1, start_ttl=120)
    pool.tick()
    (slot,) = live(pool)
    slot.kill = lambda: None
    clock.now += 121
    pool.tick()  # start timeout: retired, replacement spawned
    pool.tick()
    assert slot.name not in pool.slots and len(pool.slots) == 1


# --- webhook -----------------------------------------------------------------


def signed(secret, payload):
    import hashlib
    import hmac

    body = json.dumps(payload).encode()
    return body, "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def job_event(action, jid, labels=("self-hosted", "sbx")):
    return {"action": action, "workflow_job": {"id": jid, "labels": list(labels)}}


def test_job_queue_tracks_queued_until_started():
    changes, clock = [], Clock()
    q = runners.JobQueue("s3cret", ["self-hosted", "sbx"], on_change=lambda: changes.append(1), clock=clock)
    for event in (job_event("queued", 1), job_event("queued", 2), job_event("in_progress", 1)):
        body, sig = signed("s3cret", event)
        assert q.handle("workflow_job", sig, body) == 204
    assert len(q) == 1 and len(changes) == 3


def test_job_queue_rejects_bad_signatures_and_ignores_foreign_jobs():
    q = runners.JobQueue("s3cret", ["self-hosted", "sbx"])
    body, _ = signed("s3cret", job_event("queued", 1))
    _, wrong = signed("other", job_event("queued", 1))
    assert q.handle("workflow_job", wrong, body) == 401
    assert q.handle("workflow_job", "", body) == 401
    body, sig = signed("s3cret", job_event("queued", 2, labels=("ubuntu-latest",)))
    assert q.handle("workflow_job", sig, body) == 204
    body, sig = signed("s3cret", {"zen": "hi"})
    assert q.handle("ping", sig, body) == 204
    assert len(q) == 0


def test_job_queue_answers_400_on_malformed_payloads():
    q = runners.JobQueue("s3cret", ["sbx"])
    for payload in ({"action": "queued"}, {"action": "queued", "workflow_job": {"id": 1}}):
        body, sig = signed("s3cret", payload)
        assert q.handle("workflow_job", sig, body) == 400
    import hashlib
    import hmac

    raw = b"not json"
    assert q.handle("workflow_job", "sha256=" + hmac.new(b"s3cret", raw, hashlib.sha256).hexdigest(), raw) == 400


def test_job_queue_expires_jobs_whose_later_delivery_was_lost():
    clock = Clock()
    q = runners.JobQueue("s3cret", ["self-hosted", "sbx"], ttl=900, clock=clock)
    body, sig = signed("s3cret", job_event("queued", 1))
    q.handle("workflow_job", sig, body)
    clock.now += 899
    assert len(q) == 1
    clock.now += 2
    assert len(q) == 0


def test_webhook_server_round_trip():
    q = runners.JobQueue("s3cret", ["self-hosted", "sbx"])
    server = runners.webhook_server(q, "127.0.0.1", 0)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        body, sig = signed("s3cret", job_event("queued", 9))
        ok = httpx.post(url, content=body, headers={"X-GitHub-Event": "workflow_job", "X-Hub-Signature-256": sig})
        bad = httpx.post(url, content=body, headers={"X-GitHub-Event": "workflow_job", "X-Hub-Signature-256": "x"})
        assert (ok.status_code, bad.status_code, len(q)) == (204, 401, 1)
    finally:
        server.shutdown()


def test_backlog_scales_even_while_runners_are_idle():
    gh, clock = FakeGitHub(), Clock()
    backlog = {"n": 0}
    pool = make_pool(gh, clock, warm=2, maximum=8, queued=lambda: backlog["n"])
    pool.tick()
    for slot in live(pool):
        gh.online(slot)
    backlog["n"] = 5  # two idle runners absorb two jobs; boot the remaining three
    state = pool.tick()
    assert state["spawned"] == 3 and len(pool.slots) == 5


def test_wake_forces_an_early_tick():
    import threading

    stop, wake = threading.Event(), threading.Event()
    pool = make_pool(FakeGitHub(), Clock())
    ticks = []

    def tick():
        ticks.append(1)
        if len(ticks) == 1:
            wake.set()  # a delivery arrived
        else:
            stop.set()
        return {}

    pool.tick = tick
    started = time.monotonic()
    runners.serve(pool, interval=30, stop=stop, wake=wake)
    assert len(ticks) == 2 and time.monotonic() - started < 5


def test_webhook_port_needs_a_secret(monkeypatch, capsys):
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    monkeypatch.setenv("GH_TOKEN", "gh-test-token")
    monkeypatch.delenv("GH_WEBHOOK_SECRET", raising=False)
    assert cli.main(["runners", "serve", "--snapshot", "s", "--org", "a", "--webhook-port", "0"]) == 2
    assert "GH_WEBHOOK_SECRET" in capsys.readouterr().err


def test_failed_sandbox_create_registers_no_runner(fake_sbx):
    gh = FakeGitHub()

    def quota(*a, **k):
        raise RuntimeError("429 concurrent running sandbox quota exceeded")

    boot = runners.sandbox_boot(gh, type("NoRoom", (), {"create": staticmethod(quota)}), snapshot="s",
                                labels=["x"], group_id=1, job_timeout_s=1, idle_ttl_s=1)
    with pytest.raises(RuntimeError):
        boot(runners.Slot("sbx-1", 0.0))
    assert gh.jits == []


def test_a_freed_sandbox_ends_the_boot_backoff():
    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock, warm=2, maximum=2, boot_backoff=15)
    pool.tick()
    a, b = live(pool)
    a.sandbox_id, b.done = "sb-a", True  # b failed to boot (quota); a is running a job
    pool.backoff_until = clock.now + 15
    assert pool.tick()["spawned"] == 0
    a.done = True  # a's job finished and its sandbox was killed
    assert pool.tick()["spawned"] == 2


# --- review findings ---------------------------------------------------------


def test_a_slot_whose_sandbox_died_under_its_job_stops_counting():
    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock, warm=1, maximum=1, start_ttl=120)
    pool.tick()
    (slot,) = live(pool)
    slot.kill = lambda: None
    gh.online(slot, busy=True)
    pool.tick()
    gh.registered[slot.name]["status"] = "offline"  # sandbox killed mid-job; boot() never returns
    pool.tick()
    assert not slot.retiring
    clock.now += 121
    state = pool.tick()
    assert slot.retiring and state["spawned"] == 1  # the slot no longer holds a --max seat


def test_offline_registrations_without_a_slot_are_removed(capsys):
    gh, clock = FakeGitHub(), Clock()
    gh.registered = {
        "sbx-left": {"id": 41, "name": "sbx-left", "status": "offline", "busy": False},
        "sbx-other": {"id": 42, "name": "sbx-other", "status": "online", "busy": False},
        "ci-1": {"id": 43, "name": "ci-1", "status": "offline", "busy": False},
    }
    pool = make_pool(gh, clock, warm=0, maximum=1)
    pool.tick()
    assert gh.deleted == [41]
    assert "orphan_removed" in capsys.readouterr().out


def test_event_stream_is_scrubbed(monkeypatch, capsys):
    secret = "gh-very-secret-value"
    monkeypatch.setenv("GH_TOKEN", secret)
    runners.emit("boot_error", error=f"401 for {secret}")
    out = capsys.readouterr().out
    assert secret not in out and "[redacted]" in out


@pytest.mark.parametrize("flag", ["--interval", "--poll-interval", "--idle-min", "--job-timeout-min"])
@pytest.mark.parametrize("bad", ["0", "-1", "nan"])
def test_serve_timing_options_must_be_positive(flag, bad, monkeypatch, capsys):
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    monkeypatch.setenv("GH_TOKEN", "gh-test-token")
    assert cli.main(["runners", "serve", "--snapshot", "s", "--org", "a", flag, bad]) == 2
    assert "positive number" in capsys.readouterr().err


def test_a_retire_racing_the_boot_is_not_a_boot_error(capsys):
    gh, clock = FakeGitHub(), Clock()

    def boot(slot):
        slot.retiring = True  # retired while the sandbox was being created
        raise RuntimeError("sandbox already killed")

    pool = runners.Pool(gh, boot, warm=1, maximum=1, clock=clock, spawn=lambda fn: fn())
    pool.tick()
    assert "boot_error" not in capsys.readouterr().out and pool.backoff_until == 0.0


# --- review round 2 ----------------------------------------------------------


def test_webhook_server_answers_400_on_a_bad_content_length():
    import socket

    q = runners.JobQueue("s3cret", ["sbx"])
    server = runners.webhook_server(q, "127.0.0.1", 0)
    try:
        with socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=5) as conn:
            conn.sendall(b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: nope\r\n\r\n")
            assert conn.recv(64).startswith(b"HTTP/1.0 400")
    finally:
        server.shutdown()


@pytest.mark.parametrize("version", ["2.338.0; rm -rf /", "$(id)", "v2.338.0", ""])
def test_image_refuses_a_version_that_is_not_a_version(version, fake_sbx):
    with pytest.raises(runners.RunnerError, match="not an actions/runner version"):
        runners.build_image(fake_sbx, template=None, runner_version=version)
    assert fake_sbx.made == []


def test_watch_and_webhook_share_rest_cancel_tracking(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    monkeypatch.setenv("GH_TOKEN", "gh-test-token")
    monkeypatch.setenv("GH_WEBHOOK_SECRET", "hook-secret-value")
    monkeypatch.setattr(runners.GitHub, "check_repo", lambda *a: None)
    monkeypatch.setattr(runners, "webhook_server", lambda *a: None)
    monkeypatch.setattr(runners, "sweep", lambda *a: None)
    seen = {}
    monkeypatch.setattr(runners, "serve", lambda pool, **kw: seen.update(pool=pool))
    argv = ["runners", "serve", "--snapshot", "s", "--org", "a", "--webhook-port", "0", "--watch-repo", "a/b"]
    assert cli.main(argv) == 0
    assert seen["pool"].demand.repos == ["a/b"]


def test_a_start_timeout_is_one_retire(capsys):
    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock, warm=1, start_ttl=120)
    pool.tick()
    (slot,) = live(pool)
    slot.kill = lambda: None
    pool.tick()  # seen while still starting
    clock.now += 121
    pool.tick()
    assert capsys.readouterr().out.count('"event": "retire"') == 1


def test_a_full_pool_still_checks_demand_for_cancellations():
    gh, clock = FakeGitHub(), Clock()
    calls = []
    pool = make_pool(gh, clock, warm=1, maximum=1, queued=lambda: calls.append(1) or 3)
    pool.tick()  # empty: polls once and fills the only seat
    (slot,) = live(pool)
    gh.online(slot, busy=True)
    pool.tick()
    pool.tick()
    assert len(calls) == 3


def test_second_signal_aborts_busy_runners(monkeypatch):
    import signal as sig
    import threading

    handlers = {}
    monkeypatch.setattr(runners.signal, "signal", lambda num, fn: handlers.__setitem__(num, fn))
    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock, warm=1, maximum=1)
    killed = []
    stop = threading.Event()
    real_tick = pool.tick

    def tick():
        state = real_tick()
        (slot,) = live(pool)
        slot.kill = lambda: killed.append(slot.name)
        gh.online(slot, busy=True)
        real_tick()
        handlers[sig.SIGINT](sig.SIGINT, None)  # drain: the busy runner keeps going
        handlers[sig.SIGINT](sig.SIGINT, None)  # second Ctrl-C: kill it too
        return state

    pool.tick = tick
    done = threading.Thread(target=runners.serve, args=(pool,), kwargs={"interval": 0, "stop": stop}, daemon=True)
    done.start()
    done.join(5)
    assert not done.is_alive() and len(killed) == 1


# --- review round 3 ----------------------------------------------------------


def test_abort_never_waits_on_the_pool_lock():
    import threading

    gh, clock = FakeGitHub(), Clock()
    pool = make_pool(gh, clock, warm=1, maximum=1)
    pool.tick()
    (slot,) = live(pool)
    killed = []
    slot.kill = lambda: killed.append(1)
    with pool.lock:  # the signal arrives while the main thread is inside tick()/drain()
        done = threading.Thread(target=pool.abort, daemon=True)
        done.start()
        done.join(2)
        assert not done.is_alive() and killed == [1]


def test_concurrent_events_stay_one_json_line_each(monkeypatch):
    import io
    import threading

    class SlowOut(io.StringIO):  # yields inside every write, as a pipe to a slow reader does
        def write(self, text):
            time.sleep(0.0005)
            return super().write(text)

    out = SlowOut()
    monkeypatch.setattr(runners.sys, "stdout", out)
    threads = [threading.Thread(target=lambda i=i: [runners.emit("e", i=i, pad="x" * 2000) for _ in range(50)])
               for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    lines = out.getvalue().splitlines()
    assert len(lines) == 400 and all(json.loads(line)["event"] == "e" for line in lines)


def test_signed_payload_with_odd_labels_is_a_400():
    q = runners.JobQueue("s3cret", ["sbx"])
    body, sig = signed("s3cret", {"action": "queued", "workflow_job": {"id": 1, "labels": [3]}})
    assert q.handle("workflow_job", sig, body) == 400


def test_queued_pages_through_large_matrices():
    def handler(req):
        if req.url.path.endswith("/runs"):
            runs = [{"id": 1}] if req.url.params["status"] == "queued" else []
            return httpx.Response(200, json={"workflow_runs": runs})
        n = 100 if req.url.params["page"] == "1" else 30
        return httpx.Response(200, json={"jobs": [{"status": "queued", "labels": ["self-hosted", "sbx"]}] * n})

    demand = runners.RestDemand(github(handler), ["acme/app"], ["self-hosted", "sbx"])
    assert demand.poll(lambda repo, job: pytest.fail("unexpected cancel")) == 130


def test_job_timeout_must_fit_the_sandbox_lifetime(monkeypatch, capsys):
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    monkeypatch.setenv("GH_TOKEN", "gh-test-token")
    argv = ["runners", "serve", "--snapshot", "s", "--org", "a", "--job-timeout-min", "1440"]
    assert cli.main(argv) == 2
    assert "sandbox lifetime" in capsys.readouterr().err


class Listing:
    def __init__(self, items):
        self.items, self.has_next = items, True

    def next_items(self):
        self.has_next = False
        return self.items


def test_sweep_clears_an_earlier_serves_idle_leftovers(capsys):
    gh = FakeGitHub()
    gh.registered = {
        "sbx-idle": {"id": 1, "name": "sbx-idle", "status": "online", "busy": False},
        "sbx-busy": {"id": 2, "name": "sbx-busy", "status": "online", "busy": True},
        "sbx-dead": {"id": 3, "name": "sbx-dead", "status": "offline", "busy": False},
    }
    info = lambda sid, name: type("Info", (), {"sandbox_id": sid, "metadata": {"sbx-runner": name} if name else None})()
    killed = []

    class Sbx:
        @staticmethod
        def list():
            return Listing([info("a", "sbx-idle"), info("b", "sbx-busy"), info("c", None), info("d", "other-1")])

        @staticmethod
        def kill(sid):
            killed.append(sid)

    runners.sweep(gh, Sbx, "sbx-")
    assert sorted(gh.deleted) == [1, 3] and killed == ["a"]
    assert capsys.readouterr().out.count("orphan_") == 3


# --- review round 4 ----------------------------------------------------------


def test_sweep_spares_a_leftover_that_took_a_job_after_the_listing():
    gh = FakeGitHub()
    gh.registered = {"sbx-late": {"id": 1, "name": "sbx-late", "status": "online", "busy": False}}
    listed = {n: dict(r) for n, r in gh.registered.items()}
    gh.runners = lambda prefix: listed  # the listing says idle
    gh.registered["sbx-late"]["busy"] = True  # ...but GitHub assigned a job before the delete
    killed = []

    class Sbx:
        @staticmethod
        def list():
            meta = type("Info", (), {"sandbox_id": "a", "metadata": {"sbx-runner": "sbx-late"}})()
            return Listing([meta])

        @staticmethod
        def kill(sid):
            killed.append(sid)

    runners.sweep(gh, Sbx, "sbx-")
    assert killed == [] and gh.deleted == []


def serve_argv(*extra):
    return ["runners", "serve", "--snapshot", "s", "--org", "a", *extra]


def test_watch_repos_are_checked_at_start(monkeypatch, capsys):
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    monkeypatch.setenv("GH_TOKEN", "gh-test-token")

    def check(self, repo):
        raise runners.RunnerError(f"GitHub read repo {repo} failed: HTTP 404")

    monkeypatch.setattr(runners.GitHub, "check_repo", check)
    assert cli.main(serve_argv("--watch", "nope/typo")) == 2
    assert "HTTP 404" in capsys.readouterr().err


@pytest.mark.parametrize("prefix", ["", "  "])
def test_empty_prefix_is_refused(prefix, monkeypatch, capsys):
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    monkeypatch.setenv("GH_TOKEN", "gh-test-token")
    assert cli.main(serve_argv("--prefix", prefix)) == 2
    assert "--prefix must not be empty" in capsys.readouterr().err


def test_flag_errors_come_before_the_token_check(monkeypatch, capsys):
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_WEBHOOK_SECRET", raising=False)
    assert cli.main(serve_argv("--webhook-port", "0")) == 2
    assert "GH_WEBHOOK_SECRET" in capsys.readouterr().err


def test_labels_are_stripped(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    monkeypatch.setenv("GH_TOKEN", "gh-test-token")
    seen = {}
    monkeypatch.setattr(runners, "sandbox_boot", lambda gh, cls, **kw: seen.update(kw) or (lambda slot: None))
    monkeypatch.setattr(runners, "sweep", lambda *a: None)
    monkeypatch.setattr(runners, "serve", lambda *a, **k: None)
    assert cli.main(serve_argv("--labels", "sbx, gpu ,")) == 0
    assert seen["labels"] == ["self-hosted", "sbx", "gpu"]


def test_signed_payload_with_an_odd_job_id_is_a_400():
    q = runners.JobQueue("s3cret", ["sbx"])
    body, sig = signed("s3cret", {"action": "queued", "workflow_job": {"id": {"x": 1}, "labels": ["sbx"]}})
    assert q.handle("workflow_job", sig, body) == 400



@pytest.mark.parametrize("limit,warm,maximum", [(2, 2, 2), (1, 1, 1), (None, 2, 8), (10, 2, 8)])
def test_serve_caps_max_at_the_keys_concurrency(limit, warm, maximum, monkeypatch, capsys):
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    monkeypatch.setenv("GH_TOKEN", "gh-test-token")
    monkeypatch.setattr(cli, "_key_concurrency", lambda key, domain: limit)
    monkeypatch.setattr(runners, "sandbox_boot", lambda gh, cls, **kw: None)
    monkeypatch.setattr(runners, "sweep", lambda *a: None)
    monkeypatch.setattr(runners, "serve", lambda *a, **k: None)
    seen = {}
    monkeypatch.setattr(runners, "Pool", lambda gh, boot, **kw: seen.update(kw))
    assert cli.main(serve_argv("--warm", "2", "--max", "8")) == 0
    assert (seen["warm"], seen["maximum"]) == (warm, maximum)
    assert ('"max_capped"' in capsys.readouterr().out) == (limit is not None and limit < 8)


def test_the_quota_cap_does_not_hide_a_warm_above_max(monkeypatch, capsys):
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    monkeypatch.setenv("GH_TOKEN", "gh-test-token")
    monkeypatch.setattr(cli, "_key_concurrency", lambda key, domain: 2)
    assert cli.main(serve_argv("--warm", "5", "--max", "3")) == 2
    assert "--warm" in capsys.readouterr().err


@pytest.mark.parametrize("status,body,expected", [
    (200, {"limits": {"max_concurrent": True}}, None),
    (200, {"limits": {"max_concurrent": 2}, "tier": "free"}, 2),
    (200, {"limits": {"max_concurrent": None}}, None),
    (200, {"tier": "free"}, None),
    (404, {}, None),
])
def test_key_concurrency_reads_the_account_limit(status, body, expected, monkeypatch):
    seen = {}

    def get(url, headers, timeout):
        seen.update(url=url, key=headers["X-API-Key"])
        return httpx.Response(status, json=body)

    monkeypatch.setattr(cli.httpx, "get", get)
    monkeypatch.delenv("E2B_API_URL", raising=False)
    assert _real_key_concurrency("e2b-test-key", "sbx.example") == expected
    assert seen == {"url": "https://api.sbx.example/v0/account", "key": "e2b-test-key"}


def test_key_concurrency_is_none_when_the_gateway_is_unreachable(monkeypatch):
    def get(*a, **kw):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(cli.httpx, "get", get)
    assert _real_key_concurrency("e2b-test-key", "sbx.example") is None


# --- REST demand and cancel reclaim ----------------------------------------


def rest_demand(clock, handler, repos=None, **kw):
    gh = github(handler)
    gh.clock = clock
    return runners.RestDemand(gh, ["acme/app"] if repos is None else repos,
                              ["self-hosted", "sbx"], clock=clock, **kw)


@pytest.mark.parametrize("pool_labels,job_labels,expected", [
    (["self-hosted", "sbx", "gpu"], ["self-hosted", "SBX"], 1),
    (["self-hosted", "sbx"], ["self-hosted", "sbx", "gpu"], 0),
    (["self-hosted", "sbx"], ["self-hosted"], 1),
    (["self-hosted", "sbx"], ["ubuntu-latest"], 0),
])
def test_rest_demand_spawns_only_when_runner_includes_all_job_labels(pool_labels, job_labels, expected):
    clock = Clock()

    def handler(req):
        if req.url.path.endswith("/runs"):
            runs = [{"id": 1}] if req.url.params["status"] == "queued" else []
            return httpx.Response(200, json={"workflow_runs": runs})
        return httpx.Response(200, json={"jobs": [{"id": 1, "status": "queued", "labels": job_labels}]})

    demand = runners.RestDemand(github(handler), ["acme/app"], pool_labels, clock=clock)
    pool = make_pool(FakeGitHub(), clock, warm=0, maximum=1, demand=demand)
    state = pool.tick()
    assert state["queued"] == expected, "runner labels must include every job label"
    assert state["spawned"] == expected, "eligible jobs must start even with --warm 0"


@pytest.mark.parametrize("maximum,expected", [(10, 7), (9, 7), (5, 3), (2, 0)])
@pytest.mark.parametrize("online", [False, True])
def test_nine_queued_jobs_boot_the_shortfall_beyond_two_warm(maximum, expected, online, capsys):
    clock, gh = Clock(), FakeGitHub()
    jobs = []

    def handler(req):
        if req.url.path.endswith("/runs"):
            return httpx.Response(200, json={"workflow_runs": [{"id": 1}] if jobs else []})
        return httpx.Response(200, json={"jobs": jobs})

    demand = rest_demand(clock, handler)
    pool = make_pool(gh, clock, maximum=maximum, demand=demand)
    assert pool.tick()["spawned"] == 2
    if online:
        for slot in live(pool):
            gh.online(slot)
    jobs.extend({"id": i, "status": "queued", "labels": ["self-hosted", "sbx"]} for i in range(9))
    clock.now = demand.next_poll
    assert pool.tick()["spawned"] == expected
    assert len(pool.slots) == 2 + expected
    (event,) = [e for e in events(capsys) if e["event"] == "demand" and e["queued"] == 9]
    assert event["spawned"] == expected and event["max"] == maximum


def test_cancelled_run_disappears_but_only_its_owned_sandbox_is_reclaimed(monkeypatch, capsys):
    clock, gh = Clock(), FakeGitHub()
    jobs, active = [], True
    killed = []

    def handler(req):
        if req.url.path.endswith("/runs"):
            return httpx.Response(200, json={"workflow_runs": [{"id": 7}] if active else []})
        assert req.url.path == "/repos/acme/app/actions/runs/7/jobs"
        return httpx.Response(200, json={"jobs": jobs})

    demand = rest_demand(clock, handler)
    pool = make_pool(gh, clock, warm=2, maximum=2, demand=demand)
    pool.tick()
    a, b = live(pool)
    for slot in (a, b):
        gh.online(slot, busy=True)
        slot.sandbox_id = "sandbox-" + slot.name
        slot.kill = lambda s=slot: killed.append(s.name)
    jobs.extend({"id": i, "status": "in_progress", "labels": ["self-hosted", "sbx"],
                 "runner_name": s.name, "runner_id": gh.registered[s.name]["id"]}
                for i, s in enumerate((a, b)))
    clock.now = demand.next_poll
    pool.tick()
    jobs[0].update(status="completed", conclusion="cancelled", completed_at="2026-10-15T00:00:00Z")
    # Even a same-prefix foreign runner and a stale registration id must be spared.
    jobs.extend([
        {**jobs[0], "id": 3, "runner_name": "sbx-another-pool"},
        {**jobs[0], "id": 4, "runner_name": b.name, "runner_id": 999},
        {**jobs[1], "id": 5, "status": "completed", "conclusion": "success"},
    ])
    active = False  # the cancelled workflow no longer appears in active runs
    monkeypatch.setattr(runners.time, "time", lambda: 1792022403.0)

    def kill():
        killed.append(a.name)
        clock.now += 0.2

    a.kill = kill
    clock.now = demand.next_poll
    pool.tick()
    assert killed == [a.name] and a.retiring and not b.retiring
    assert a.name not in pool.slots and b.name in pool.slots
    assert gh.deleted == []  # cancellation bypasses GitHub's busy-runner delete refusal
    (reclaimed,) = [e for e in events(capsys) if e["event"] == "reclaimed"]
    assert reclaimed["job"] == 0 and reclaimed["sandbox"] == a.sandbox_id
    assert reclaimed["poll_delay_s"] == 0.2 and reclaimed["delay_s"] == 3.0


def test_job_started_and_cancelled_between_polls_reclaims_only_its_owned_runner():
    clock, registered, jobs, killed = Clock(), [], [], []

    def handler(req):
        if req.url.path.endswith("/actions/runners"):
            return httpx.Response(200, json={"runners": registered})
        if req.url.path.endswith("/runs"):
            runs = [{"id": 7}] if jobs and req.url.params["status"] == "cancelled" else []
            return httpx.Response(200, json={"workflow_runs": runs})
        assert req.url.path.endswith("/7/jobs")
        return httpx.Response(200, json={"jobs": jobs})

    demand = rest_demand(clock, handler)
    pool = make_pool(demand.gh, clock, warm=2, maximum=2, demand=demand)
    pool.tick()
    assert not demand.tracked  # no poll observes the job queued or running
    a, b = live(pool)
    for i, slot in enumerate((a, b), 1):
        registered.append({"id": i, "name": slot.name, "status": "online", "busy": True})
        slot.runner_id, slot.sandbox_id = i, "sandbox-" + slot.name
        slot.kill = lambda s=slot: killed.append(s.name)
    cancelled = {"id": 1, "status": "completed", "conclusion": "cancelled",
                 "runner_name": a.name, "runner_id": a.runner_id}
    jobs.extend([
        cancelled,
        {**cancelled, "id": 2, "runner_name": "sbx-foreign"},
        {**cancelled, "id": 3, "runner_name": b.name, "runner_id": 999},
        {**cancelled, "id": 4, "runner_name": b.name, "runner_id": b.runner_id,
         "status": "in_progress", "conclusion": None},
    ])
    for _ in range(4):
        clock.now = demand.next_poll
        pool.tick()
    assert killed == [a.name], "discover cancellations even when no poll saw the active run"
    assert a.retiring and not b.retiring


def test_cancel_discovery_pages_past_old_runs_without_fetching_their_jobs(monkeypatch):
    clock, calls, cancelled = Clock(), [], []
    monkeypatch.setattr(runners.time, "time", lambda: 1792022403.0)

    def handler(req):
        calls.append(req)
        if req.url.path.endswith("/runs"):
            if req.url.params["status"] != "cancelled":
                runs = []
            elif req.url.params["page"] == "1":
                runs = [{"id": i, "updated_at": "2020-01-01T00:00:00Z"} for i in range(100)]
            else:
                # An old workflow rerun can complete now, beyond the first page.
                runs = [{"id": 700, "created_at": "2020-01-01T00:00:00Z",
                         "updated_at": "2026-10-15T00:00:03Z"}]
            return httpx.Response(200, json={"workflow_runs": runs})
        assert req.url.path.endswith("/700/jobs")
        return httpx.Response(200, json={"jobs": [
            {"id": 7, "status": "completed", "conclusion": "cancelled"},
        ]})

    demand = rest_demand(clock, handler)
    demand.poll(lambda repo, job: cancelled.append(job["id"]))
    assert cancelled == [7], "discover recent cancellations even for old workflow reruns"
    assert sum(req.url.path.endswith("/jobs") for req in calls) == 1
    assert not demand.tracked


def test_reclaim_does_not_claim_a_failed_kill_and_retries_the_cancel(capsys):
    clock, gh = Clock(), FakeGitHub()
    job = {"id": 1, "status": "completed", "conclusion": "cancelled",
           "runner_name": "sbx-owned", "runner_id": 1}

    def handler(req):
        key = "workflow_runs" if req.url.path.endswith("/runs") else "jobs"
        return httpx.Response(200, json={key: [] if key == "workflow_runs" else [job]})

    demand = rest_demand(clock, handler)
    demand.tracked.add(("acme/app", 7))
    pool = make_pool(gh, clock, warm=0, maximum=1, demand=demand)
    kill = Blip(1, httpx.ConnectError("kill unavailable"))
    slot = runners.Slot("sbx-owned", clock(), sandbox_id="sandbox-owned", kill=kill)
    pool.slots[slot.name] = slot
    assert pool.tick()["spawned"] == 0
    assert not slot.retiring and ("acme/app", 7) in demand.tracked
    assert not [e for e in events(capsys) if e["event"] == "reclaimed"]
    clock.now = demand.next_poll
    pool.tick()
    assert slot.retiring and kill.calls == 2 and not demand.tracked
    assert len([e for e in events(capsys) if e["event"] == "reclaimed"]) == 1


@pytest.mark.parametrize("failure,delay", [("network", 5), (500, 5), (403, 60), (429, 60)])
def test_rest_errors_back_off_without_crashing_or_reusing_stale_demand(failure, delay, capsys):
    clock, calls = Clock(), []

    def handler(req):
        calls.append(req)
        if failure == "network":
            raise httpx.ConnectError("unavailable")
        return httpx.Response(failure, headers={"Retry-After": "60"} if failure in (403, 429) else {})

    demand = rest_demand(clock, handler)
    demand.backlog = 9
    assert demand.poll(lambda *a: None) == 0
    assert demand.next_poll == clock() + delay
    assert demand.poll(lambda *a: None) == 0 and len(calls) == 1
    with pytest.raises(runners.RunnerError, match="backing off"):
        demand.gh.get("/repos/acme/app/actions/runs")
    assert len(calls) == 1
    clock.now = demand.next_poll
    assert demand.poll(lambda *a: None) == 0 and len(calls) == 2
    assert demand.next_poll - clock() >= delay
    assert len([e for e in events(capsys) if e["event"] == "poll_error"]) == 2


@pytest.mark.parametrize("failure", [403, 500, "network"])
def test_demand_failures_do_not_block_warm_cleanup_or_drain(failure):
    clock, calls, killed = Clock(), [], []
    registered = []

    def handler(req):
        calls.append(req)
        if req.url.path.endswith("/actions/runners"):
            return httpx.Response(200, json={"runners": registered})
        if req.method == "DELETE":
            return httpx.Response(204)
        if failure == "network":
            raise httpx.ConnectError("workflow API unavailable")
        return httpx.Response(failure)

    demand = rest_demand(clock, handler)
    pool = make_pool(demand.gh, clock, warm=1, maximum=1, demand=demand)

    def tick():
        try:
            return pool.tick()
        except runners.RunnerError as exc:
            pytest.fail(f"demand errors must not disable healthy runner control: {exc}")

    for _ in range(3):
        assert tick()["spawned"] == 1, "warm pool must refill during demand failures"
        (slot,) = live(pool)
        slot.sandbox_id, slot.done = "sandbox-finished", True
        clock.now = demand.next_poll
    assert tick()["spawned"] == 1
    (slot,) = live(pool)
    slot.kill = lambda: killed.append(slot.name)
    registered.append({"id": 1, "name": slot.name, "status": "online", "busy": False})
    pool.drain()
    assert slot.retiring and killed == [slot.name], "shutdown must work during demand backoff"
    assert sum(req.url.path.endswith("/actions/runners") for req in calls) == 5


def test_explicit_rate_limit_still_backs_off_runner_control():
    clock = Clock()
    demand = rest_demand(clock, lambda req: httpx.Response(429, headers={"Retry-After": "60"}))
    demand.poll(lambda *a: None)
    with pytest.raises(runners.RunnerError, match="backing off"):
        demand.gh.runners("sbx-")


@pytest.mark.parametrize("missing_page", [1, 2])
def test_deleted_tracked_run_is_forgotten_without_blocking_later_runs(missing_page):
    clock, calls = Clock(), []

    def handler(req):
        calls.append(req)
        if req.url.path.endswith("/runs"):
            return httpx.Response(200, json={"workflow_runs": [{"id": 2}]})
        if req.url.path.endswith("/1/jobs"):
            if int(req.url.params["page"]) == missing_page:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"jobs": [{"status": "completed"}] * 100})
        assert req.url.path.endswith("/2/jobs")
        return httpx.Response(200, json={"jobs": [
            {"id": 20, "status": "queued", "labels": ["self-hosted", "sbx"]},
        ]})

    demand = rest_demand(clock, handler)
    demand.tracked.add(("acme/app", 1))
    for _ in range(3):
        assert demand.poll(lambda *a: None) == 1, "a deleted run must not hide healthy demand"
        assert ("acme/app", 1) not in demand.tracked, "forget deleted tracked runs"
        clock.now = demand.next_poll
    assert sum(req.url.path.endswith("/1/jobs") for req in calls) == missing_page
    assert sum(req.url.path.endswith("/2/jobs") for req in calls) == 3


def test_rate_limit_reset_is_respected(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(runners.time, "time", lambda: 100)
    demand = rest_demand(clock, lambda req: httpx.Response(
        403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "220"}))
    assert demand.poll(lambda *a: None) == 0
    assert demand.next_poll == clock() + 120


def test_conditional_reads_reuse_304_bodies_and_obey_cost_aware_interval():
    clock, requests = Clock(), []
    seen = set()

    def handler(req):
        requests.append(req)
        key = str(req.url)
        if key in seen:
            assert req.headers["If-None-Match"] == '"v1"'
            return httpx.Response(304)
        seen.add(key)
        assert "If-None-Match" not in req.headers
        if req.url.path.endswith("/runs"):
            body = {"workflow_runs": [{"id": 1}]}  # deduplicated across queued/in_progress
        else:
            body = {"jobs": [{"id": 1, "status": "queued", "labels": ["self-hosted", "SBX"]}]}
        return httpx.Response(200, json=body, headers={"ETag": '"v1"'})

    demand = rest_demand(clock, handler)
    assert demand.poll(lambda *a: None) == 1 and len(requests) == 3
    assert demand.next_poll == clock() + 6
    clock.now += 5
    assert demand.poll(lambda *a: None) == 1 and len(requests) == 3
    clock.now += 1
    assert demand.poll(lambda *a: None) == 1 and len(requests) == 6


def test_default_discovery_is_capped_recent_and_refreshed():
    clock, calls = Clock(), []

    def handler(req):
        calls.append(req)
        if req.url.path == "/orgs/acme/repos":
            assert req.url.params["per_page"] == "20" and req.url.params["sort"] == "pushed"
            return httpx.Response(200, json=[{"full_name": "acme/new"}, {"full_name": "acme/old"}])
        if "created" in req.url.params:
            assert req.url.params["created"].startswith(">=")
            return httpx.Response(200, json={"workflow_runs": [{"id": 1}] if "/new/" in req.url.path else []})
        assert "/old/" not in req.url.path
        return httpx.Response(200, json={"workflow_runs": []})

    demand = rest_demand(clock, handler, repos=[])
    assert demand.poll(lambda *a: None) == 0
    assert demand.repos == ["acme/new"]
    clock.now = demand.next_poll
    demand.poll(lambda *a: None)
    assert sum(r.url.path == "/orgs/acme/repos" for r in calls) == 1
    clock.now += 300
    demand.poll(lambda *a: None)
    assert sum(r.url.path == "/orgs/acme/repos" for r in calls) == 2


def test_active_run_pagination_is_not_limited_to_fifty_runs():
    clock = Clock()

    def handler(req):
        if req.url.path.endswith("/runs"):
            ids = range(100) if req.url.params["page"] == "1" else [100]
            return httpx.Response(200, json={"workflow_runs": [{"id": i} for i in ids]})
        return httpx.Response(200, json={"jobs": [{"id": req.url.path, "status": "queued",
                                                  "labels": ["self-hosted", "sbx"]}]})

    demand = rest_demand(clock, handler)
    assert demand.poll(lambda *a: None) == 101


@pytest.mark.parametrize("repos", [["bad"], [f"acme/repo{i}" for i in range(21)]])
def test_watch_repo_validation_is_local(repos, monkeypatch, capsys):
    monkeypatch.setenv("E2B_API_KEY", "e2b-test-key")
    monkeypatch.setenv("GH_TOKEN", "gh-test-token")
    argv = [arg for repo in repos for arg in ("--watch-repo", repo)]
    assert cli.main(serve_argv(*argv)) == 2
    assert "--watch-repo" in capsys.readouterr().err
