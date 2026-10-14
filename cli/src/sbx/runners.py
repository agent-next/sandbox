"""GitHub Actions runners on sandboxes: one disposable sandbox per job.

`sbx runners image` bakes a snapshot with the official actions/runner and a
running Docker daemon. `sbx runners serve` keeps a warm pool of single-use
(JIT) runners registered on that snapshot: a queued job lands on an idle
runner at once, the runner exits after that one job, its sandbox is killed and
the pool refills. Every state change is one JSON line on stdout.
"""

from __future__ import annotations

import hashlib
import re
import hmac
import json
import os
import secrets
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

import httpx

from .cli import SbxError as RunnerError
from .cli import _scrub

RUNNER_DIR = "/opt/actions-runner"
GITHUB_API = "https://api.github.com"

# The sandbox init is not systemd, so nothing starts dockerd on its own.
RUNNER_USER = "user"  # the runner drops to this account (passwordless sudo, docker), like GitHub's
RUNNER_PACKAGES = (
    "sudo curl git ca-certificates lsb-release gnupg build-essential python3 python3-venv python3-pip "
    "jq unzip zip wget xz-utils pkg-config file rsync openssh-client zstd "
    "libgl1 libglib2.0-0 libsm6 libxext6 libxrender1"  # native deps of opencv/matplotlib-style wheels
)

TOOL_CACHE = "/opt/hostedtoolcache"  # where GitHub's image keeps them; setup-python/-node look here first
# the newest stable build per minor, from the same sources actions/setup-python and setup-node download
TOOLCACHE_PYTHON = (
    "manifest=$(curl -fsSL https://raw.githubusercontent.com/actions/python-versions/main/versions-manifest.json) "
    "&& for v in 3.12 3.13; do url=$(echo \"$manifest\" | python3 -c '"
    "import json, sys; v = sys.argv[1]; print(next(f[\"download_url\"] for r in json.load(sys.stdin) "
    "if r[\"stable\"] and r[\"version\"].startswith(v + \".\") for f in r[\"files\"] "
    "if f[\"platform\"] == \"linux\" and f.get(\"platform_version\") == \"24.04\" and f[\"arch\"] == \"x64\"))' $v) "
    "&& d=$(mktemp -d) && curl -fsSL \"$url\" | tar xz -C $d && (cd $d && bash setup.sh >/dev/null) && rm -rf $d || exit 1; done"
)
TOOLCACHE_NODE = (
    "index=$(curl -fsSL https://nodejs.org/dist/index.json) "
    "&& for v in 20 22; do ver=$(echo \"$index\" | python3 -c '"
    "import json, sys; print(next(r[\"version\"] for r in json.load(sys.stdin) if r[\"version\"].startswith(\"v\" + sys.argv[1] + \".\")))' $v) "
    f"&& d={TOOL_CACHE}/node/${{ver#v}}/x64 && mkdir -p $d "
    "&& curl -fsSL https://nodejs.org/dist/$ver/node-$ver-linux-x64.tar.gz | tar xz -C $d --strip-components=1 "
    "&& touch $d.complete || exit 1; done"
)

DOCKER_UP = (
    "pgrep -x dockerd >/dev/null || (sudo nohup dockerd >/tmp/dockerd.log 2>&1 &); "
    "for _ in $(seq 100); do [ -S /var/run/docker.sock ] && break; sleep 0.1; done; "
    "sudo chmod 666 /var/run/docker.sock"
)


_emit_lock = threading.RLock()  # reentrant: the signal handler emits from the main thread


def emit(event: str, **fields) -> None:
    """One scrubbed JSON line per event; boot, webhook and main threads all emit."""
    line = _scrub(json.dumps({"t": round(time.time(), 3), "event": event, **fields})) + "\n"
    with _emit_lock:
        sys.stdout.write(line)
        sys.stdout.flush()


