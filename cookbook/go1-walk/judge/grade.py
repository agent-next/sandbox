#!/usr/bin/env python3
"""Grade a go1-walk artifact on a fresh GPU lease (stdlib only).

    python3 grade.py <artifact_dir> [--seed S] [--json out.json]
        [--episodes N] [--steps N] [--mass-scale M] [--vram GB] [--keep]

<artifact_dir> must contain policy.npz (actor weights). The judge ships
env.py + the Go1 model + this judge's evaluator (_eval.py) to a 4 GiB
VRAM-slice lease, simulates the policy on held-out seeds, and writes one
JSON verdict. Everything the artifact claims is ignored: the judge
re-measures every gated number itself.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = "https://api.sbx.agent-next.com"
HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)

JOB = """
import base64, hashlib, json, os, subprocess, sys, time
FILES = __PAYLOAD__
ARGS = __ARGS__
POLICY_SOURCE = __REMOTE_POLICY__
ROOT = os.path.expanduser('~/go1judge')
os.makedirs(os.path.join(ROOT, 'model'), exist_ok=True)
os.chdir(ROOT)
for name, b64 in FILES.items():
    sub = 'model' if name.endswith('.xml') else ''
    d = os.path.join(ROOT, sub)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), 'wb') as fh:
        fh.write(base64.b64decode(b64))
if POLICY_SOURCE is not None:
    import shutil
    shutil.copyfile(os.path.expanduser(POLICY_SOURCE), 'policy.npz')
for m in ('env', '_eval'):
    sys.modules.pop(m, None)
protected = [n for n in FILES if n != 'policy.npz']
def hashes():
    return {n: hashlib.sha256(open(os.path.join(ROOT, 'model' if
             n.endswith('.xml') else '', n), 'rb').read()).hexdigest()
            for n in protected}
before = hashes()
if os.path.exists('verdict_out.json'):
    os.unlink('verdict_out.json')
t0 = time.time()
proc = subprocess.run([sys.executable, '_eval.py'] + ARGS,
                      capture_output=True, text=True, timeout=600)
report['rc'] = proc.returncode
report['stdout_tail'] = proc.stdout[-3000:]
report['stderr_tail'] = proc.stderr[-2000:]
report['eval_wall_s'] = round(time.time() - t0, 1)
try:
    report['verdict'] = json.load(open('verdict_out.json'))
    report['verdict']['judge_intact'] = before == hashes()
    if not report['verdict']['judge_intact']:
        report['verdict']['ok'] = False
except Exception as exc:
    report['verdict'] = None
    report['verdict_error'] = str(exc)
