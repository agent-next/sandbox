#!/usr/bin/env python3
"""One-command run for the bisect-breaking-commit demo.

The parser test fails at HEAD.  This script does what the user asks their
agent: sweep commits 20..30 in parallel, one disposable agent-next sandbox per
suspect commit, and name the exact commit that introduced the regression with
the diff of it — then let a judge it cannot fool grade the sweep report.

Self-contained: everything runs inside sandboxes that clone this repo at
--ref (default main), so the script works from any directory (no local
checkout of the repo is needed — only the `sbx` CLI and an API key).

Steps (each timed, each printed, each fatal on failure):
  1. sbx create x11 (one per suspect commit) — parallel
  2. each sandbox: clone repo at ref, run sweep/one_commit.sh <i>, print a
     receipt JSON; kill the sandbox as soon as its receipt is in
  3. one utility sandbox: clone repo, judge/setup.sh, judge/selftest.sh
     (proves the judge can fail before its verdict is trusted)
  4. serial baseline in the utility sandbox: the same 11 one_commit.sh runs,
     one after another (the honest serial floor for the sweep alone)
  5. negative control in the utility sandbox: the same sweep on the reverted
     fixture must report "no regression in range"
  6. judge/grade.sh on the sweep report → verdict JSON; PASS only if every
     gate passes
  7. always kill every sandbox this run created and confirm with sbx list

Requires the `sbx` CLI on PATH:
  pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
and SBX_API_KEY (or E2B_API_KEY) in the environment.

Usage: python3 run.py [--ref REF] [--keep] [--seed N]
"""

from __future__ import annotations

import argparse
import base64
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
# transient transport errors worth one retry (a retry is safe for every
# command this script issues: creates leak nothing we can name, execs are
# idempotent, killing an already-gone sandbox is not an error)
TRANSIENT = ("503", "bad gateway", "temporarily", "connection reset",
             "connection refused", "timeout occurred")


def scrub(text: str) -> str:
    for name in ("SBX_API_KEY", "E2B_API_KEY"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[redacted]")
    return text


def sbx(*args, timeout=120):
    """Run one sbx command with a single retry on transient transport
    errors; return (exit_code, combined_output)."""
    cmd = ["sbx", *[str(a) for a in args]]
    for attempt in (1, 2):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=timeout)
        except subprocess.TimeoutExpired:
            if attempt == 1:
                time.sleep(5)
                continue
            return 124, f"sbx {' '.join(str(a) for a in args)}: timed out " \
                       f"after {timeout}s"
        out = scrub((p.stdout or "") + (p.stderr or ""))
        if p.returncode != 0 and attempt == 1 and \
                any(t in out.lower() for t in TRANSIENT):
            time.sleep(5)
            continue
        return p.returncode, out
    raise AssertionError("unreachable")


def timed(name, fn, *args, **kwargs):
    t0 = time.monotonic()
    rc, out = fn(*args, **kwargs)
    dt = time.monotonic() - t0
    print(f"[run] {name:<34} {dt:6.1f}s  exit={rc}", flush=True)
    return rc, out, dt


class CleanupError(RuntimeError):
    pass


def kill_and_confirm(sid: str, what: str) -> None:
    """Kill one sandbox this run created and confirm via sbx list."""
    for attempt in (1, 2):
        rc, out = sbx("kill", sid, timeout=180)
        if rc == 0:
            break
        if attempt == 2:
            raise CleanupError(f"could not kill sandbox {sid} ({what}): "
                               f"rc={rc} {out.strip()}")
        time.sleep(5)
    rc, listing = sbx("list", timeout=120)
    if rc != 0:
        raise CleanupError(f"sandbox {sid} ({what}): sbx list failed "
                           f"(rc={rc}): {listing.strip()}")
    if sid in listing:
        raise CleanupError(f"sandbox {sid} ({what}) still in `sbx list` "
                           "after kill — run `sbx kill "
                           f"{sid}` by hand before it holds a slot")


