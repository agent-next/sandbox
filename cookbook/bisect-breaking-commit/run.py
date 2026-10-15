#!/usr/bin/env python3
"""One-command run for the bisect-breaking-commit demo.

The parser test fails at HEAD.  This script does what the user asks their
agent: sweep commits 20..30 in parallel, one disposable agent-next sandbox per
suspect commit, and name the exact commit that introduced the regression with
the diff of it.

Steps: create one sandbox per suspect commit (plus the serial baseline on the
orchestrating machine) → each sandbox clones this repo at --ref (default
main), rebuilds the fixture and runs its one commit's suite → collect the
receipts → write the sweep report (the artifact the judge grades) → kill
every sandbox in a finally block and confirm with `sbx list`.

Requires the `sbx` CLI on PATH:
  pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
and SBX_API_KEY (or E2B_API_KEY) in the environment.

Usage: python3 run.py [--ref REF] [--keep] [--seed N]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_URL = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/bisect-breaking-commit"
SWEEP_FIRST, SWEEP_LAST = 20, 30
N_SANDBOXES = SWEEP_LAST - SWEEP_FIRST + 1
SEED = 20261015
TIMEOUT_MIN = "30"
PLANTED_INDEX = 25          # must match fixture/make_fixture.py


def scrub(text: str) -> str:
    for name in ("SBX_API_KEY", "E2B_API_KEY"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[redacted]")
    return text


def sbx(*args, timeout=120, capture=True):
    """Run one sbx command; return (exit_code, combined_output)."""
    cmd = ["sbx", *[str(a) for a in args]]
    p = subprocess.run(cmd, capture_output=capture, text=True,
                       timeout=timeout)
    out = scrub((p.stdout or "") + (p.stderr or "")) if capture else ""
    return p.returncode, out


def step(name, fn, *args, timeout=120):
    t0 = time.monotonic()
    rc, out = fn(*args, timeout=timeout)
    dt = time.monotonic() - t0
    print(f"[run] {name:<34} {dt:6.1f}s  exit={rc}", flush=True)
    return rc, out, dt


def make_one_sandbox(i: int):
    """Create one sandbox for suspect commit i; return (i, id) or raise."""
    rc, out = sbx("create", "--timeout-min", TIMEOUT_MIN, timeout=180)
    if rc != 0 or not out.strip():
        raise RuntimeError(f"sandbox create for commit {i} failed: "
                           f"{out.strip()}")
    return i, out.strip().splitlines()[-1].strip()


def parse_receipt(out: str, sid: str, i: int) -> dict:
    """Extract the receipt JSON from a combined `sbx exec` output.

    sbx exec returns the command's stdout and stderr as separate buffers
    (stdout written first, then stderr), while one_commit.sh sends ALL
    progress noise to stderr and prints the single JSON receipt line to
    stdout.  The receipt is therefore a JSON line in the combined output —
    but NOT the last line (the suite's own stderr follows it), so scan for
    the last line that parses as a receipt object instead.
    """
    for line in reversed(out.strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and "index" in obj and "sha" in obj:
            if obj["index"] != i:
                raise RuntimeError(f"sandbox {sid} (commit {i}) printed a "
                                   f"receipt for commit {obj['index']}:\n"
                                   f"{out.strip()}")
            return obj
    raise RuntimeError(f"sandbox {sid} (commit {i}) printed no receipt "
                       f"JSON:\n{out.strip()}")


def run_one_sandbox(sid: str, ref: str, i: int) -> dict:
    """Clone the repo in sandbox `sid`, run sweep/one_commit.sh for index i."""
    cmd = ("git clone --depth 1 -b {ref} {url} repo && "
           "cd repo/{demo} && FIXTURE_DIR=/tmp/fixture-{i} "
           "bash sweep/one_commit.sh {i}").format(
               ref=ref, url=REPO_URL, demo=DEMO_DIR, i=i)
    rc, out = sbx("exec", sid, "--timeout", "600", "--",
                  "bash", "-c", cmd, timeout=660)
    if rc != 0:
        raise RuntimeError(f"sandbox {sid} (commit {i}) exec failed "
                           f"(exit {rc}):\n{out.strip()}")
    return parse_receipt(out, sid, i)


def serial_baseline(ref: str) -> float:
    """Serial sweep on this machine, one clone per commit (the baseline the
    speedup gate compares against).  Same work the sandboxes do, minus the
    create/kill latency — the honest serial floor for the sweep alone."""
    t0 = time.monotonic()
    workdir = Path("/tmp/serial-baseline")
    for i in range(SWEEP_FIRST, SWEEP_LAST + 1):
        rc, out = sbx_local_sweep(workdir, i)
        if rc != 0:
            raise RuntimeError(f"serial baseline failed at {i}: {out}")
    return time.monotonic() - t0


def sbx_local_sweep(workdir: Path, i: int):
    here = str(Path(__file__).resolve().parent)
    cmd = ["bash", "-c",
           f"cd {here} && FIXTURE_DIR={workdir}/fx bash sweep/one_commit.sh {i}"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return p.returncode, scrub((p.stdout or "") + (p.stderr or ""))


def negative_control(ref: str) -> dict:
    """Run the same sweep on the reverted fixture (in one sandbox): it must
    report 'no regression in range', never a commit SHA."""
    rc, out = sbx("create", "--timeout-min", TIMEOUT_MIN, timeout=180)
    if rc != 0 or not out.strip():
        raise RuntimeError(f"negative-control create failed: {out.strip()}")
    sid = out.strip().splitlines()[-1].strip()
    try:
        cmd = ("cd repo/{demo} && python3 -I fixture/make_fixture.py "
               "/tmp/fixture-rev --revert-planted && "
               "python3 -I - <<'PY'\n"
               "import concurrent.futures, json, subprocess, tempfile\n"
               "FIRST, LAST = 20, 30\n"
               "def one(i):\n"
               "    with tempfile.TemporaryDirectory() as td:\n"
               "        c = td + '/c'\n"
               "        subprocess.run(['git','clone','-q','/tmp/fixture-rev', c],"
               "check=True)\n"
               "        subprocess.run(['git','-C',c,'checkout','-q',"
               "'HEAD~%d' % (30-i)], check=True)\n"
               "        p = subprocess.run(['python3','test_suite.py'], cwd=c)\n"
               "        return i, p.returncode == 0\n"
               "with concurrent.futures.ThreadPoolExecutor(LAST-FIRST+1) as ex:\n"
               "    res = dict(ex.map(one, range(FIRST, LAST+1)))\n"
               "bad = [i for i in sorted(res) if not res[i]]\n"
               "print(json.dumps({'report': 'no regression in range' if not bad "
               "else 'first failing commit: index %d' % bad[0]}))\n"
               "PY").format(demo=DEMO_DIR)
        rc, out = sbx("exec", sid, "--timeout", "600", "--",
                      "bash", "-c",
                      f"git clone --depth 1 -b {ref} {REPO_URL} repo && " + cmd,
                      timeout=660)
        if rc != 0:
            raise RuntimeError(f"negative-control exec failed: {out.strip()}")
        return parse_negctrl(out, sid)
    finally:
        sbx("kill", sid, timeout=120)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", default="main",
                    help="git ref of this repo to clone in the sandboxes "
                         "(default: main)")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandboxes running and print their ids")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        sys.exit("run.py: export SBX_API_KEY (or E2B_API_KEY) first")

    ids: dict[int, str] = {}
    timings: dict[str, float] = {}
    report: dict = {}

    try:
        # --- create one sandbox per suspect commit, in parallel ------------
        print(f"[run] sweeping commits {SWEEP_FIRST}..{SWEEP_LAST} "
              f"({N_SANDBOXES} sandboxes in parallel)", flush=True)
        t0 = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(N_SANDBOXES) as ex:
            for i, sid in ex.map(make_one_sandbox,
                                 range(SWEEP_FIRST, SWEEP_LAST + 1)):
                ids[i] = sid
        timings["create_sandboxes"] = round(time.monotonic() - t0, 2)
        print(f"[run] created {len(ids)} sandboxes "
              f"in {timings['create_sandboxes']}s", flush=True)

        # --- every sandbox runs its commit (parallel wall) -----------------
        t0 = time.monotonic()
        receipts: dict[int, dict] = {}
        with concurrent.futures.ThreadPoolExecutor(N_SANDBOXES) as ex:
            futs = {ex.submit(run_one_sandbox, sid, args.ref, i): i
                    for i, sid in ids.items()}
            for fut in concurrent.futures.as_completed(futs):
                r = fut.result()
                receipts[r["index"]] = r
        timings["parallel_sweep_s"] = round(time.monotonic() - t0, 2)
        print(f"[run] parallel sweep: {timings['parallel_sweep_s']}s",
              flush=True)

        # --- serial baseline on this machine ------------------------------
        t0 = time.monotonic()
        serial_seconds = serial_baseline(args.ref)
        timings["serial_sweep_s"] = round(serial_seconds, 2)

        # --- derive the culprit from the receipts -------------------------
        bad = sorted(i for i, r in receipts.items() if not r["passed"])
        if bad:
            first = bad[0]
            culprit = receipts[first]
            evidence = {"n_minus_1_passes": receipts[first - 1]["passed"],
                        "n_fails": not culprit["passed"]}
        else:
            first, culprit, evidence = None, None, None

        # --- negative control (the same sweep on the reverted fixture) ----
        t0 = time.monotonic()
        neg = negative_control(args.ref)
        timings["negative_control_s"] = round(time.monotonic() - t0, 2)
        if neg["report"] != "no regression in range":
            raise RuntimeError(f"negative control failed: {neg}")

        if culprit is None:
            raise RuntimeError("sweep found no failing commit in range; "
                               "the fixture at ref "
                               f"{args.ref} does not reproduce the regression")

        report = {
            "identified_commit": culprit["sha"],
            "identified_index": culprit["index"],
            "evidence": evidence,
            "diff": culprit["diff"],
            "serial_seconds": serial_seconds,
            "parallel_seconds": timings["parallel_sweep_s"],
            "speedup": serial_seconds / timings["parallel_sweep_s"],
            "sandboxes_used": len(ids),
        }
        out = Path("sweep_report.json")
        out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\n[run] culprit: {report['identified_commit']} "
              f"(index {report['identified_index']})\n"
              f"[run] evidence: N-1 passes={evidence['n_minus_1_passes']}, "
              f"N fails={evidence['n_fails']}\n"
              f"[run] speedup : {report['speedup']:.2f}x "
              f"(serial {report['serial_seconds']:.1f}s vs parallel "
              f"{report['parallel_seconds']:.1f}s over "
              f"{len(ids)} sandboxes)\n"
              f"[run] report written to {out}", flush=True)

        # Judge the report (in this repo checkout, not in a sandbox).
        here = str(Path(__file__).resolve().parent)
        p = subprocess.run(
            ["bash", "-c", f"cd {here} && bash judge/grade.sh sweep_report.json "
             f"--json /tmp/bisect_verdict.json"],
            capture_output=True, text=True, timeout=1800)
        timings["grade_s"] = round(time.monotonic() - t0, 2)
        verdict = None
        vpath = Path("/tmp/bisect_verdict.json")
        if vpath.exists():
            verdict = json.loads(vpath.read_text())
        print(scrub(p.stdout), flush=True)
        if p.returncode != 0 or not (verdict and verdict.get("passed")):
            raise RuntimeError(f"judge rejected the report (exit "
                               f"{p.returncode}); see /tmp/bisect_verdict.json")

        print("\n[run] ======== verdict ========", flush=True)
        print(json.dumps(verdict, indent=2), flush=True)
        print("[run] PASS", flush=True)

    finally:
        # Always kill what we created, then confirm each id is gone.
        if args.keep:
            print(f"[run] --keep: sandboxes left running: "
                  f"{sorted(ids.values())}", flush=True)
        else:
            for i, sid in sorted(ids.items()):
                rc, _ = sbx("kill", sid, timeout=180)
            rc, listing = sbx("list", timeout=120)
            leftovers = [sid for sid in ids.values() if sid in listing]
            if leftovers:
                print(f"[run] ERROR: could not confirm cleanup of "
                      f"{leftovers}; run `sbx kill <id>` for each",
                      file=sys.stderr, flush=True)
                sys.exit(1)
            print(f"[run] confirmed: all {len(ids)} sandboxes are gone",
                  flush=True)


if __name__ == "__main__":
    main()