class GitHub:
    """The few GitHub REST calls a JIT runner pool needs."""

    def __init__(self, token: str, scope: str, client: httpx.Client | None = None):
        # scope: "orgs/<org>" or "repos/<owner>/<repo>"
        self.scope = scope
        self.http = client or httpx.Client(
            base_url=GITHUB_API,
            timeout=30,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def _check(self, resp: httpx.Response, what: str) -> httpx.Response:
        if resp.status_code >= 400:
            raise RunnerError(f"GitHub {what} failed: HTTP {resp.status_code} {resp.text[:200]}")
        return resp

    def check_repo(self, repo: str) -> None:
        self._check(self.http.get(f"/repos/{repo}"), f"read repo {repo}")

    def jit(self, name: str, labels: list[str], group_id: int) -> str:
        resp = self.http.post(
            f"/{self.scope}/actions/runners/generate-jitconfig",
            json={"name": name, "runner_group_id": group_id, "labels": labels, "work_folder": "_work"},
        )
        return self._check(resp, "generate-jitconfig").json()["encoded_jit_config"]

    def runners(self, prefix: str) -> dict[str, dict]:
        """Registered runners whose name starts with prefix, by name."""
        out: dict[str, dict] = {}
        page = 1
        while True:
            resp = self.http.get(f"/{self.scope}/actions/runners", params={"per_page": 100, "page": page})
            batch = self._check(resp, "list runners").json()["runners"]
            out.update({r["name"]: r for r in batch if r["name"].startswith(prefix)})
            if len(batch) < 100:
                return out
            page += 1

    def delete(self, runner_id: int) -> bool:
        """Deregister an idle runner. False when GitHub refuses because it is running a job."""
        resp = self.http.delete(f"/{self.scope}/actions/runners/{runner_id}")
        if resp.status_code == 422:
            return False
        if resp.status_code == 404:
            return True
        self._check(resp, "delete runner")
        return True

    def queued(self, repos: list[str], labels: list[str]) -> int:
        """Queued jobs in repos whose runs-on labels are all served by this pool."""
        want = {label.lower() for label in labels}
        count = 0
        for repo in repos:
            for status in ("queued", "in_progress"):
                resp = self.http.get(f"/repos/{repo}/actions/runs", params={"status": status, "per_page": 50})
                for run in self._check(resp, "list runs").json()["workflow_runs"]:
                    page = 1
                    while True:
                        resp = self.http.get(f"/repos/{repo}/actions/runs/{run['id']}/jobs",
                                             params={"per_page": 100, "page": page})
                        jobs = self._check(resp, "list jobs").json()["jobs"]
                        count += sum(1 for job in jobs if job["status"] == "queued"
                                     and {x.lower() for x in job["labels"]} <= want)
                        if len(jobs) < 100:
                            break
                        page += 1
        return count


@dataclass
class Slot:
    name: str
    born: float
    online_at: float | None = None
    gone_since: float | None = None
    idle_since: float | None = None
    busy: bool = False
    done: bool = False
    retiring: bool = False
    sandbox_id: str | None = None
    kill: Callable[[], None] | None = field(default=None, repr=False)


class Pool:
    """Warm pool of single-job runners. tick() is the whole control loop; boot() runs one slot."""

    def __init__(
        self,
        gh: GitHub,
        boot: Callable[[Slot], None],
        *,
        warm: int,
        maximum: int,
        prefix: str = "sbx-",
        idle_ttl: float = 1800,
        start_ttl: float = 180,
        scale_down_after: float = 60,
        boot_backoff: float = 15,
        queued: Callable[[], int] = lambda: 0,
        queued_is_cheap: bool = False,
        clock: Callable[[], float] = time.monotonic,
        spawn: Callable[[Callable[[], None]], None] | None = None,
    ):
        if warm < 0 or maximum < 1 or warm > maximum:
            raise RunnerError("need 0 <= --warm <= --max and --max >= 1")
        self.gh, self.boot = gh, boot
        self.warm, self.maximum, self.prefix = warm, maximum, prefix
        self.idle_ttl, self.start_ttl, self.scale_down_after = idle_ttl, start_ttl, scale_down_after
        self.boot_backoff, self.backoff_until = boot_backoff, 0.0
        self.queued, self.queued_is_cheap, self.clock = queued, queued_is_cheap, clock
        self.spawn = spawn or (lambda fn: threading.Thread(target=fn, daemon=True).start())
        self.slots: dict[str, Slot] = {}
        self.lock = threading.Lock()

    def _new_slot(self) -> None:
        slot = Slot(f"{self.prefix}{secrets.token_hex(4)}", self.clock())
        self.slots[slot.name] = slot
        emit("spawn", runner=slot.name)

        def run():
            try:
                self.boot(slot)
            except Exception as exc:  # one bad sandbox must not stop the pool
                if not slot.retiring:  # a retire racing the boot is not a boot failure
                    # e.g. the key's concurrent-sandbox quota: retrying at once only repeats the 429
                    self.backoff_until = self.clock() + self.boot_backoff
                    emit("boot_error", runner=slot.name, error=f"{type(exc).__name__}: {str(exc)[:300]}")
            finally:
                slot.done = True

        self.spawn(run)

    def retire(self, slot: Slot, registered: dict | None, why: str) -> bool:
        """Deregister then kill. A runner GitHub reports busy is left alone."""
        if registered is not None and not self.gh.delete(registered["id"]):
            return False
        slot.retiring = True
        if slot.kill:
            slot.kill()
        emit("retire", runner=slot.name, why=why, sandbox=slot.sandbox_id)
        return True

    def tick(self) -> dict:
        now = self.clock()
        seen = self.gh.runners(self.prefix)
        with self.lock:
            # a retired slot's sandbox is killed (or its boot() kills it right after create)
            for name in [n for n, s in self.slots.items() if s.done or s.retiring]:
                if self.slots[name].sandbox_id:
                    self.backoff_until = 0.0  # a sandbox was freed: quota room again
                del self.slots[name]
            # registrations under our prefix with no slot were left by an earlier serve that died
            # without draining; offline ones are dead weight against the org's runner limit
            for name, reg in seen.items():
                if name not in self.slots and reg["status"] == "offline" and not reg["busy"]:
                    if self.gh.delete(reg["id"]):
                        emit("orphan_removed", runner=name)
            starting, idle, busy = [], [], []
            for slot in self.slots.values():
                if slot.retiring:
                    continue
                reg = seen.get(slot.name)
                if reg is None or reg["status"] != "online":
                    if slot.online_at is None:
                        if now - slot.born > self.start_ttl:
                            self.retire(slot, reg, "start_timeout")
                        else:
                            starting.append(slot)
                        continue
                    # online once, now gone: the job finished and boot() is cleaning up. If boot()
                    # never reports back (the sandbox died under the job), stop counting the slot.
                    slot.gone_since = slot.gone_since or now
                    if now - slot.gone_since > self.start_ttl:
                        self.retire(slot, None, "lost")
                    continue
                slot.gone_since = None
                if slot.online_at is None:
                    slot.online_at = now
                    emit("online", runner=slot.name, boot_s=round(now - slot.born, 2))
                if reg["busy"]:
                    if not slot.busy:
                        emit("busy", runner=slot.name)
                    slot.busy, slot.idle_since = True, None
                    busy.append(slot)
                else:
                    slot.idle_since = slot.idle_since or now
                    idle.append((slot, reg))

            # idle runners absorb queued jobs on their own; a polled backlog costs GitHub API
            # calls, so it is only counted once the pool is empty and can still grow (a webhook
            # count is free)
            full = sum(1 for s in self.slots.values() if not s.retiring) >= self.maximum
            backlog = self.queued() if self.queued_is_cheap or not (starting or idle or full) else 0
            excess = len(idle) - (self.warm + backlog)
            for slot, reg in sorted(idle, key=lambda x: x[0].idle_since):
                idle_for = now - slot.idle_since
                if idle_for > self.idle_ttl:
                    why = "idle_ttl"
                elif excess > 0 and idle_for > self.scale_down_after:
                    why = "scale_down"
                else:
                    continue
                if self.retire(slot, reg, why):
                    excess -= 1
            ready = len(starting) + sum(1 for s, _ in idle if not s.retiring)
            live = sum(1 for s in self.slots.values() if not s.retiring)
            need = min(self.maximum - live, self.warm + backlog - ready)
            if now < self.backoff_until:
                need = 0
            for _ in range(max(0, need)):
                self._new_slot()
            return {"starting": len(starting), "idle": ready - len(starting), "busy": len(busy),
                    "queued": backlog, "spawned": max(0, need)}

    def abort(self) -> None:
        """Kill every sandbox, busy ones included; their jobs fail.

        Lock-free on purpose: it runs in the signal handler, on the main thread, which may be
        inside tick() or drain() holding self.lock across GitHub calls."""
        for slot in list(self.slots.values()):
            if not slot.done and not slot.retiring:
                slot.retiring = True
                if slot.kill:
                    slot.kill()
                emit("retire", runner=slot.name, why="abort", sandbox=slot.sandbox_id)

    def drain(self) -> None:
        """Retire every slot not running a job; busy ones finish their job first."""
        seen = self.gh.runners(self.prefix)
        with self.lock:
            for slot in list(self.slots.values()):
                if not slot.done and not slot.retiring:
                    self.retire(slot, seen.get(slot.name), "shutdown")


def sweep(gh: GitHub, sandbox_cls, prefix: str) -> None:
    """Clear what an earlier serve with this prefix left behind (it was killed or crashed).

    Its idle runners are deregistered and their sandboxes killed. Runners still on a job are
    left to finish; their sandbox lifetime bounds them. Two live pools must not share a prefix.
    """
    seen = gh.runners(prefix)
    busy = {name for name, reg in seen.items() if reg["busy"]}
    for name, reg in seen.items():
        if name in busy:
            continue
        if gh.delete(reg["id"]):
            emit("orphan_removed", runner=name)
        else:  # 422: it took a job after the listing, so its sandbox must live
            busy.add(name)
    listing = sandbox_cls.list()
    while listing.has_next:
        for info in listing.next_items():
            name = (info.metadata or {}).get("sbx-runner", "")
            if name.startswith(prefix) and name not in busy:
                sandbox_cls.kill(info.sandbox_id)
                emit("orphan_killed", runner=name, sandbox=info.sandbox_id)


def sandbox_boot(gh: GitHub, sandbox_cls, *, snapshot: str, labels: list[str], group_id: int,
                 job_timeout_s: int, idle_ttl_s: int) -> Callable[[Slot], None]:
    """boot() for Pool: JIT-register, start the runner in a fresh sandbox, kill it after one job."""

    lifetime = job_timeout_s + idle_ttl_s + 300

    def boot(slot: Slot) -> None:
        # sandbox first: a failed create (e.g. quota 429) must not leave a registered runner behind
        sbx = sandbox_cls.create(
            snapshot,
            timeout=lifetime,
            metadata={"sbx-runner": slot.name},
            lifecycle={"on_timeout": "kill"},
        )
        slot.sandbox_id = sbx.sandbox_id
        slot.kill = sbx.kill
        emit("sandbox", runner=slot.name, sandbox=sbx.sandbox_id, create_s=round(time.monotonic() - slot.born, 2))
        try:
            if slot.retiring:
                return
            sbx.files.write("/tmp/jit", gh.jit(slot.name, labels, group_id))
            run = (
                # .env: the runner hands these to every job, so a job can name its sandbox
                f"{DOCKER_UP}; cd {RUNNER_DIR} && echo \"E2B_SANDBOX_ID=$E2B_SANDBOX_ID\" >> .env "
                f"&& jit=$(cat /tmp/jit) && rm -f /tmp/jit "
                f'&& exec sudo -n -u {RUNNER_USER} -H ./run.sh --jitconfig "$jit"'
            )
            # bounded like the sandbox: a stream from a sandbox killed under the job never ends
            handle = sbx.commands.run(run, background=True, timeout=lifetime, user="root")
            _wait_runner(sbx, handle, slot, deadline=time.monotonic() + lifetime)
        finally:
            _kill(sbx, slot)

    return boot


def _error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc)[:200]}"


