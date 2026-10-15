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
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = "https://api.sbx.agent-next.com"
HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)

JOB = """
import base64, json, os, subprocess, sys, time
FILES = __PAYLOAD__
ARGS = __ARGS__
ROOT = os.path.expanduser('~/go1judge')
os.makedirs(os.path.join(ROOT, 'model'), exist_ok=True)
os.chdir(ROOT)
for name, b64 in FILES.items():
    sub = 'model' if name.endswith('.xml') else ''
    d = os.path.join(ROOT, sub)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), 'wb') as fh:
        fh.write(base64.b64decode(b64))
for m in ('env', '_eval'):
    sys.modules.pop(m, None)
t0 = time.time()
proc = subprocess.run([sys.executable, '_eval.py'] + ARGS,
                      capture_output=True, text=True, timeout=600)
report['rc'] = proc.returncode
report['stdout_tail'] = proc.stdout[-3000:]
report['stderr_tail'] = proc.stderr[-2000:]
report['eval_wall_s'] = round(time.time() - t0, 1)
try:
    report['verdict'] = json.load(open('verdict_out.json'))
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
    for attempt in range(5):
        try:
            with urlopen(r, timeout=timeout) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if raw else None
        except HTTPError as exc:
            # 409 = exec slot busy, 5xx = transient gateway blip
            if exc.code == 409 or 500 <= exc.code < 600:
                last = exc
                time.sleep(5 * (attempt + 1))
                continue
            return exc.code, None
    return last.code, None


def check_lease_id(sid):
    return isinstance(sid, str) and sid.startswith("gl-") and all(
        c.isascii() and (c.isalnum() or c == "-") for c in sid)


class Lease:
    """A VRAM-slice lease; always delete() in a finally."""

    def __init__(self, key, vram_gb=4):
        self.key, self.vram_gb = key, vram_gb
        self.id = None

    def __enter__(self):
        t0 = time.monotonic()
        while True:
            st, created = request(self.key, "POST", "/sandboxes", {
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
        self.id = created["sandboxID"]
        if not check_lease_id(self.id):
            die(f"GPU create returned unexpected lease id {self.id!r}")
        return self

    def exec(self, code, timeout_s=600):
        st, r = request(self.key, "POST", f"/sandboxes/{self.id}/exec",
                        {"code": code, "timeout_s": timeout_s},
                        timeout=timeout_s + 60)
        if st != 200 or not isinstance(r, dict):
            die(f"GPU exec: HTTP {st}")
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
            if st == 404 or (st == 200 and isinstance(remaining, dict)
                             and remaining.get("phase") == "dead"):
                print(f"destroyed {self.id}; verified absent or dead",
                      flush=True)
                self.id = None
                return
            time.sleep(5 * (attempt + 1))
        raise RuntimeError(
            f"cleanup unconfirmed for {self.id}: HTTP {st}; "
            f"delete it yourself via the API")
        print(f"destroyed {self.id}; verified absent or dead", flush=True)
        self.id = None


def grade_on_lease(lease, artifact, seeds, episodes, steps, mass_scale,
                   extra_files=None, timeout_s=600):
    """Ship the judge payload and run _eval.py. Returns the report dict."""
    files = {
        "env.py": os.path.join(DEMO, "env.py"),
        "_eval.py": os.path.join(HERE, "_eval.py"),
        "go1_meshless.xml": os.path.join(DEMO, "model", "go1_meshless.xml"),
        "policy.npz": os.path.join(artifact, "policy.npz"),
    }
    if extra_files:
        files.update(extra_files)
    payload = {}
    for name, path in files.items():
        with open(path, "rb") as fh:
            payload[name] = base64.b64encode(fh.read()).decode()
    args = ["--policy", "policy.npz", "--json", "verdict_out.json",
            "--seeds", seeds, "--episodes", str(episodes),
            "--steps", str(steps), "--mass-scale", str(mass_scale)]
    code = JOB.replace("__PAYLOAD__", repr(payload)).replace(
        "__ARGS__", repr(args))
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
    print(f"grading {a.artifact} on a {a.vram} GiB VRAM slice "
          f"(seeds {a.seed}, {a.episodes} episodes/seed, "
          f"{a.steps} steps)", flush=True)
    with Lease(key, a.vram) as lease:
        print(f"created {lease.id}", flush=True)
        t = time.monotonic()
        rep = grade_on_lease(lease, a.artifact, a.seed, a.episodes,
                             a.steps, a.mass_scale)
        print(f"  eval: {rep.get('eval_wall_s', '?')} s on lease "
              f"(incl. first-time kernel compile)", flush=True)
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
    print(f"verdict: {'PASS' if ok else 'FAIL'} "
          f"(total wall {time.monotonic() - t0:.0f} s)")
    for name, g in sorted((verdict.get("gates") or {}).items()):
        print(f"  {name}: {'pass' if g.get('pass') else 'FAIL'} "
              f"({g.get('rule')}; measured {g.get('value')})")
    if verdict.get("error"):
        print(f"  error: {verdict['error']}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
