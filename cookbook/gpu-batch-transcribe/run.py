#!/usr/bin/env python3
"""gpu-batch-transcribe demo: one command, one disposable sandbox, one verdict.

Creates an agent-next sandbox, clones this repository inside it, installs
the pinned judge toolchain, regenerates + digest-checks the audio corpus,
runs the judge self-test, then grades the known-good transcriber — and
always kills the sandbox afterwards.

    python3 cookbook/gpu-batch-transcribe/run.py [--ref main] [--keep] [--gpu]

Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

--gpu additionally grades the same artifact on a 1 GiB VRAM slice lease
over the REST API exactly like cookbook/small-gpu/run.py (POST /sandboxes
{"accel":{"vram_gb":1,"reserve":"exec"}}, then POST /sandboxes/{id}/exec
{"code": <python>, "timeout_s": N}, then DELETE + GET confirm 404/dead).
The lease runs the same judge with the lease image's own torch (CUDA);
the transcripts must be byte-identical to the CPU sandbox's — the demo's
determinism claim — and the verdict must be all gates pass.

Every step's exit code is checked; any failure exits non-zero, naming the
sandbox id if cleanup could not be confirmed. Standard library only.
Wall time is printed per step.
"""

import argparse
import base64
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/gpu-batch-transcribe"
# sbx exec's default timeout is 60 s; every step below needs more. The
# setup budget covers the ~200 MB torch wheel download.
STEP_TIMEOUTS = {
    "clone": 300,
    "setup": 1800,
    "selftest": 2400,
    "grade": 1200,
}

API = "https://api.sbx.agent-next.com"

# A transport blip (tunnel error, connection reset, a 5xx/429 from the
# gateway) is not a verdict on the command — the CLI may have failed
# before the request was even sent. These are retried with backoff
# (LESSONS.md, 616b07c). Anything else fails immediately and verbatim.
TRANSIENT_ERRORS = (
    "connecterror", "tunnel error", "error sending request",
    "connection reset", "connection refused", "connection aborted",
    "remote end closed", "temporarily unavailable", "timed out",
    "timeout", "http 408", "http 429", "http 500", "http 502",
    "http 503", "http 504", "bad gateway", "service unavailable",
)


def is_transient(text):
    if not text:
        return False
    low = text.lower()
    return any(pat in low for pat in TRANSIENT_ERRORS)


def die(msg, code=1):
    print(f"run.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def need_sbx():
    if not shutil.which("sbx"):
        die("sbx CLI not found: pip install "
            "'git+https://github.com/agent-next/sandbox#subdirectory=cli'")
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        die("no API key: export SBX_API_KEY (or E2B_API_KEY)")


class StepProc:
    """A step outcome: returncode plus output, or a local timeout marker."""

    def __init__(self, returncode, stdout="", stderr="", timeout=False):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timeout = timeout


def run(step, *args, timeout=None, capture=False, attempts=1, backoff=10):
    """Run one sbx command, retrying transient transport failures.

    `attempts` bounds the tries; each retry waits `backoff` * attempt
    seconds first. A command that fails for a non-transient reason runs
    once. A local subprocess timeout is never retried here (the command
    may still be running remotely); callers treat it as a failure.
    """
    for attempt in range(1, attempts + 1):
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                args, capture_output=capture, text=True,
                timeout=timeout and timeout + 30)
        except subprocess.TimeoutExpired:
            dt = time.monotonic() - t0
            print(f"  [{step}] {' '.join(args[:3])} ... local timeout "
                  f"after {dt:.0f} s (the command may still be running "
                  "in the sandbox)", flush=True)
            return StepProc(124, timeout=True, stderr="local timeout"), dt
        dt = time.monotonic() - t0
        status = "ok" if proc.returncode == 0 else f"exit {proc.returncode}"
        print(f"  [{step}] {' '.join(args[:3])} ... {status} "
              f"({dt:.0f} s)", flush=True)
        text = (proc.stderr or "") + (proc.stdout or "")
        if proc.returncode != 0 and attempt < attempts and is_transient(text):
            wait = backoff * attempt
            print(f"  [{step}] transient transport error; retrying in "
                  f"{wait} s (attempt {attempt + 1}/{attempts})", flush=True)
            time.sleep(wait)
            continue
        return proc, dt
    raise AssertionError("unreachable")


# --------------------------------------------------------------- GPU lease