def _wait_runner(sbx, handle, slot: Slot, *, deadline: float, outage: float = 600) -> None:
    """Wait for the runner to exit. A dropped stream (gateway restart, network) is not an exit:
    reattach to the runner process, or a blip would kill the job it is running. Reattaching
    gives up after `outage` seconds without a connection."""
    from e2b import CommandExitException, NotFoundException, TimeoutException

    pid = handle.pid
    while True:
        try:
            emit("runner_exit", runner=slot.name, code=handle.wait().exit_code)
            return
        except (CommandExitException, TimeoutException) as exc:
            if not slot.retiring:
                emit("runner_exit", runner=slot.name, error=_error(exc))
            return
        except Exception as exc:
            if slot.retiring:  # killed on retire
                return
            emit("stream_lost", runner=slot.name, error=_error(exc))
        delay, give_up = 2, min(deadline, time.monotonic() + outage)
        while True:
            if time.monotonic() >= give_up:
                emit("runner_exit", runner=slot.name, error="could not reattach to the runner")
                return
            try:
                handle = sbx.commands.connect(pid, timeout=max(1, deadline - time.monotonic()))
                break
            except (NotFoundException, TimeoutException) as exc:  # the runner (or its sandbox) is gone
                emit("runner_exit", runner=slot.name, error=_error(exc))
                return
            except Exception:
                time.sleep(delay)
                delay = min(delay * 2, 15)


