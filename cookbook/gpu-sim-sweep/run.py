#!/usr/bin/env python3
"""gpu-sim-sweep demo: one command, one disposable sandbox, one verdict.

Creates an agent-next sandbox, clones this repository inside it, installs
the pinned judge toolchain, runs the judge self-test, then grades the
known-good sweep config — and always kills the sandbox afterwards.

    python3 cookbook/gpu-sim-sweep/run.py [--ref main] [--keep] [--gpu]

Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

--gpu creates a 4 GiB VRAM slice lease over the REST API exactly like
cookbook/small-gpu/run.py (POST /sandboxes {"accel":{"vram_gb":4,"reserve":"exec"}},
then POST /sandboxes/{id}/exec {"code": <python>, "timeout_s": N} which runs
Python with a report dict, then DELETE + GET confirm 404/dead). The lease
image already has Python 3.13, mujoco 3.8.1, mujoco-warp 3.8.1, warp 1.13.0,
numpy 1.26.4 on an RTX 5090 slice (cc 12.0); no pip needed.

Without --gpu the sandbox is a plain CPU sandbox (via sbx CLI) and the judge
auto-falls back to cpu-check mode (structure + a live CPU physics oracle).

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
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/gpu-sim-sweep"
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


def request(key, method, path, body=None, timeout=570):
    """One call to the agent-next sandbox API. Returns (status, parsed).

    On a non-2xx reply the response body is printed verbatim to stderr —
    a bare 'HTTP 502' must tell you why — and returned as
    {"error_body": ...} when it is not JSON. Transport errors
    (URLError, RemoteDisconnected, timeouts) are raised for the caller.
    """
    data = None if body is None else json.dumps(body).encode()
    req = Request(API + path, data=data, method=method,
                  headers={"X-API-Key": key, "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as r:
            status, raw = r.status, r.read()
    except HTTPError as exc:
        status, raw = exc.code, exc.read()
    if status >= 300 and not (method == "GET" and status == 404):
        # GET 404 is the cleanup-confirmation success path, not an error.
        detail = raw.decode("utf-8", "replace").strip()[:2000]
        print(f"run.py: {method} {path}: HTTP {status}"
              + (f": {detail}" if detail else " (empty error body)"),
              file=sys.stderr, flush=True)
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:
        return status, {"error_body": raw.decode("utf-8", "replace")[:2000]}


def pack_judge_and_examples(demo_path):
    """Pack judge/ and examples/ as a base64-encoded tar.gz."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for sub in ("judge", "examples"):
            tf.add(os.path.join(demo_path, sub), arcname=sub,
                   filter=lambda ti: None if (
                       "__pycache__" in ti.name or
                       ti.name.endswith(".pyc")) else ti)
    return base64.b64encode(buf.getvalue()).decode()


JOB_ROOT = "~/gsims-job"  # under $HOME: persists across exec calls on a lease

# Exec 1: unpack judge/ + examples/ and generate the mutants. Every later
# exec grades ONE artifact as its own subprocess: the whole run takes minutes
# (9 real sim grades), which no single exec request could outlive, and a
# point that crashes the CUDA context cannot take the job down with it.
def gpu_unpack_job(payload_b64):
    return f"""
import base64, io, json, os, shutil, subprocess, sys, tarfile
root = os.path.expanduser({JOB_ROOT!r})
shutil.rmtree(root, ignore_errors=True)
os.makedirs(root)
tarfile.open(fileobj=io.BytesIO(base64.b64decode({payload_b64!r})), mode='r:gz').extractall(root)
j = os.path.join(root, 'judge')
mdir = os.path.join(root, 'mutants')
r = subprocess.run([sys.executable, os.path.join(j, 'mutants.py'), mdir],
                   capture_output=True, text=True, timeout=120)
names = [l.split('\\t') for l in r.stdout.splitlines() if l.strip()]
report.update(root=root, python=sys.version.split()[0],
              mutants=[{{'name': n, 'mode': m}} for n, m in names],
              mutants_stderr=r.stderr[-300:])
"""


# Exec timeouts, all well under the 600 s at which the platform drops an
# exec HTTP reply. The cost gate bounds every grade's sim work (SPEC.md):
# the good grade pays the ~90 s Warp cold-compile plus ~60 s of sims, and a
# cost-passing mutant is at most ~90 s of bounded sims. Each grade's
# subprocess timeout sits just below its exec timeout so a hung grade comes
# back as a job error, not a dropped reply.
UNPACK_TIMEOUT_S = 120
GRADE_GOOD_TIMEOUT_S = 360
GRADE_MUTANT_TIMEOUT_S = 240