def request(key, method, path, body=None):
    """HTTP request to the agent-next sandbox API (GPU lease path)."""
    data = None if body is None else json.dumps(body).encode()
    req = Request(API + path, data=data, method=method,
                  headers={"X-API-Key": key,
                           "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=900) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        return exc.code, None


def pack_demo(demo_path):
    """judge/ + examples/ + SPEC as a base64 tar.gz (uploaded to a lease).

    Packed before the lease exists, so a local error cannot leak one.
    The corpus is regenerated on the lease by setup.sh from the committed
    synthesizer and digest-checked, so no audio crosses the wire.
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for sub in ("judge", "examples"):
            tf.add(os.path.join(demo_path, sub), arcname=sub)
    return base64.b64encode(buf.getvalue()).decode()


def gpu_exec_job(payload_b64):
    """Python code the GPU lease runs: setup, grade good, grade mutants."""
    return f"""
import base64, io, json, os, subprocess, sys, tarfile, tempfile
root = tempfile.mkdtemp(prefix='gbt-')
tarfile.open(fileobj=io.BytesIO(base64.b64decode({payload_b64!r})),
             mode='r:gz').extractall(root)
j = os.path.join(root, 'judge')
env = dict(os.environ)
def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    return r.returncode, (r.stdout or '') + (r.stderr or '')
rc, out = run(['bash', os.path.join(j, 'setup.sh')])
report['setup'] = dict(rc=rc, tail=out.strip()[-300:])
if rc != 0:
    raise SystemExit(0)
rc, out = run([sys.executable, os.path.join(j, '_grade.py'),
               os.path.join(root, 'examples', 'good', 'transcriber.py'),
               '--json', os.path.join(root, 'good.json'),
               '--judge-dir', j])
report['good'] = dict(rc=rc, tail=out.strip()[-300:])
good = {{}}
try:
    good = json.load(open(os.path.join(root, 'good.json')))
except Exception as exc:
    report['good_read_error'] = str(exc)
report['good_verdict'] = good
gates = {{g: x.get('pass') for g, x in (good.get('gates') or {{}}).items()}}
report['good_all_pass'] = all(gates.values()) and good.get('judge_intact', False)
report['cuda_available'] = None
try:
    import torch
    report['cuda_available'] = bool(torch.cuda.is_available())
    report['torch_version'] = torch.__version__
    report['device_name'] = (torch.cuda.get_device_name(0)
                             if report['cuda_available'] else 'cpu')
except Exception as exc:
    report['torch_error'] = str(exc)[:200]
mut = os.path.join(root, 'mutants')
rc, out = run([sys.executable, os.path.join(j, 'mutants.py'), mut])
names = out.split()
kills = {{}}
for n in names:
    rc2, _ = run([sys.executable, os.path.join(j, '_grade.py'),
                  os.path.join(mut, n + '.py'),
                  '--json', os.path.join(mut, n + '.json'),
                  '--judge-dir', j])
    v = {{}}
    try:
        v = json.load(open(os.path.join(mut, n + '.json')))
    except Exception:
        pass
    gs = {{g: x.get('pass') for g, x in (v.get('gates') or {{}}).items()}}
    kills[n] = dict(killed=not (all(gs.values()) and v.get('judge_intact', False)),
                    failed=[g for g, x in gs.items() if x is False])
report['mutants'] = kills
report['kill_rate'] = (sum(1 for k in kills.values() if k['killed']), len(kills))
"""


def run_gpu_grade(key, demo_path):
    """Grade the good artifact + all mutants on a GPU lease; return report.

    The lease is destroyed here (finally) and its id is recorded so a
    lost reply cannot leak a lease.
    """
    job = gpu_exec_job(pack_demo(demo_path))
    print("create GPU lease (1 GiB VRAM slice)...", flush=True)
    st, created = request(key, "POST", "/sandboxes",
                          {"accel": {"vram_gb": 1, "reserve": "exec"}})
    if st != 201:
        die(f"GPU create: HTTP {st}; check GPU access, credit and capacity")
    sid = created["sandboxID"]
    # Only gateway-generated GPU ids may be interpolated into request paths.
    if not isinstance(sid, str) or not sid.startswith("gl-") or not all(
        c.isascii() and (c.isalnum() or c == "-") for c in sid
    ):
        die(f"GPU create returned an unexpected lease id {sid!r}; it was not "
            "destroyed automatically, delete it with sandbox_kill")
    print(f"created {sid} (1 GiB VRAM slice)", flush=True)
    try:
        print("exec judge on GPU lease...", flush=True)
        st, executed = request(key, "POST", f"/sandboxes/{sid}/exec", {
            "code": job,
            "timeout_s": 1800,
        })
        if st != 200 or not isinstance(executed, dict):
            die(f"GPU exec: HTTP {st}")
        result = executed.get("result") or {}
        if result.get("ok") is not True:
            stderr = result.get("stderr", "")
            die(f"GPU job failed: {stderr[-500:]}")
        report = result.get("report") or {}

        print(f"  gpu lease: torch {report.get('torch_version')} on "
              f"{report.get('device_name')} (cuda_available="
              f"{report.get('cuda_available')})", flush=True)
        setup = report.get("setup") or {}
        if setup.get("rc") != 0:
            die(f"GPU lease setup.sh failed: {setup.get('tail')}")
        good = report.get("good_verdict") or {}
        gates = {g: x.get("pass")
                 for g, x in (good.get("gates") or {}).items()}
        acc = good.get("accuracy") or {}
        print(f"  gpu lease verdict: "
              f"{'PASS' if report.get('good_all_pass') else 'FAIL'} "
              f"(gates: {gates}, exact {acc.get('exact')}/{acc.get('n')}, "
              f"wer {acc.get('wer')})", flush=True)
        killed, total = report.get("kill_rate", (0, 0))
        print(f"  gpu lease mutants: {killed}/{total} killed", flush=True)
        for name, k in sorted((report.get("mutants") or {}).items()):
            if not k.get("killed"):
                print(f"    {name}: SURVIVED ({k.get('failed')})", flush=True)
        if not report.get("good_all_pass"):
            die("GPU lease grade did not pass every gate")
        if total and killed < total:
            die(f"GPU lease self-test incomplete: {total - killed} "
                "mutant(s) not killed")
        return report
    finally:
        print(f"destroying {sid}...", flush=True)
        try:
            request(key, "DELETE", f"/sandboxes/{sid}")
        except Exception:
            pass
        try:
            st, remaining = request(key, "GET", f"/sandboxes/{sid}")
        except Exception:
            die(f"cleanup unconfirmed for {sid}; run sandbox_kill for this id")
        if st != 404 and not (
            st == 200 and isinstance(remaining, dict)
            and remaining.get("phase") == "dead"
        ):
            die(f"cleanup unconfirmed for {sid}: HTTP {st}; "
                "run sandbox_kill for this id")
        print(f"destroyed {sid}; verified absent or dead", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main",
                    help="repository ref to clone inside the sandbox")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox up and print its id")
    ap.add_argument("--gpu", action="store_true",
                    help="also grade the artifact on a 1 GiB VRAM slice "
                         "lease via the REST API (GPU access required on "
                         "your key) and check the verdict matches")
    args = ap.parse_args()

    need_sbx()
    total0 = time.monotonic()

    proc, _ = run("create", "sbx", "create", "--timeout-min", "30",
                  timeout=120, capture=True)
    if proc.returncode != 0:
        die(f"sbx create failed: {proc.stderr.strip()}")
    sbx_id = proc.stdout.strip().splitlines()[-1]
    print(f"sandbox: {sbx_id} (template default)", flush=True)

    verdict = None
    try:
        def exec_step(name, cmd):
            proc, _ = run(name, "sbx", "exec", sbx_id,
                          "--timeout", str(STEP_TIMEOUTS[name]), "--", *cmd)
            if proc.returncode != 0:
                die(f"step {name} failed in sandbox {sbx_id} "
                    f"(exit {proc.returncode})")
            return proc

        exec_step("clone", [
            "git", "clone", "--depth", "1", "-b", args.ref, REPO, "sandbox"])
        exec_step("setup", [
            "bash", f"sandbox/{DEMO_DIR}/judge/setup.sh"])
        exec_step("selftest", [
            "bash", f"sandbox/{DEMO_DIR}/judge/selftest.sh"])
        exec_step("grade", [
            "bash", f"sandbox/{DEMO_DIR}/judge/grade.sh",
            f"sandbox/{DEMO_DIR}/examples/good/transcriber.py",
            "--json", "/tmp/verdict.json"])

        # Pull the verdict back for the local summary.
        proc, _ = run("cat", "sbx", "exec", sbx_id, "--timeout", "60",
                      "--", "cat", "/tmp/verdict.json", capture=True)
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                verdict = json.loads(proc.stdout)
            except json.JSONDecodeError:
                pass
        if verdict is None:
            die(f"no verdict JSON returned from sandbox {sbx_id}")
    finally:
        if args.keep:
            print(f"run.py: --keep: sandbox {sbx_id} left running; "
                  "kill it with: sbx kill " + sbx_id)
        else:
            run("kill", "sbx", "kill", sbx_id, timeout=120)
            proc, _ = run("list", "sbx", "list", timeout=60, capture=True)
            if sbx_id in (proc.stdout or ""):
                die(f"cleanup not confirmed: sandbox {sbx_id} still live; "
                    "kill it with: sbx kill " + sbx_id)
            print(f"cleanup: sandbox {sbx_id} killed and confirmed gone",
                  flush=True)

    if args.gpu:
        key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
        demo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)))
        run_gpu_grade(key, demo_path)

    print(f"total: {time.monotonic() - total0:.0f} s", flush=True)
    gates = verdict.get("gates", {})
    ok = all(g.get("pass") for g in gates.values()) and \
        verdict.get("judge_intact", False)
    acc = verdict.get("accuracy", {})
    print(f"\ngpu-batch-transcribe: {'PASS' if ok else 'FAIL'}")
    for name, g in sorted(gates.items()):
        print(f"  gate {name}: {'pass' if g.get('pass') else 'FAIL'}")
    if acc:
        print(f"  exact {acc.get('exact')}/{acc.get('n')} "
              f"({acc.get('exact_rate'):.2f}), "
              f"WER {acc.get('wer'):.4f}")
    print(json.dumps(verdict, indent=2, sort_keys=True))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