"""


def die(msg, code=1):
    print(f"grade.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def request(key, method, path, body=None, timeout=900):
    data = None if body is None else json.dumps(body).encode()
    r = Request(API + path, data=data, method=method,
                headers={"X-API-Key": key, "Content-Type": "application/json"})
    last = None
    error = None
    for attempt in range(12 if method == "POST" else 5):
        try:
            with urlopen(r, timeout=timeout) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if raw else None
        except HTTPError as exc:
            raw = exc.read()
            try:
                error = json.loads(raw) if raw else None
            except ValueError:
                error = None
            # A lost POST reply is ambiguous: never resend an operation
            # that could have created a lease or already executed code.
            capacity = (exc.code == 503 and isinstance(error, dict) and
                        str(error.get("message", "")).startswith("GPU plane at capacity"))
            if exc.code == 409 or capacity or (method in ("GET", "DELETE") and
                                               500 <= exc.code < 600):
                if isinstance(error, dict) and "failed" in str(error.get("message", "")):
                    return exc.code, error
                last = exc
                time.sleep(min(5 * (attempt + 1), 30))
                continue
            return exc.code, error
    return last.code, error


def check_lease_id(sid):
    return isinstance(sid, str) and sid.startswith("gl-") and all(
        c.isascii() and (c.isalnum() or c == "-") for c in sid)


class Lease:
    """A VRAM-slice lease; always delete() in a finally."""

    def __init__(self, key, vram_gb=4):
        self.key, self.vram_gb = key, vram_gb
        self.id = None
        self.events = []
        self._stop = threading.Event()
        self._heartbeat = None

    def __enter__(self):
        t0 = time.monotonic()
        while True:
            st, created = request(self.key, "POST", "/sandboxes", {
                "timeout": 7200,
                "accel": {"vram_gb": self.vram_gb, "reserve": "exec"}})
            if st == 201 and isinstance(created, dict):
                break
            # the API key allows a bounded number of concurrent leases;
            # a 409 means the slots are busy — retry briefly
            wait = float(os.environ.get("GO1_LEASE_WAIT_S", "300"))
            if st == 409 and time.monotonic() - t0 < wait:
                time.sleep(20)
                continue
            die(f"GPU lease create: HTTP {st}; check GPU access "
                "and capacity")
        sid = created.get("sandboxID")
        if not check_lease_id(sid):
            die("GPU create returned an invalid lease id; no unvalidated "
                "cleanup URL was requested. Inspect your owned inventory.")
        self.id = sid
        self._heartbeat = threading.Thread(target=self._watch, daemon=True)
        self._heartbeat.start()
        return self

    def _watch(self):
        """Keep observing only our lease while long calls are in flight."""
        while not self._stop.wait(15):
            sid = self.id
            if sid is None:
                return
            try:
                status, body = request(self.key, "GET", f"/sandboxes/{sid}",
                                       timeout=20)
                self.events.append({"kind": "heartbeat", "status": status,
                                    "phase": (body or {}).get("phase")
                                    if isinstance(body, dict) else None})
            except Exception:
                self.events.append({"kind": "heartbeat", "status": "transport_error"})

    def exec(self, code, timeout_s=600):
        t0 = time.monotonic()
        st, r = request(self.key, "POST", f"/sandboxes/{self.id}/exec",
                        {"code": code, "timeout_s": timeout_s},
                        timeout=timeout_s + 60)
        self.events.append({"kind": "exec", "status": st,
                            "wall_s": round(time.monotonic()-t0, 3)})
        if st != 200 or not isinstance(r, dict):
            message = "capacity unavailable" if isinstance(r, dict) and \
                str(r.get("message", "")).startswith("GPU plane at capacity") \
                else "no confirmed execution result"
            die(f"GPU exec: HTTP {st}; {message}")
        return r.get("result") or {}

    def fetch_file(self, remote_path, chunk=524288):
        """Fetch a lease file as bytes via chunked exec (report channel)."""
        out = b""
        while True:
            code = (
                "import base64, os\n"
                f"p = os.path.expanduser({remote_path!r})\n"
                f"data = open(p, 'rb').read() if os.path.exists(p) else b''\n"
                f"off = {len(out)}\n"
                f"report['n'] = len(data)\n"
                f"report['chunk'] = base64.b64encode(data[off:off+{chunk}]).decode()\n")
            res = self.exec(code, 120)
            rep = res.get("report") or {}
            if res.get("ok") is not True or "n" not in rep:
                die(f"fetch {remote_path}: {res.get('stderr', '')[-200:]}")
            out += base64.b64decode(rep.get("chunk") or "")
            if len(out) >= rep["n"]:
                return out

    def __exit__(self, *exc):
        self.delete()
        return False

    def delete(self):
        self._stop.set()
        if self._heartbeat is not None:
            self._heartbeat.join(timeout=1)
        if not self.id:
            return
        for attempt in range(5):
            try:
                request(self.key, "DELETE", f"/sandboxes/{self.id}")
            except Exception:
                pass
            try:
                st, remaining = request(self.key, "GET",
                                         f"/sandboxes/{self.id}")
            except Exception:
                st = None
            if st == 404:
                print(f"destroyed {self.id}; GET 404 confirmed",
                      file=sys.stderr, flush=True)
                self.id = None
                return
            time.sleep(5 * (attempt + 1))
        raise RuntimeError(
            f"cleanup unconfirmed for {self.id}: HTTP {st}; "
            f"delete it yourself via the API")


def grade_on_lease(lease, artifact, seeds, episodes, steps, mass_scale,
                   extra_files=None, timeout_s=600, trace=False,
                   remote_policy=None):
    """Ship the judge payload and run _eval.py. Returns the report dict."""
    files = {
        "env.py": os.path.join(DEMO, "env.py"),
        "_eval.py": os.path.join(HERE, "_eval.py"),
        "go1_meshless.xml": os.path.join(DEMO, "model", "go1_meshless.xml"),
    }
    if remote_policy is None:
        files["policy.npz"] = os.path.join(artifact, "policy.npz")
    if extra_files:
        files.update(extra_files)
    payload = {}
    for name, path in files.items():
        with open(path, "rb") as fh:
            payload[name] = base64.b64encode(fh.read()).decode()
    args = ["--policy", "policy.npz", "--json", "verdict_out.json",
            "--seeds", seeds, "--episodes", str(episodes),
            "--steps", str(steps), "--mass-scale", str(mass_scale)]
    if trace:
        args += ["--trace-dir", "traces"]
    code = JOB.replace("__PAYLOAD__", repr(payload)).replace(
        "__ARGS__", repr(args)).replace("__REMOTE_POLICY__", repr(remote_policy))
    res = lease.exec(code, timeout_s)
    rep = res.get("report") or {}
    if res.get("ok") is not True:
        rep.setdefault("exec_error",
                       (res.get("stderr") or "")[-300:])
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact", help="directory containing policy.npz")
    ap.add_argument("--seed", default="101,202,303",
                    help="held-out eval seed(s), comma-separated")
    ap.add_argument("--json", metavar="OUT")
    ap.add_argument("--episodes", type=int, default=64)
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--mass-scale", type=float, default=1.0,
                    help="robot mass multiplier (judge debugging / mutants)")
    ap.add_argument("--vram", type=int, default=4)
    ap.add_argument("--keep", action="store_true",
                    help="leave the lease up and print its id")
    a = ap.parse_args()

    key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
    if not key:
        die("no API key: export SBX_API_KEY (or E2B_API_KEY)")
    if not os.path.isfile(os.path.join(a.artifact, "policy.npz")):
        die(f"{a.artifact}: no policy.npz")

    t0 = time.monotonic()
    print(f"grading {a.artifact} (seeds {a.seed}, "
          f"{a.episodes} episodes/seed, {a.steps} steps)",
          file=sys.stderr, flush=True)
    with Lease(key, a.vram) as lease:
        print(f"created {lease.id}", file=sys.stderr, flush=True)
        t = time.monotonic()
        rep = grade_on_lease(lease, a.artifact, a.seed, a.episodes,
                             a.steps, a.mass_scale)
        print(f"  eval: {rep.get('eval_wall_s', '?')} s on lease "
              "(independent CPU MuJoCo)", file=sys.stderr, flush=True)
        if a.keep:
            print(f"--keep: lease {lease.id} left running")
            keep_id = lease.id
            lease.id = None
        verdict = rep.get("verdict")
        if verdict is None:
            die("no verdict from lease: "
                + json.dumps(rep, indent=1)[:1200])

    if a.json:
        with open(a.json, "w") as fh:
            json.dump(verdict, fh, indent=1, sort_keys=True)
    ok = verdict.get("ok") is True
    print(json.dumps(verdict, sort_keys=True))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