def _kill(sbx, slot: Slot) -> None:
    """Kill with retries: a kill lost to a gateway blip leaves the sandbox holding a quota slot
    until its lifetime ends. A kill that never lands is reported, not claimed."""
    for delay in (0, 2, 4, 8, 15, 30, 60):
        time.sleep(delay)
        try:
            sbx.kill()
        except Exception as exc:
            error = _error(exc)
            continue
        emit("killed", runner=slot.name, sandbox=sbx.sandbox_id)
        return
    emit("kill_failed", runner=slot.name, sandbox=sbx.sandbox_id, error=error)


def ensure_template(http: httpx.Client, *, image: str, size: str, poll_s: float = 5,
                    wait_s: float = 900) -> str:
    """The key's own template imported from a public image (`http`: the sandbox API, key set).
    Registered once per key and image, then reused; a failed import is deleted again."""
    alias = f"sbx-runner-{re.sub(r'[^a-z0-9]+', '-', image.lower()).strip('-')}-{size}"

    def check(resp: httpx.Response, what: str) -> httpx.Response:
        if resp.status_code >= 400:
            raise RunnerError(f"template {what} failed: HTTP {resp.status_code} {resp.text[:200]}")
        return resp

    if http.get(f"/templates/aliases/{alias}").status_code == 200:
        return alias
    reg = check(http.post("/v3/templates", json={"name": alias, "resourceClass": size}), "register").json()
    tid, bid = reg["templateID"], reg["buildID"]
    emit("template", template=alias, image=image, size=size)
    try:
        check(http.post(f"/v2/templates/{tid}/builds/{bid}", json={"fromImage": image}), "import")
        deadline = time.monotonic() + wait_s
        while True:
            status = check(http.get(f"/templates/{tid}/builds/{bid}/status"), "status").json().get("status")
            if status == "ready":
                return alias
            if status not in ("waiting", "building", "pending") or time.monotonic() > deadline:
                raise RunnerError(f"template import of {image} ended {status!r}")
            time.sleep(poll_s)
    except BaseException:
        http.delete(f"/templates/{tid}")
        raise