def create_sandbox(what: str, registry: dict) -> str:
    """Create one sandbox and register its id immediately, so the finally
    block can kill it no matter how the run fails afterwards."""
    rc, out, _ = timed(f"create sandbox ({what})", sbx,
                       "create", "--timeout-min", TIMEOUT_MIN, timeout=180)
    if rc != 0 or not out.strip():
        raise RuntimeError(f"sandbox create for {what} failed "
                           f"(exit {rc}): {out.strip()[-400:]}")
    sid = out.strip().splitlines()[-1].strip()
    registry[what] = sid
    print(f"[run]   {what} -> {sid}", flush=True)
    return sid


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


def parse_tagged(out: str, begin: str, end: str) -> str:
    """Return the text between the BEGIN/END sentinels of a combined
    output (the reliable way to fetch multi-line JSON out of a sandbox)."""
    lines = out.splitlines()
    try:
        i = len(lines) - 1 - lines[::-1].index(begin)
        j = len(lines) - 1 - lines[::-1].index(end)
    except ValueError:
        raise RuntimeError(f"sentinels {begin}/{end} not found in output:\n"
                           f"{out.strip()[-800:]}")
    if j <= i:
        raise RuntimeError(f"sentinels out of order in output:\n"
                           f"{out.strip()[-800:]}")
    return "\n".join(lines[i + 1:j])


def run_one_sandbox(sid: str, ref: str, i: int) -> dict:
    """Clone the repo in sandbox `sid`, run sweep/one_commit.sh for index i,
    then kill the sandbox (its receipt is all we need from it)."""
    cmd = ("git clone --depth 1 -b {ref} {url} repo && "
           "cd repo/{demo} && FIXTURE_DIR=/tmp/fixture-{i} "
           "bash sweep/one_commit.sh {i}").format(
               ref=ref, url=REPO_URL, demo=DEMO_DIR, i=i)
    rc, out = sbx("exec", sid, "--timeout", "600", "--",
                  "bash", "-c", cmd, timeout=660)
    if rc != 0:
        raise RuntimeError(f"sandbox {sid} (commit {i}) exec failed "
                           f"(exit {rc}):\n{out.strip()[-800:]}")
    receipt = parse_receipt(out, sid, i)
    kill_and_confirm(sid, f"commit {i}")
    return receipt


def util_exec(sid: str, name: str, cmd: str, timeout_s: int) -> tuple[str, float]:
    """Run one step in the utility sandbox (repo already cloned at ~/repo);
    print its output, return (combined_output, wall_seconds)."""
    rc, out, dt = timed(name, sbx, "exec", sid, "--timeout", str(timeout_s),
                        "--", "bash", "-c", cmd, timeout=timeout_s + 60)
    if out.strip():
        print(scrub(_indent(out)), flush=True)
    if rc != 0:
        raise RuntimeError(f"{name} failed (exit {rc}) in sandbox {sid} — "
                           "never printing ok for a failed step; "
                           f"output above")
    return out, dt


def _indent(text: str) -> str:
    return "\n".join(f"      {ln}" for ln in text.strip().splitlines())


def negative_control_cmd() -> str:
    """The same sweep on the reverted fixture, inside the utility sandbox:
    it must report 'no regression in range', never a commit SHA."""
    return ("cd repo/{demo} && "
            "python3 -I fixture/make_fixture.py /tmp/fixture-rev "
            "--revert-planted >&2 && "
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
            "print('NEGCTRL_BEGIN')\n"
            "print(json.dumps({'report': 'no regression in range' if not bad "
            "else 'first failing commit: index %d' % bad[0]}))\n"
            "print('NEGCTRL_END')\n"
            "PY").format(demo=DEMO_DIR)