def gpu_grade_job(artifact_rel, sub_timeout_s, want_traj=False):
    """Exec code grading one artifact under JOB_ROOT (real sim, minutes)."""
    return f"""
import json, os, subprocess, sys, time
root = os.path.expanduser({JOB_ROOT!r})
j = os.path.join(root, 'judge')
art = os.path.join(root, {artifact_rel!r})
out = art + '.verdict.json'
t0 = time.perf_counter()
r = subprocess.run([sys.executable, os.path.join(j, '_grade.py'), art,
                    '--seed', '0', '--json', out, '--judge-dir', j]
                   + (['--traj-json', art + '.traj.json']
                      if {want_traj!r} else []),
                   capture_output=True, text=True, timeout={sub_timeout_s})
report.update(rc=r.returncode,
              verdict=json.load(open(out)) if os.path.exists(out) else None,
              grade_wall_s=round(time.perf_counter() - t0, 1),
              stderr=r.stderr[-400:])
tp = art + '.traj.json'
if os.path.exists(tp):
    report['world0_traj'] = json.load(open(tp))
"""


def gpu_exec(key, sid, code, timeout_s, label):
    """One exec call on the lease; returns the report dict.

    A transport error (dropped reply, connection reset, socket timeout)
    aborts the run naming this exec — it is retried once first, since a
    grade job is idempotent and a blip should not sink a minutes-long run.
    """
    for attempt in (1, 2):
        t0 = time.monotonic()
        try:
            st, executed = request(key, "POST", f"/sandboxes/{sid}/exec",
                                   {"code": code, "timeout_s": timeout_s},
                                   timeout=min(timeout_s + 60, 570))
        except (OSError, URLError, TimeoutError) as exc:
            dt = time.monotonic() - t0
            if attempt == 1:
                print(f"  [{label}] exec transport error after {dt:.0f} s: "
                      f"{type(exc).__name__}: {exc}; retrying once",
                      file=sys.stderr, flush=True)
                time.sleep(3)
                continue
            die(f"GPU exec ({label}) failed: transport error after retry: "
                f"{type(exc).__name__}: {exc}")
        break
    dt = time.monotonic() - t0
    if st != 200 or not isinstance(executed, dict):
        die(f"GPU exec ({label}): HTTP {st}")
    result = executed.get("result") or {}
    if result.get("ok") is not True:
        die(f"GPU job ({label}) failed: {(result.get('stderr') or '')[-500:]}")
    print(f"  [{label}] exec ok ({dt:.0f} s)", flush=True)
    return result.get("report") or {}


