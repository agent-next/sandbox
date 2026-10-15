#!/usr/bin/env python3
"""gpu-embed-rag-index demo: one command, one disposable sandbox, one verdict.

Creates an agent-next sandbox, clones this repository inside it, installs
the pinned judge toolchain, runs the judge self-test, then grades the
known-good RAG pipeline — and always kills the sandbox afterwards.

    python3 cookbook/gpu-embed-rag-index/run.py [--ref main] [--keep] [--gpu]

Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

--gpu creates a 1 GiB VRAM slice lease over the REST API exactly like
cookbook/small-gpu/run.py (POST /sandboxes {"accel":{"vram_gb":1,"reserve":"exec"}},
then POST /sandboxes/{id}/exec {"code": <python>, "timeout_s": N} which runs
Python with a report dict, then DELETE + GET confirm 404/dead). The lease
image already has Python 3.13, torch 2.10.0+cu128, numpy 1.26.4 on an RTX 5090
slice (cc 12.0); no nvcc, no pip needed. The pinned model weights and
faiss-cpu wheel are uploaded to the lease via the files API before the judge
runs.

Without --gpu the sandbox is a plain CPU sandbox (via sbx CLI) and the judge
auto-falls back to --cpu-check (interpreter numerics, no GPU throughput).

Standard library only. Wall time is printed per step.
"""

import argparse
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/gpu-embed-rag-index"
STEP_TIMEOUTS = {
    "clone": 300,
    "setup": 2400,
    "selftest": 1800,
    "grade": 1200,
}

API = "https://api.sbx.agent-next.com"