def build_image(sandbox_cls, *, template: str | None, runner_version: str) -> str:
    """Bake the runner snapshot: actions/runner + its deps + a running dockerd."""
    if not re.fullmatch(r"\d+(\.\d+)*", runner_version):
        raise RunnerError(f"not an actions/runner version: {runner_version!r}")
    url = (
        f"https://github.com/actions/runner/releases/download/v{runner_version}/"
        f"actions-runner-linux-x64-{runner_version}.tar.gz"
    )
    sbx = sandbox_cls.create(template, timeout=1800, lifecycle={"on_timeout": "kill"})
    emit("image_sandbox", sandbox=sbx.sandbox_id, runner_version=runner_version)
    try:
        steps = [
            "export DEBIAN_FRONTEND=noninteractive; apt-get update -qq "
            f"&& apt-get install -y -qq --no-install-recommends {RUNNER_PACKAGES} >/dev/null",
            # sudo warns on every call when the hostname does not resolve
            'grep -q "$(hostname)" /etc/hosts || echo "127.0.1.1 $(hostname)" >> /etc/hosts',
            f"id {RUNNER_USER} >/dev/null 2>&1 || useradd -m -s /bin/bash {RUNNER_USER}; "
            f"echo '{RUNNER_USER} ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/sbx-runner && chmod 440 /etc/sudoers.d/sbx-runner",
            "command -v dockerd >/dev/null || (curl -fsSL https://get.docker.com | sh >/tmp/docker.log 2>&1 "
            "|| (tail -20 /tmp/docker.log; false))",
            f"groupadd -f docker && usermod -aG docker {RUNNER_USER}",
            f"mkdir -p {RUNNER_DIR} && cd {RUNNER_DIR} && curl -fsSL {url} | tar xz "
            f"&& chown -R {RUNNER_USER}: {RUNNER_DIR}",
            f"cd {RUNNER_DIR} && ./bin/installdependencies.sh >/tmp/deps.log 2>&1 || (tail -20 /tmp/deps.log; false)",
            f"export AGENT_TOOLSDIRECTORY={TOOL_CACHE} && mkdir -p {TOOL_CACHE} && {TOOLCACHE_PYTHON}",
            f"{TOOLCACHE_NODE} && chown -R {RUNNER_USER}: {TOOL_CACHE} "
            f"&& echo AGENT_TOOLSDIRECTORY={TOOL_CACHE} > {RUNNER_DIR}/.env",
            DOCKER_UP,
            "docker run --rm hello-world >/dev/null && docker image rm hello-world >/dev/null",
        ]
        for step in steps:
            sbx.commands.run(step, timeout=600, user="root")
            emit("image_step", done=step.split("&&")[0][:60])
        snap = sbx.create_snapshot()
    finally:
        sbx.kill()
    snapshot_id = getattr(snap, "snapshot_id", None) or getattr(snap, "id", None) or str(snap)
    emit("image", snapshot=snapshot_id)
    return snapshot_id