def run_gpu_path(key, demo_path, report_json=None):
    """Run the GPU path using the REST API (4 GiB VRAM slice lease)."""
    print("create GPU lease (4 GiB VRAM slice)...", flush=True)
    try:
        st, created = request(key, "POST", "/sandboxes",
                              {"accel": {"vram_gb": 4, "reserve": "exec"}})
    except (OSError, URLError, TimeoutError) as exc:
        die(f"GPU create failed: transport error: "
            f"{type(exc).__name__}: {exc}")
    if st != 201:
        die(f"GPU create: HTTP {st}; check GPU access, credit and capacity")
    sid = created["sandboxID"]
    if not isinstance(sid, str) or not sid.startswith("gl-") or not all(
        c.isascii() and (c.isalnum() or c == "-") for c in sid
    ):
        die(f"GPU create returned an unexpected lease id {sid!r}; it was not "
            "destroyed automatically, delete it with sandbox_kill")
    print(f"created {sid} (4 GiB VRAM slice)", flush=True)

    try:
        print("exec unpack + mutant generation on GPU lease...", flush=True)
        rep = gpu_exec(key, sid,
                       gpu_unpack_job(pack_judge_and_examples(demo_path)),
                       UNPACK_TIMEOUT_S, "unpack")
        mutant_list = rep.get("mutants") or []
        print(f"lease python {rep.get('python')}; "
              f"{len(mutant_list)} mutants generated", flush=True)

        print("grade known-good (full mode: CPU baseline + real GPU sweep; "
              "first grade pays the Warp cold-compile)...", flush=True)
        good = gpu_exec(key, sid,
                        gpu_grade_job("examples/good/sweep.json",
                                      GRADE_GOOD_TIMEOUT_S - 30,
                                      want_traj=True),
                        GRADE_GOOD_TIMEOUT_S, "grade good")
        verdict = good.get("verdict") or {}

        kills = {}
        for m in mutant_list:
            name, mode = m["name"], m["mode"]
            r = gpu_exec(key, sid,
                         gpu_grade_job(f"mutants/{name}.json",
                                       GRADE_MUTANT_TIMEOUT_S - 30),
                         GRADE_MUTANT_TIMEOUT_S, f"grade {name}")
            v = r.get("verdict") or {}
            gs = {g: x for g, x in (v.get("gates") or {}).items()
                  if isinstance(x, dict)}
            failed = [g for g, x in gs.items() if x.get("pass") is False]
            probs = {g: [str(p)[:110] for p in (x.get("problems") or [])[:3]]
                     for g, x in gs.items()}
            kills[name] = dict(mode=mode, rc=r.get("rc"), failed=failed,
                               gates={g: x.get("pass") for g, x in gs.items()},
                               problems=probs,
                               grade_wall_s=r.get("grade_wall_s"),
                               judge_error=None if v else
                               (r.get("stderr") or "")[-300:])

        report = {"unpack": rep, "good": good, "mutants": kills}
        if report_json:
            with open(report_json, "w") as fh:
                json.dump(report, fh, indent=2, sort_keys=True)
            print(f"wrote exec report: {report_json}")

        mutants = kills
        if verdict:
            gates = verdict.get("gates", {})
            ok = all(g.get("pass") for g in gates.values()) and verdict.get("judge_intact", False)
            timing = verdict.get("timing") or {}
            print(f"\ngpu-sim-sweep demo: {'PASS' if ok else 'FAIL'} (mode {verdict.get('mode')})")
            for name, g in sorted(gates.items()):
                print(f"  gate {name}: {'pass' if g.get('pass') else 'FAIL'}")
            pts = timing.get("points") or []
            if pts:
                print("  measured sweep (judge-ran, 4 GiB slice):")
                print(f"  {'nworld':>7} | {'steps/s':>11} | {'arm err':>7} | "
                      f"{'box z':>16} | {'1st step s':>10}")
                for p in pts:
                    if p.get("ok"):
                        print(f"  {p['nworld']:>7} | {p.get('steps_per_s', 0):>11,} | "
                              f"{p.get('arm_max_err', 0):>7.3f} | "
                              f"[{p.get('box_z_min', 0):.3f},{p.get('box_z_max', 0):.3f}] | "
                              f"{p.get('first_step_s', 0):>10.2f}")
                    else:
                        print(f"  {p['nworld']:>7} | {'FAILED':>11} | "
                              f"{str(p.get('error'))[:48]}")
            cpu_sps = timing.get("cpu_steps_per_s")
            top_sps = timing.get("top_steps_per_s")
            speedup = timing.get("speedup")
            if cpu_sps and top_sps:
                print(f"  CPU {cpu_sps:,.0f} steps/s, top GPU {top_sps:,.0f} steps/s"
                      + (f" (speedup x{speedup:.1f}, floor x{timing.get('speedup_floor')})"
                         if speedup is not None else ""))
            if timing.get("cold_compile_s"):
                print(f"  cold Warp compile (first step): {timing['cold_compile_s']} s;"
                      f" parity max err {timing.get('parity_max_err')} rad")
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
        # Transient control-plane errors (a 503 while a node is
        # unreachable, a dropped reply) must not fail an otherwise-clean
        # run: retry the delete, then retry the confirmation. A lease that
        # still will not confirm is reported by id and fails the run.
        for attempt in range(3):
            try:
                st, _ = request(key, "DELETE", f"/sandboxes/{sid}")
                if st in (200, 202, 204, 404):
                    break
            except (OSError, URLError, TimeoutError) as exc:
                print(f"run.py: DELETE {sid}: transport error: "
                      f"{type(exc).__name__}: {exc}",
                      file=sys.stderr, flush=True)
            if attempt < 2:
                time.sleep(3)
        gone = False
        for attempt in range(4):
            try:
                st, remaining = request(key, "GET", f"/sandboxes/{sid}")
            except (OSError, URLError, TimeoutError) as exc:
                print(f"run.py: GET {sid}: transport error: "
                      f"{type(exc).__name__}: {exc}",
                      file=sys.stderr, flush=True)
                st, remaining = -1, None
            if st == 404 or (
                st == 200 and isinstance(remaining, dict)
                and remaining.get("phase") == "dead"
            ):
                gone = True
                break
            if attempt < 3:
                time.sleep(3)
        if not gone:
            die(f"cleanup unconfirmed for {sid}: run sandbox_kill for this id")
        print(f"destroyed {sid}; verified absent or dead", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main",
                    help="repository ref to clone inside the sandbox")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox up and print its id")
    ap.add_argument("--gpu", action="store_true",
                    help="create a 4 GiB VRAM slice lease via REST API "
                         "(GPU access required on your key) for full judge")
    ap.add_argument("--report-json", metavar="PATH",
                    help="with --gpu: write the raw exec report dict "
                         "to PATH, e.g. media/data/report.json")
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
            f"sandbox/{DEMO_DIR}/examples/good/sweep.json",
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
        print(f"\ngpu-sim-sweep demo: {'PASS' if ok else 'FAIL'} "
              f"(mode {verdict.get('mode')})")
        for name, g in sorted(gates.items()):
            print(f"  gate {name}: {'pass' if g.get('pass') else 'FAIL'}")
        raise SystemExit(0 if ok else 1)
    die("no verdict JSON returned from the sandbox")


if __name__ == "__main__":
    main()
