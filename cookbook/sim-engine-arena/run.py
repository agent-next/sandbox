#!/usr/bin/env python3
"""sim-engine-arena demo: one command, one disposable sandbox, one verdict.

Creates an agent-next sandbox, clones this repository inside it, installs
the pinned judge toolchain (mujoco 3.8.1), runs the judge self-test, then
grades the known-good MuJoCo port of the arena scene spec — and always
kills the sandbox afterwards, confirming it is gone.

    python3 cookbook/sim-engine-arena/run.py [--ref main] [--keep] [--gpu]

Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

--gpu adds an optional lane after the CPU verdict: a 4 GiB VRAM slice
lease over the REST API (exactly like cookbook/small-gpu/run.py) that
replays the good port's four MJCF models (examples/good/mjcf/) with
mujoco_warp 3.8.1 and scores the replays against the same oracles. The
GPU row is reported in the summary but never gates the exit code; if the
lease's stack differs from the pinned versions, that is reported as a
lease_stack mismatch. The lease is always DELETEd in a finally and the
DELETE confirmed with a GET (404 = gone).

Standard library only. Wall time per step and the GPU lease lifecycle are
printed.
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
DEMO_DIR = "cookbook/sim-engine-arena"
STEP_TIMEOUTS = {"clone": 300, "setup": 900, "selftest": 900, "grade": 900}
API = "https://api.sbx.agent-next.com"
GPU_VRAM_GB = 4
THETA0_RAD = 0.1          # pendulum release angle, from judge/spec.json


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
    proc = subprocess.run(args, capture_output=capture, text=True,
                          timeout=timeout and timeout + 30)
    dt = time.monotonic() - t0
    status = "ok" if proc.returncode == 0 else f"exit {proc.returncode}"
    print(f"  [{step}] {' '.join(args[:3])} ... {status} ({dt:.0f} s)",
          flush=True)
    return proc, dt


def request(key, method, path, body=None, timeout=900):
    """-> (status, parsed-body-or-None); on HTTP error, -> (status, error body)."""
    data = None if body is None else json.dumps(body).encode()
    req = Request(API + path, data=data, method=method,
                  headers={"X-API-Key": key, "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else None
        except ValueError:
            return exc.code, {"message": raw.decode("utf-8", "replace")[:500]}


# ---------------------------------------------------------------- GPU lane

GPU_JOB = """
import json, sys, time
import mujoco, mujoco_warp, warp as wp
report = {"versions": {"mujoco": mujoco.__version__,
                       "mujoco_warp": mujoco_warp.__version__,
                       "warp": wp.__version__,
                       "python": sys.version.split()[0]}}
fail = [f"{k} {report['versions'].get(k, '?')} != {v}"
        for k, v in {"mujoco": "3.8.1", "mujoco_warp": "3.8.1"}.items()
        if report["versions"].get(k) != v]
report["lease_stack_ok"] = not fail
report["lease_stack_problems"] = fail
dt = 0.001
SCEN = {"drop": {"xml": "model_drop.xml", "duration": 1.5},
        "incline_stick": {"xml": "model_incline_stick.xml", "duration": 1.0},
        "incline_slide": {"xml": "model_incline_slide.xml", "duration": 1.0},
        "pendulum": {"xml": "model_pendulum.xml", "duration": 10.0}}