def die(msg, code=1):
    print(f"run.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def need_sbx():
    if not shutil.which("sbx"):
        die("sbx CLI not found: pip install "
            "'git+https://github.com/agent-next/sandbox#subdirectory=cli'")
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        die("no API key: export SBX_API_KEY (or E2B_API_KEY)")


def run(step, *args, timeout=None, capture=False):
    t0 = time.monotonic()
    proc = subprocess.run(
        args, capture_output=capture, text=True,
        timeout=timeout and timeout + 30)
    dt = time.monotonic() - t0
    status = "ok" if proc.returncode == 0 else f"exit {proc.returncode}"
    print(f"  [{step}] {' '.join(args[:3])} ... {status} "
          f"({dt:.0f} s)", flush=True)
    return proc, dt


def request(key, method, path, body=None):
    """Make an HTTP request to the agent-next sandbox API."""
    data = None if body is None else json.dumps(body).encode()
    req = Request(API + path, data=data, method=method,
                  headers={"X-API-Key": key, "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=900) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        return exc.code, None


def pack_judge_and_examples(demo_path):
    """Pack judge/ and examples/ as a base64-encoded tar.gz."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for sub in ("judge", "examples"):
            tf.add(os.path.join(demo_path, sub), arcname=sub)
    return base64.b64encode(buf.getvalue()).decode()


def gpu_exec_job(payload_b64):
    """Return the Python code to exec on the GPU lease."""
    return f"""
import base64, io, json, os, subprocess, sys, tarfile, tempfile
root = tempfile.mkdtemp(prefix='rage-')
tarfile.open(fileobj=io.BytesIO(base64.b64decode({payload_b64!r})), mode='r:gz').extractall(root)
j = os.path.join(root, 'judge')
def grade(art, out):
    r = subprocess.run([sys.executable, os.path.join(j, '_grade.py'), art, '--seed', '0',
                        '--json', out, '--judge-dir', j], capture_output=True, text=True, timeout=240)
    v = json.load(open(out)) if os.path.exists(out) else None
    return r.returncode, v, r.stderr[-400:]
rc, v, err = grade(os.path.join(root, 'examples', 'good', 'rag.py'), os.path.join(root, 'good.json'))
report['good'] = dict(rc=rc, verdict=v, stderr=err)
mdir = os.path.join(root, 'mutants')
names = subprocess.run([sys.executable, os.path.join(j, 'mutants.py'), mdir],
                       capture_output=True, text=True).stdout.split()
kills = {{}}
for n in names:
    rc, v, err = grade(os.path.join(mdir, n + '.py'), os.path.join(mdir, n + '.json'))
    gs = {{g: x for g, x in ((v or {{}}).get('gates') or {{}}).items() if isinstance(x, dict)}}
    failed = [g for g, x in gs.items() if x.get('pass') is False]
    detail = {{g: (f"{{len(x.get('failed') or [])}}/{{x.get('cases')}} cases" if g == 'index-correctness'
                  else '; '.join(map(str, x.get('problems') or []))[:60]) for g, x in gs.items()}}
    kills[n] = dict(rc=rc, failed=failed, gates={{g: x.get('pass') for g, x in gs.items()}}, detail=detail,
                    judge_error=None if v else err[-300:])
report['mutants'] = kills
"""


def run_gpu_path(key, demo_path, report_json=None):
    """Run the GPU path using the REST API (1 GiB VRAM slice lease)."""
    job = gpu_exec_job(pack_judge_and_examples(demo_path))
    print("create GPU lease (1 GiB VRAM slice)...", flush=True)
    st, created = request(key, "POST", "/sandboxes", {"accel": {"vram_gb": 1, "reserve": "exec"}})
    if st != 201:
        die(f"GPU create: HTTP {st}; check GPU access, credit and capacity")
    sid = created["sandboxID"]
    if not isinstance(sid, str) or not sid.startswith("gl-") or not all(
        c.isascii() and (c.isalnum() or c == "-") for c in sid
    ):
        die(f"GPU create returned an unexpected lease id {sid!r}; it was not "
            "destroyed automatically, delete it with sandbox_kill")
    print(f"created {sid} (1 GiB VRAM slice)", flush=True)

    try:
        print("exec grading job on GPU lease...", flush=True)
        st, executed = request(key, "POST", f"/sandboxes/{sid}/exec", {
            "code": job,
            "timeout_s": 600,
        })
        if st != 200 or not isinstance(executed, dict):
            die(f"GPU exec: HTTP {st}")
        result = executed.get("result") or {}
        report = result.get("report") or {}
        if result.get("ok") is not True:
            stderr = result.get("stderr", "")
            die(f"GPU job failed: {stderr[-500:]}")

        if report_json:
            with open(report_json, "w") as fh:
                json.dump(report, fh, indent=2, sort_keys=True)
            print(f"wrote exec report: {report_json}")

        good = report.get("good", {})
        verdict = good.get("verdict", {})
        mutants = report.get("mutants", {})

        if verdict:
            gates = verdict.get("gates", {})
            ok = all(g.get("pass") for g in gates.values()) and verdict.get("judge_intact", False)
            timing = verdict.get("timing") or {}
            print(f"\ngpu-embed-rag-index demo: {'PASS' if ok else 'FAIL'} (mode {verdict.get('mode')})")
            for name, g in sorted(gates.items()):
                print(f"  gate {name}: {'pass' if g.get('pass') else 'FAIL'}")
            if timing:
                gpu_pps = timing.get('gpu_passages_per_s', 0)
                cpu_pps = timing.get('cpu_passages_per_s', 0)
                speedup = timing.get('speedup', 0)
                print(f"  GPU {gpu_pps:.0f} passages/s vs CPU {cpu_pps:.0f} passages/s (speedup x{speedup:.2f})")
            print()

        total = len(mutants)
        killed = sum(1 for m in mutants.values() if m.get("failed"))
        broken = sorted(n for n, m in mutants.items() if m.get("judge_error"))
        print(f"mutants: {killed}/{total} killed")
        for name, m in sorted(mutants.items()):
            failed = m.get("failed", [])
            if m.get("judge_error"):
                print(f"  {name}: JUDGE ERROR ({m['judge_error'].strip()[-120:]})")
            else:
                print(f"  {name}: {'FAIL' if failed else 'SURVIVED'} "
                      f"({', '.join(failed) if failed else 'no gate failed'})")
        if broken or killed < total:
            die(f"judge self-test incomplete: {total - killed} mutant(s) not killed")

        return verdict, mutants

    finally:
        print(f"destroying {sid}...", flush=True)
        try:
            request(key, "DELETE", f"/sandboxes/{sid}")
        except Exception:
            pass
        try:
            st, remaining = request(key, "GET", f"/sandboxes/{sid}")
        except Exception as exc:
            raise RuntimeError(f"cleanup unconfirmed for {sid}; run sandbox_kill for this id") from exc
        if st != 404 and not (
            st == 200 and isinstance(remaining, dict) and remaining.get("phase") == "dead"
        ):
            die(f"cleanup unconfirmed for {sid}: HTTP {st}; run sandbox_kill for this id")
        print(f"destroyed {sid}; verified absent or dead", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main",
                    help="repository ref to clone inside the sandbox")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox up and print its id")
    ap.add_argument("--gpu", action="store_true",
                    help="create a 1 GiB VRAM slice lease via REST API "
                         "(GPU access required on your key) for full CUDA judge")
    ap.add_argument("--report-json", metavar="PATH",
                    help="with --gpu: write the raw exec report dict "
                         "(good verdict incl. timing + per-mutant failed "
                         "gates) to PATH, e.g. media/data/report.json")
    args = ap.parse_args()

    total0 = time.monotonic()

    if args.report_json and not args.gpu:
        die("--report-json only applies to the --gpu path")

    if args.gpu:
        key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
        if not key:
            die("no API key: export SBX_API_KEY (or E2B_API_KEY)")
        demo_path = os.path.dirname(os.path.abspath(__file__))
        verdict, mutants = run_gpu_path(key, demo_path, args.report_json)
        print(f"total: {time.monotonic() - total0:.0f} s")
        gates = verdict.get("gates", {})
        ok = all(g.get("pass") for g in gates.values()) and verdict.get("judge_intact", False)
        raise SystemExit(0 if ok else 1)

    need_sbx()
    create = ["sbx", "create", "--timeout-min", "30"]
    proc, _ = run("create", *create, timeout=120, capture=True)
    if proc.returncode != 0:
        die(f"sbx create failed: {proc.stderr.strip()}")
    sbx_id = proc.stdout.strip().splitlines()[-1]
    print(f"sandbox: {sbx_id} (template default)")

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
        grade = exec_step("grade", [
            "bash", f"sandbox/{DEMO_DIR}/judge/grade.sh",
            f"sandbox/{DEMO_DIR}/examples/good/rag.py",
            "--json", "/tmp/verdict.json"])

        proc, _ = run("cat", "sbx", "exec", sbx_id, "--timeout", "60",
                      "--", "cat", "/tmp/verdict.json", capture=True)
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                verdict = json.loads(proc.stdout)
            except json.JSONDecodeError:
                pass
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
            print(f"cleanup: sandbox {sbx_id} killed and confirmed gone")

    print(f"total: {time.monotonic() - total0:.0f} s")
    if verdict:
        gates = verdict.get("gates", {})
        ok = all(g.get("pass") for g in gates.values()) and \
            verdict.get("judge_intact", False)
        timing = verdict.get("timing") or {}
        print(f"\ngpu-embed-rag-index demo: {'PASS' if ok else 'FAIL'} "
              f"(mode {verdict.get('mode')})")
        for name, g in sorted(gates.items()):
            print(f"  gate {name}: {'pass' if g.get('pass') else 'FAIL'}")
        if timing:
            gpu_pps = timing.get('gpu_passages_per_s', 0)
            cpu_pps = timing.get('cpu_passages_per_s', 0)
            speedup = timing.get('speedup', 0)
            print(f"  GPU {gpu_pps:.0f} passages/s vs CPU {cpu_pps:.0f} passages/s "
                  f"(speedup x{speedup:.2f})")
        raise SystemExit(0 if ok else 1)
    die("no verdict JSON returned from the sandbox")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        message = str(exc)
        for name in ("SBX_API_KEY", "E2B_API_KEY"):
            if os.environ.get(name):
                message = message.replace(os.environ[name], "[redacted]")
        print(f"gpu-embed-rag-index: {message}", file=sys.stderr)
        sys.exit(1)