def grade_cmd(report_b64: str) -> str:
    return (
        "cd repo/{demo} && "
        "python3 -c 'import base64,sys;"
        "open(\"/tmp/sweep_report.json\",\"wb\")."
        "write(base64.b64decode(sys.argv[1]))' {b64} && "
        "set +e; bash judge/grade.sh /tmp/sweep_report.json "
        "--json /tmp/bisect_verdict.json; rc=$?; set -e; "
        "echo GRADE_RC=$rc; "
        "echo VERDICT_BEGIN; cat /tmp/bisect_verdict.json; echo VERDICT_END; "
        "test $rc -eq 0"
    ).format(demo=DEMO_DIR, b64=report_b64)


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
    created: dict[str, str] = {}      # every sandbox this run created
    timings: dict[str, float] = {}
    util_sid: str | None = None
    report: dict = {}
    verdict: dict | None = None

    try:
        # --- 1. one sandbox per suspect commit, in parallel -----------------
        print(f"[run] ref {args.ref}: sweeping commits {SWEEP_FIRST}.."
              f"{SWEEP_LAST} ({N_SANDBOXES} sandboxes in parallel)",
              flush=True)
        t0 = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(N_SANDBOXES) as ex:
            for i, sid in ex.map(
                    lambda i: (i, create_sandbox(f"commit {i}", created)),
                    range(SWEEP_FIRST, SWEEP_LAST + 1)):
                ids[i] = sid
        timings["create_sandboxes_s"] = round(time.monotonic() - t0, 2)
        print(f"[run] created {len(ids)} sandboxes "
              f"in {timings['create_sandboxes_s']}s", flush=True)

        # --- 2. every sandbox runs its commit (parallel wall) --------------
        t0 = time.monotonic()
        receipts: dict[int, dict] = {}
        with concurrent.futures.ThreadPoolExecutor(N_SANDBOXES) as ex:
            futs = {ex.submit(run_one_sandbox, sid, args.ref, i): i
                    for i, sid in ids.items()}
            for fut in concurrent.futures.as_completed(futs):
                r = fut.result()
                receipts[r["index"]] = r
                print(f"[run]   commit {r['index']:>2}: "
                      f"{'pass' if r['passed'] else 'FAIL'} "
                      f"({r['sha'][:12]})", flush=True)
        timings["parallel_sweep_s"] = round(time.monotonic() - t0, 2)
        print(f"[run] parallel sweep: {timings['parallel_sweep_s']}s "
              f"(sandboxes killed as receipts arrived)", flush=True)

        # --- 3. utility sandbox: setup + selftest --------------------------
        util_sid = create_sandbox("setup/selftest/serial/control/grade",
                                  created)
        util_exec(util_sid, "clone repo (utility)",
                  f"git clone --depth 1 -b {args.ref} {REPO_URL} repo",
                  300)
        util_exec(util_sid, "judge/setup.sh",
                  f"cd repo/{DEMO_DIR} && bash judge/setup.sh", 600)
        _, dt = util_exec(util_sid, "judge/selftest.sh",
                          f"cd repo/{DEMO_DIR} && bash judge/selftest.sh",
                          1500)
        timings["selftest_s"] = round(dt, 2)

        # --- 4. serial baseline in the utility sandbox ---------------------
        serial_cmd = ("cd repo/{demo} && r=0; for i in $(seq {first} {last}); "
                      "do FIXTURE_DIR=/tmp/fixture-serial bash "
                      "sweep/one_commit.sh $i >/dev/null 2>&1 || r=1; done; "
                      "exit $r").format(demo=DEMO_DIR, first=SWEEP_FIRST,
                                        last=SWEEP_LAST)
        _, dt = util_exec(util_sid, "serial baseline (11 commits, 1 machine)",
                          serial_cmd, 1500)
        timings["serial_sweep_s"] = round(dt, 2)
        serial_seconds = dt

        # --- 5. negative control on the reverted fixture -------------------
        out, dt = util_exec(util_sid, "negative control (reverted fixture)",
                            negative_control_cmd(), 900)
        timings["negative_control_s"] = round(dt, 2)
        neg = json.loads(parse_tagged(out, "NEGCTRL_BEGIN", "NEGCTRL_END"))
        if neg["report"] != "no regression in range":
            raise RuntimeError(f"negative control failed: {neg}")

        # --- 6. derive the culprit from the receipts -----------------------
        bad = sorted(i for i, r in receipts.items() if not r["passed"])
        if not bad:
            raise RuntimeError("sweep found no failing commit in range; "
                               "the fixture at ref "
                               f"{args.ref} does not reproduce the regression")
        first = bad[0]
        culprit = receipts[first]
        evidence = {"n_minus_1_passes": receipts[first - 1]["passed"],
                    "n_fails": not culprit["passed"]}

        report = {
            "identified_commit": culprit["sha"],
            "identified_index": culprit["index"],
            "evidence": evidence,
            "diff": culprit["diff"],
            "serial_seconds": round(serial_seconds, 3),
            "parallel_seconds": timings["parallel_sweep_s"],
            "speedup": round(serial_seconds / timings["parallel_sweep_s"], 3),
            "sandboxes_used": len(ids),
        }
        out_path = Path("sweep_report.json").resolve()
        out_path.write_text(json.dumps(report, indent=2) + "\n")

        # --- 7. grade the report in the utility sandbox --------------------
        report_b64 = base64.b64encode(
            json.dumps(report).encode()).decode("ascii")
        out, dt = util_exec(util_sid, "judge/grade.sh sweep_report.json",
                            grade_cmd(report_b64), 1800)
        timings["grade_s"] = round(dt, 2)
        verdict = json.loads(parse_tagged(out, "VERDICT_BEGIN",
                                          "VERDICT_END"))
        Path("bisect_verdict.json").write_text(
            json.dumps(verdict, indent=2) + "\n")

        print(f"\n[run] culprit  : {report['identified_commit']} "
              f"(index {report['identified_index']})\n"
              f"[run] evidence : N-1 passes={evidence['n_minus_1_passes']}, "
              f"N fails={evidence['n_fails']}\n"
              f"[run] speedup  : {report['speedup']:.2f}x "
              f"(serial {report['serial_seconds']:.1f}s vs parallel "
              f"{report['parallel_seconds']:.1f}s over "
              f"{len(ids)} sandboxes)\n"
              f"[run] report   : {out_path}", flush=True)

        if not verdict.get("passed"):
            failed = verdict.get("failed_gate", "?")
            raise RuntimeError(f"judge rejected the report at gate "
                               f"'{failed}'; verdict in bisect_verdict.json")

        print("\n[run] ======== verdict ========", flush=True)
        print(json.dumps(verdict, indent=2), flush=True)
        print("\n[run] timings:", flush=True)
        for k in sorted(timings):
            print(f"[run]   {k:<26} {timings[k]:>8.2f}s", flush=True)
        print("[run] PASS", flush=True)

    finally:
        # Always kill what we created (workers already killed their own;
        # a re-kill of a gone sandbox is not an error), then confirm each
        # id is gone — naming ids we could not confirm.
        if args.keep:
            print(f"[run] --keep: sandboxes left running: "
                  f"{sorted(created.values())}", flush=True)
        else:
            cleanup_failures = []
            to_kill = sorted(created.items())
            for sid, what in to_kill:
                try:
                    kill_and_confirm(sid, what)
                except CleanupError as exc:
                    cleanup_failures.append(str(exc))
            if cleanup_failures:
                print("[run] ERROR: cleanup could not be confirmed —\n  "
                      + "\n  ".join(cleanup_failures), file=sys.stderr,
                      flush=True)
                sys.exit(1)
            print(f"[run] confirmed: all {len(to_kill)} sandboxes this run "
                  "created are gone (`sbx list` shows none of their ids)",
                  flush=True)


if __name__ == "__main__":
    main()