def latest_runner_version(http: httpx.Client) -> str:
    resp = http.get(f"{GITHUB_API}/repos/actions/runner/releases/latest", timeout=30)
    if resp.status_code != 200:
        raise RunnerError(f"cannot read the latest actions/runner release: HTTP {resp.status_code}")
    return resp.json()["tag_name"].lstrip("v")


def github_token() -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RunnerError("no GitHub token: export GH_TOKEN with admin rights on the org or repo")
    return token


class JobQueue:
    """Queued jobs this pool can serve, kept current from workflow_job webhooks."""

    def __init__(self, secret: str, labels: list[str], on_change: Callable[[], None] = lambda: None,
                 ttl: float = 900, clock: Callable[[], float] = time.monotonic):
        self.secret = secret.encode()
        self.labels = {label.lower() for label in labels}
        self.on_change, self.ttl, self.clock = on_change, ttl, clock
        self.jobs: dict[int, float] = {}  # job id -> when it was queued
        self.lock = threading.Lock()

    def __len__(self) -> int:
        """Jobs still waiting. A job whose start/finish delivery was lost expires after ttl."""
        with self.lock:
            cutoff = self.clock() - self.ttl
            self.jobs = {j: t for j, t in self.jobs.items() if t > cutoff}
            return len(self.jobs)

    def handle(self, event: str, signature: str, body: bytes) -> int:
        """Apply one delivery; returns the HTTP status to answer with."""
        expected = "sha256=" + hmac.new(self.secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature or ""):
            return 401
        if event != "workflow_job":
            return 204
        try:
            payload = json.loads(body)
            action, job = payload["action"], payload["workflow_job"]
            jid, labels = job["id"], {x.lower() for x in job["labels"]}
            if not isinstance(jid, int):
                raise TypeError("job id")
        except (ValueError, KeyError, TypeError, AttributeError):
            return 400
        if not labels <= self.labels:
            return 204
        with self.lock:
            if action == "queued":
                self.jobs[jid] = self.clock()
            else:
                self.jobs.pop(jid, None)
            waiting = len(self.jobs)
        emit("webhook", action=action, job=jid, queued=waiting)
        self.on_change()
        return 204


def webhook_server(queue: JobQueue, host: str, port: int) -> ThreadingHTTPServer:
    """Serve POST deliveries for queue on host:port (in a daemon thread)."""

    class Handler(BaseHTTPRequestHandler):
        timeout = 30  # a client that stalls mid-body must not hold a thread forever

        def do_POST(self):
            try:
                size = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                size = -1
            try:
                if size < 0:
                    status = 400
                elif size > 5_000_000:
                    status = 413
                else:
                    status = queue.handle(self.headers.get("X-GitHub-Event", ""),
                                          self.headers.get("X-Hub-Signature-256", ""), self.rfile.read(size))
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()
            except OSError:  # the client went away or stalled past the timeout
                self.close_connection = True

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    emit("webhook_listen", host=host, port=server.server_address[1])
    return server


def serve(pool: Pool, *, interval: float, stop: threading.Event, wake: threading.Event | None = None) -> None:
    """Run the pool until stop is set; wake (set by webhook deliveries) forces an early tick."""
    wake = wake or threading.Event()

    def on_signal(signum, _frame):
        emit("signal", signal=signum)
        if stop.is_set():  # a second Ctrl-C: stop waiting for busy runners
            pool.abort()
        stop.set()
        wake.set()

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    emit("serve", warm=pool.warm, max=pool.maximum, prefix=pool.prefix)
    last = None
    while not stop.is_set():
        wake.clear()  # before the tick: a delivery during it still cuts the next wait short
        try:
            state = pool.tick()
            if state != last:
                emit("pool", **state)
                last = state
        except Exception as exc:  # GitHub/gateway hiccup: keep serving
            emit("tick_error", error=f"{type(exc).__name__}: {str(exc)[:200]}")
        if not stop.is_set():
            wake.wait(interval)
    pool.drain()
    # retired sandboxes are already killed; only runners still on a job are waited for
    while any(not s.done and not s.retiring for s in pool.slots.values()):
        time.sleep(1)
    emit("stopped")
