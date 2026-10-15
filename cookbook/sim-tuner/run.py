#!/usr/bin/env python3
"""sim-tuner demo: one command, one GPU slice lease, one verdict.

Creates a fresh 4 GiB VRAM slice lease over the agent-next REST API, ships the
demo (judge + examples) into it as a base64 tar.gz payload, runs the pinned
setup check, the judge self-test, and grades the known-good params.json,
then always deletes the lease and confirms the deletion (GET -> 404/dead).

    python3 cookbook/sim-tuner/run.py [--seed N] [--keep] [--report-json PATH]
    python3 cookbook/sim-tuner/run.py --selftest-only   # skip the final grade

Needs SBX_API_KEY (or E2B_API_KEY) with GPU access, and Python 3.10+ on this
machine. Standard library only. Wall time is printed per step.

The lease image already provides Python 3.13, mujoco 3.8.1, mujoco-warp 3.8.1
and numpy; the judge on the lease uses those directly (they are exactly what
SPEC.md pins and judge/version-table.json records).
"""

import argparse
import base64
import io
import json
import os
import sys
import tarfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = "https://api.sbx.agent-next.com"
DEMO_DIR = os.path.dirname(os.path.abspath(__file__))
SETUP_WAIT_S = 1500
SELFTEST_TIMEOUT_S = 3600