for name, item in SCEN.items():
    t0 = time.perf_counter()
    try:
        m = mujoco.MjModel.from_xml_path(item["xml"])
        m.opt.timestep = dt
        d = mujoco.MjData(m)
        if name == "pendulum":
            # hinge about +y; the spec's theta (+ toward +x) is -qpos
            d.qpos[m.jnt_qposadr[0]] = -__THETA0__
        mujoco.mj_forward(m, d)
        mm = mujoco_warp.put_model(m)
        dd = mujoco_warp.put_data(m, d, nworld=1, nconmax=64, njmax=256)
        bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "mover")
        n = int(round(item["duration"] / dt))
        dec = max(1, n // 2000)
        # first step also cold-compiles the warp kernels: ~25 s per fresh
        # lease, reported as setup time, not sim time
        tc0 = time.perf_counter()
        mujoco_warp.step(mm, dd)
        wp.synchronize()
        compile_s = time.perf_counter() - tc0
        tt, pos = [0.0], [dd.xpos.numpy()[0, bid].tolist()]
        qpos = [float(dd.qpos.numpy()[0, m.jnt_qposadr[0]])]
        for i in range(1, n + 1):
            mujoco_warp.step(mm, dd)
            if i % dec == 0 or i == n:
                tt.append(i * dt)
                pos.append(dd.xpos.numpy()[0, bid].tolist())
                qpos.append(float(dd.qpos.numpy()[0, m.jnt_qposadr[0]]))
        wp.synchronize()
        report[name] = {"t": tt, "pos": pos, "qpos": qpos,
                        "compile_s": round(compile_s, 2),
                        "sim_s": round(time.perf_counter() - t0 - compile_s, 2)}
    except Exception as e:
        report[name] = {"error": type(e).__name__ + ": " + str(e)[:200]}
"""


def load_oracle_helpers(demo_path):
    """Import the judge's oracle math (host-side; agents never see this)."""
    sys.path.insert(0, os.path.join(demo_path, "judge"))
    import _grade
    return _grade


def score_gpu_lane(report, _grade, spec):
    """Score the mujoco_warp replays against the same analytic oracles."""
    exp = _grade.oracle_values(spec)
    scored = {}
    for name, sc in report.items():
        if name in ("versions", "lease_stack_ok", "lease_stack_problems"):
            continue
        if "error" in sc:
            scored[name] = {"error": sc["error"]}
            continue
        t, pos = sc["t"], sc["pos"]
        try:
            if name == "drop":
                rows = {"t": t, "z": [p[2] for p in pos]}
            elif name.startswith("incline"):
                rows = {"t": t, "x": [p[0] for p in pos],
                        "z": [p[2] for p in pos]}
            elif name == "pendulum":
                # the mover body frame origin IS the anchor (the bob hangs at
                # (0, 0, -L) in body frame), so theta comes from the hinge
                # angle itself: hinge about +y turns bob to (-L sin q, 0, ...),
                # and the spec's theta (+ toward +x) is -q
                rows = {"t": t, "theta": [-v for v in sc["qpos"]]}
            scored[name] = _grade.analyze(name, rows, exp[name], spec)
        except Exception as exc:
            scored[name] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    return scored


def run_gpu_lane(key, demo_path, report_json=None):
    """Replay the good port's MJCF on a GPU slice with mujoco_warp; report only."""
    mjdir = os.path.join(demo_path, "examples", "good", "mjcf")
    want = ["model_%s.xml" % n for n in
            ("drop", "incline_stick", "incline_slide", "pendulum")]
    missing = [w for w in want if not os.path.exists(os.path.join(mjdir, w))]
    if missing:
        die("gpu lane needs examples/good/mjcf/ with " + ", ".join(missing), 2)

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        # normalized members: the lease worker cannot read files that keep the
        # builder's uid/gid/uname, so ship uid=gid=0, mode 0644, no names
        for name in sorted(os.listdir(mjdir)):
            with open(os.path.join(mjdir, name), "rb") as fh:
                data_bytes = fh.read()
            info = tarfile.TarInfo(name=name)
            info.size = len(data_bytes)
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            tf.addfile(info, io.BytesIO(data_bytes))
    payload = base64.b64encode(buf.getvalue()).decode()
    # the exec endpoint runs each job with cwd=/ (read-only, uid 1000); only
    # $HOME is writable, so extract the models there and chdir into it
    job = ("import base64, io, os, tarfile\n"
           "_d = os.path.expanduser('~/arena')\n"
           "os.makedirs(_d, exist_ok=True)\n"
           "os.chdir(_d)\n"
           "_t = tarfile.open(fileobj=io.BytesIO(base64.b64decode('%s')), "
           "mode='r:gz')\n"
           "for _m in _t.getmembers():\n"
           "    if _m.isfile():\n"
           "        open(_m.name, 'wb').write(_t.extractfile(_m).read())\n"
           % payload) \
        + GPU_JOB.replace("__THETA0__", repr(THETA0_RAD))

    print(f"gpu: creating lease ({GPU_VRAM_GB} GiB VRAM slice)...", flush=True)
    t0 = time.monotonic()
    for attempt in range(3):
        st, created = request(key, "POST", "/sandboxes",
                              {"accel": {"vram_gb": GPU_VRAM_GB,
                                         "reserve": "exec"}})
        if st == 201:
            break
        print(f"gpu: lease create HTTP {st} (attempt {attempt + 1}); "
              "no free seat is a capacity condition, retrying", flush=True)
        time.sleep(10 * (attempt + 1))
    if st != 201:
        die(f"gpu: lease create HTTP {st}; GPU lane skipped "
            "(the CPU verdict above is unaffected)", 1)
    sid = created["sandboxID"]
    print(f"gpu: lease {sid} created "
          f"({time.monotonic() - t0:.0f} s)", flush=True)
    try:
        print("gpu: running mujoco_warp replay (warp kernels cold-compile "
              "~25 s per fresh lease; that is setup time, not sim time)...",
              flush=True)
        t0 = time.monotonic()
        for attempt in range(4):
            st, executed = request(key, "POST", f"/sandboxes/{sid}/exec",
                                   {"code": job, "timeout_s": 600})
            if st == 200:
                break
            reason = ""
            if isinstance(executed, dict):
                reason = str(executed.get("message") or "")[:300]
            print(f"gpu: exec HTTP {st} (attempt {attempt + 1}) {reason}",
                  flush=True)
            if st == 409 and "job" in reason and "failed" in reason:
                # a 409 carrying "lease ... job N failed: <python error>" is the
                # job itself crashing, which is deterministic: retrying cannot
                # fix it, so fail now with the reason instead of burning retries
                die(f"gpu: exec job failed: {reason}", 1)
            time.sleep(5 * (attempt + 1))
        print(f"gpu: exec round trip {time.monotonic() - t0:.0f} s "
              f"(HTTP {st})", flush=True)
        if st != 200 or not isinstance(executed, dict):
            die(f"gpu: exec HTTP {st} after retries; GPU lane skipped "
                "(the CPU verdict above is unaffected)", 1)
        result = executed.get("result") or {}
        if result.get("ok") is not True:
            die(f"gpu: job failed: {result.get('stderr', '')[-500:]}", 1)
        report = result.get("report") or {}
        _grade = load_oracle_helpers(demo_path)
        with open(os.path.join(demo_path, "judge", "spec.json")) as fh:
            spec = json.load(fh)
        report["scored"] = score_gpu_lane(report, _grade, spec)
        return report
    finally:
        print(f"gpu: destroying lease {sid}...", flush=True)
        try:
            request(key, "DELETE", f"/sandboxes/{sid}")
        except Exception as exc:
            die(f"cleanup failed for lease {sid}: {exc}; it may still be "
                f"live: DELETE /sandboxes/{sid}", 2)
        try:
            st, remaining = request(key, "GET", f"/sandboxes/{sid}")
        except Exception as exc:
            die(f"cleanup unconfirmed for lease {sid} ({exc}); it may "
                f"still be live: DELETE /sandboxes/{sid}", 2)
        if st != 404 and not (st == 200 and isinstance(remaining, dict)
                              and remaining.get("phase") == "dead"):
            die(f"cleanup unconfirmed for lease {sid}: HTTP {st}; it may "
                f"still be live: DELETE /sandboxes/{sid}", 2)
        print(f"gpu: lease {sid} deleted; GET confirms gone (404)", flush=True)


# ---------------------------------------------------------------- main

def confirm_gone(sbx_id):
    """Exit 2 unless `sbx list` succeeds and no longer shows the sandbox."""
    proc, _ = run("list", "sbx", "list", timeout=60, capture=True)
    if sbx_id in (proc.stdout or ""):
        die(f"cleanup not confirmed: sandbox {sbx_id} still live; "
            "kill it with: sbx kill " + sbx_id, 2)
    print(f"cleanup: sandbox {sbx_id} killed and confirmed gone")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main",
                    help="repository ref to clone inside the sandbox")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox up and print its id")
    ap.add_argument("--gpu", action="store_true",
                    help="also replay the good port's MJCF on a 4 GiB VRAM "
                         "slice with mujoco_warp (reported, never gating)")
    ap.add_argument("--report-json", metavar="PATH",
                    help="write the CPU verdict JSON here")
    args = ap.parse_args()

    total0 = time.monotonic()
    need_sbx()
    proc, _ = run("create", "sbx", "create", "--timeout-min", "30",
                  timeout=120, capture=True)
    if proc.returncode != 0:
        die(f"sbx create failed: {proc.stderr.strip()}")
    sbx_id = proc.stdout.strip().splitlines()[-1]
    print(f"sandbox: {sbx_id} (template default)")

    verdict = None
    try:
        def exec_step(name, cmd):
            proc, _ = run(name, "sbx", "exec", sbx_id, "--timeout",
                          str(STEP_TIMEOUTS[name]), "--", *cmd)
            if proc.returncode != 0:
                die(f"step {name} failed in sandbox {sbx_id} "
                    f"(exit {proc.returncode})")
            return proc

        exec_step("clone", ["git", "clone", "--depth", "1", "-b", args.ref,
                            REPO, "sandbox"])
        exec_step("setup", ["bash", f"sandbox/{DEMO_DIR}/judge/setup.sh"])
        exec_step("selftest", ["bash", f"sandbox/{DEMO_DIR}/judge/selftest.sh"])
        exec_step("grade", ["bash", f"sandbox/{DEMO_DIR}/judge/grade.sh",
                            f"sandbox/{DEMO_DIR}/examples/good/sim.py",
                            "--json", "/tmp/verdict.json"])
        proc, _ = run("cat", "sbx", "exec", sbx_id, "--timeout", "60", "--",
                      "cat", "/tmp/verdict.json", capture=True)
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
            confirm_gone(sbx_id)

    gpu_report = None
    if args.gpu:
        key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
        gpu_report = run_gpu_lane(key, os.path.dirname(os.path.abspath(__file__)))

    print(f"total: {time.monotonic() - total0:.0f} s")
    if not verdict:
        die("no verdict JSON returned from the sandbox")
    if args.report_json:
        if gpu_report:
            # keep every measured number (lease versions, compile/sim wall
            # times, per-scenario scores) in one JSON for later media rounds
            verdict["gpu"] = {k: gpu_report.get(k) for k in
                              ("versions", "lease_stack_ok",
                               "lease_stack_problems", "scored")}
            verdict["gpu"]["wall_s"] = {
                n: {"compile_s": (gpu_report.get(n) or {}).get("compile_s"),
                    "sim_s": (gpu_report.get(n) or {}).get("sim_s")}
                for n in ("drop", "incline_stick", "incline_slide", "pendulum")
                if isinstance(gpu_report.get(n), dict)}
        with open(args.report_json, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
        print(f"wrote verdict JSON: {args.report_json}")

    ok = all(g.get("pass") for g in verdict.get("gates", {}).values()) \
        and verdict.get("judge_intact", False)
    print(f"\nsim-engine-arena demo: {'PASS' if ok else 'FAIL'}")
    for name, g in sorted(verdict.get("gates", {}).items()):
        print(f"  gate {name}: {'pass' if g.get('pass') else 'FAIL'}")
    for name, s in sorted(verdict.get("scenarios", {}).items()):
        o = s.get("oracle", {})
        detail = ""
        if "t_contact" in o:
            detail = (f"t_contact={o['t_contact']:.4f} s "
                      f"({o['t_contact_err'] * 100:+.2f}%)")
        elif o.get("accel") is not None:
            detail = (f"a={o['accel']:.4f} m/s^2 "
                      f"({o['accel_err'] * 100:+.2f}%)")
        elif "period" in o:
            detail = f"T={o['period']:.4f} s ({o['period_err'] * 100:+.2f}%)"
        elif "state" in o:
            detail = f"state={o['state']} travel={o['travel_m'] * 1000:.1f} mm"
        print(f"  {name}: {'ok' if o.get('pass') else 'FAIL'}  {detail}")
    if gpu_report:
        print("  gpu lane (mujoco_warp replay; reported, never gating):")
        print(f"    lease versions: {gpu_report.get('versions')}")
        if not gpu_report.get("lease_stack_ok", False):
            print(f"    lease stack mismatch: "
                  f"{gpu_report.get('lease_stack_problems')}")
        for name, m in sorted((gpu_report.get("scored") or {}).items()):
            if "error" in m:
                print(f"    {name}: ERROR {m['error']}")
            elif "t_contact" in m:
                print(f"    {name}: {'pass' if m.get('pass') else 'FAIL'} "
                      f"t_contact={m['t_contact']:.4f} s")
            elif m.get("accel") is not None:
                print(f"    {name}: {'pass' if m.get('pass') else 'FAIL'} "
                      f"a={m['accel']:.4f} m/s^2")
            elif "travel_m" in m:
                print(f"    {name}: {'pass' if m.get('pass') else 'FAIL'} "
                      f"state={m['state']} travel={m['travel_m'] * 1000:.1f} mm")
            elif "period" in m:
                print(f"    {name}: {'pass' if m.get('pass') else 'FAIL'} "
                      f"T={m['period']:.4f} s")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