def die(msg, code=1):
    print(f"run.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def request(key, method, path, body=None, timeout=1200):
    data = None if body is None else json.dumps(body).encode()
    req = Request(API + path, data=data, method=method,
                  headers={"X-API-Key": key, "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        raw = exc.read() or b""
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw.decode("utf-8", "replace")
        return exc.code, parsed


def fmt_body(b, limit=400):
    """One-line error body for die(); never contains the API key (it is sent
    in the request header, and API error bodies never echo headers)."""
    if b is None:
        return "(empty body)"
    if not isinstance(b, str):
        try:
            b = json.dumps(b)
        except Exception:
            b = str(b)
    return b.replace("\n", " ")[:limit]


def pack_demo():
    """Pack the whole demo dir (judge, examples, SPEC, README) as base64 tar.gz."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for sub in ("judge", "examples", "SPEC.md", "README.md"):
            p = os.path.join(DEMO_DIR, sub)
            if os.path.isdir(p):
                tf.add(p, arcname=sub,
                       filter=lambda ti: None if "__pycache__" in ti.name or ti.name.endswith(".pyc") else ti)
            else:
                tf.add(p, arcname=sub)
    return base64.b64encode(buf.getvalue()).decode()


EXEC_SRC = """
import base64, io, json, os, subprocess, sys, tarfile, tempfile, time

# the lease image IS the pinned toolchain (judge/version-table.json); point the
# judge at this python and let G4 score on this very slice -- exec slices have
# no outbound network and no API key, so a nested lease cannot be created.
os.environ['SIM_TUNER_PYTHON'] = sys.executable
os.environ['SIM_TUNER_GPU_LOCAL'] = '1'

root = os.path.expanduser('~/sim-tuner-demo')
os.makedirs(root, exist_ok=True)
tarfile.open(fileobj=io.BytesIO(base64.b64decode(__PAYLOAD__)), mode='r:gz').extractall(root)
j = os.path.join(root, 'judge')
report['stages'] = stages = {}
t0 = time.monotonic()

def step(name, cmd, timeout):
    t = time.monotonic()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=root)
    stages[name] = {'rc': r.returncode, 'wall_s': round(time.monotonic() - t, 1),
                    'stdout_tail': r.stdout[-1500:], 'stderr_tail': r.stderr[-800:]}
    return r

# 1. setup: validate the lease stack against SPEC (the lease image IS the toolchain;
# setup.sh --record already pinned judge/version-table.json from a reference lease).
step('stack-check', [sys.executable, '-c', '''
import sys, platform, json
import numpy, mujoco, importlib.metadata as md
got = {"python": sys.version.split()[0], "mujoco": mujoco.__version__,
       "mujoco_warp": md.version("mujoco-warp"), "numpy": numpy.__version__}
want = json.load(open("judge/version-table.json"))["gpu"]
bad = {k: (got.get(k), want.get(k)) for k in ("mujoco", "mujoco_warp", "numpy")
       if got.get(k) != want.get(k)}
print(json.dumps({"got": got, "want": {k: want.get(k) for k in got}}))
sys.exit(1 if bad else 0)
'''], 300)

if stages['stack-check']['rc'] == 0:
    step('selftest', ['bash', 'judge/selftest.sh'], __SELFTEST_TIMEOUT_S__)
    rc, verdict = 1, None
    vr = subprocess.run(['bash', 'judge/grade.sh', 'examples/good/params.json',
                         '--seed', str(__SEED__), '--json', '/tmp/verdict.json'],
                        capture_output=True, text=True, timeout=1200, cwd=root)
    if os.path.exists('/tmp/verdict.json'):
        verdict = json.load(open('/tmp/verdict.json'))
    stages['grade'] = {'rc': vr.returncode, 'wall_s': None,
                       'stdout_tail': vr.stdout[-1500:], 'stderr_tail': vr.stderr[-800:]}
    report['verdict'] = verdict
report['total_s'] = round(time.monotonic() - t0, 1)
"""


def render_job(payload, seed):
    """Substitute every value the lease job needs into EXEC_SRC.

    The exec sandbox runs the rendered source with only `report` injected;
    every other name must be bound inside EXEC_SRC itself (a bare host-side
    name left over renders as a NameError inside the lease — see
    tools/test_rendered_job.py, which compiles and executes the rendered job
    with stubs to prove no such name remains)."""
    return (EXEC_SRC
            .replace("__PAYLOAD__", repr(payload))
            .replace("__SEED__", str(int(seed)))
            .replace("__SELFTEST_TIMEOUT_S__", str(int(SELFTEST_TIMEOUT_S))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--selftest-only", action="store_true")
    ap.add_argument("--keep", action="store_true",
                    help="leave the GPU lease up and print its id")
    ap.add_argument("--report-json", metavar="PATH", help="write the exec report here")
    args = ap.parse_args()

    key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
    if not key:
        die("export SBX_API_KEY (a key with GPU access)")
    if not os.path.exists(os.path.join(DEMO_DIR, "judge", "version-table.json")):
        die("judge/version-table.json missing: run "
            "`SIM_TUNER_PYTHON=<judge python> python3 judge/record_lease.py` (or "
            "judge/setup.sh --record) first")

    total0 = time.monotonic()
    payload = pack_demo()
    print(f"packed demo ({len(payload) // 1024} KiB base64)", flush=True)

    print("create GPU lease (4 GiB VRAM slice)...", flush=True)
    t0 = time.monotonic()
    st, created = request(key, "POST", "/sandboxes", {"accel": {"vram_gb": 4, "reserve": "exec"}})
    if st != 201:
        die(f"GPU create: HTTP {st} {fmt_body(created)}; "
            "check GPU access, credit and capacity")
    sid = created["sandboxID"]
    if not isinstance(sid, str) or not sid.startswith("gl-") or not all(
            c.isascii() and (c.isalnum() or c == "-") for c in sid):
        die(f"GPU create returned an unexpected lease id {sid!r}; it was not "
            "destroyed automatically, delete it with sandbox_kill")
    print(f"created {sid} in {time.monotonic() - t0:.1f} s", flush=True)

    report = {}
    rc = 1
    try:
        job = render_job(payload, args.seed)
        print("exec judge on the lease (stack check, selftest, grade)...", flush=True)
        t0 = time.monotonic()
        st, executed = request(key, "POST", f"/sandboxes/{sid}/exec",
                               {"code": job, "timeout_s": SELFTEST_TIMEOUT_S}, timeout=SELFTEST_TIMEOUT_S + 60)
        dt = time.monotonic() - t0
        if st != 200 or not isinstance(executed, dict):
            die(f"GPU exec: HTTP {st} {fmt_body(executed)}")
        result = executed.get("result") or {}
        report = result.get("report") or {}
        if result.get("ok") is not True:
            die(f"judge job failed on the lease: {(result.get('stderr') or '')[-500:]}")
        print(f"lease job done in {dt:.0f} s", flush=True)

        if args.report_json:
            with open(args.report_json, "w") as fh:
                json.dump(report, fh, indent=2, sort_keys=True)
            print(f"wrote exec report: {args.report_json}")

        for name, stg in (report.get("stages") or {}).items():
            print(f"  [{name}] rc={stg.get('rc')} ({stg.get('wall_s')} s)")
        verdict = report.get("verdict")
        if verdict:
            gates = verdict.get("gates", {})
            ok = verdict.get("pass")
            print(f"\nsim-tuner demo: {verdict.get('verdict')} (seed {verdict.get('seed')})")
            for name, g in sorted(gates.items()):
                line = f"  gate {name}: {'pass' if g.get('pass') else 'FAIL'}"
                if name == "G3_heldout":
                    line += (f"  heldout_err {g.get('heldout_err')} (< {g.get('abs_threshold')}; "
                             f"frac of default {g.get('frac_of_default')} < {g.get('rel_threshold')})")
                if name == "G4_gpu_cpu_agree":
                    line += (f"  gpu {g.get('gpu_train_err')} vs cpu {g.get('cpu_train_err')} "
                             f"(abs {g.get('abs_diff')}, rel {g.get('rel_diff')})")
                print(line)
        rc = 0
        if (report.get("stages") or {}).get("selftest", {}).get("rc") != 0:
            rc = 1
        if not args.selftest_only:
            if not verdict or not verdict.get("pass"):
                rc = 1
        if rc != 0:
            print("\n(good grade or selftest did not pass; see stage output)", flush=True)
    finally:
        if args.keep:
            print(f"run.py: --keep: lease {sid} left running; delete it with "
                  f"DELETE /sandboxes/{sid} (or sandbox_kill)", flush=True)
            print(f"total: {time.monotonic() - total0:.0f} s")
            raise SystemExit(rc)
        print(f"destroying {sid}...", flush=True)
        try:
            request(key, "DELETE", f"/sandboxes/{sid}")
        except Exception:
            pass  # the confirm below decides; a lost destroy reply may still be a release
        try:
            st, remaining = request(key, "GET", f"/sandboxes/{sid}")
        except Exception as exc:
            raise RuntimeError(f"cleanup unconfirmed for {sid}; run sandbox_kill for this id") from exc
        if st != 404 and not (st == 200 and isinstance(remaining, dict)
                              and remaining.get("phase") == "dead"):
            die(f"cleanup unconfirmed for {sid}: HTTP {st} {fmt_body(remaining)}; "
                "run sandbox_kill for this id")
        print(f"destroyed {sid}; verified absent or dead", flush=True)

    print(f"total: {time.monotonic() - total0:.0f} s")
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
