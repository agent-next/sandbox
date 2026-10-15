#!/usr/bin/env python3
"""untrusted-code-isolation demo: one command, one disposable sandbox.

Creates an agent-next sandbox, clones this repository inside it, installs
the pinned judge toolchain, runs the judge self-test (10 single-edit
mutants must all be killed), then grades the known-good containment
runner against 10 hostile and 5 benign snippets — and always kills the
sandbox afterwards, confirming it is gone.

    python3 cookbook/untrusted-code-isolation/run.py [--ref main] [--keep]

Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

Standard library only. Wall time per step is printed.

The sandbox is the outer boundary of the demo: the hostile snippets are
real fork bombs, memory balloons and disk fillers, so run the judge
inside a disposable sandbox (or a VM you own), never on a machine that
hosts anything you care about.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/untrusted-code-isolation"
ARTIFACT = "examples/good/runner.py"
STEP_TIMEOUTS = {"clone": 300, "setup": 600, "selftest": 1800, "grade": 300}


def die(msg, code=1):
    print("run.py: %s" % msg, file=sys.stderr)
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
                          timeout=timeout and timeout + 60)
    dt = time.monotonic() - t0
    status = "ok" if proc.returncode == 0 else "exit %d" % proc.returncode
    print("  [%s] %s ... %s (%.0f s)" % (step, " ".join(args[:3]), status, dt),
          flush=True)
    return proc, dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main",
                    help="repository ref to clone inside the sandbox")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox up and print its id")
    ap.add_argument("--report-json", metavar="PATH",
                    help="write the verdict JSON here")
    args = ap.parse_args()

    total0 = time.monotonic()
    need_sbx()
    proc, _ = run("create", "sbx", "create", "--timeout-min", "30",
                  timeout=120, capture=True)
    if proc.returncode != 0:
        die("sbx create failed: %s" % (proc.stderr or "").strip())
    sbx_id = proc.stdout.strip().splitlines()[-1]
    print("sandbox: %s (template default)" % sbx_id)

    verdict = None
    try:
        def exec_step(name, cmd):
            p, _ = run(name, "sbx", "exec", sbx_id, "--timeout",
                       str(STEP_TIMEOUTS[name]), "--", *cmd)
            if p.returncode != 0:
                die("step %s failed in sandbox %s (exit %d)"
                    % (name, sbx_id, p.returncode))
            return p

        exec_step("clone", ["git", "clone", "--depth", "1", "-b", args.ref,
                            REPO, "sandbox"])
        exec_step("setup", ["bash", "sandbox/%s/judge/setup.sh" % DEMO_DIR])
        exec_step("selftest",
                  ["bash", "sandbox/%s/judge/selftest.sh" % DEMO_DIR])
        exec_step("grade", ["bash", "sandbox/%s/judge/grade.sh" % DEMO_DIR,
                            "sandbox/%s/%s" % (DEMO_DIR, ARTIFACT),
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
            print("run.py: --keep: sandbox %s left running; "
                  "kill it with: sbx kill %s" % (sbx_id, sbx_id))
        else:
            run("kill", "sbx", "kill", sbx_id, timeout=120)
            proc, _ = run("list", "sbx", "list", timeout=60, capture=True)
            if sbx_id in (proc.stdout or ""):
                die("cleanup not confirmed: sandbox %s still live; "
                    "kill it with: sbx kill %s" % (sbx_id, sbx_id), 2)
            print("cleanup: sandbox %s killed and confirmed gone" % sbx_id)

    print("total: %.0f s" % (time.monotonic() - total0))
    if not verdict:
        die("no verdict JSON returned from the sandbox")
    if args.report_json:
        with open(args.report_json, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
        print("wrote verdict JSON: %s" % args.report_json)

    ok = all(g.get("pass") for g in verdict.get("gates", {}).values()) \
        and verdict.get("judge_intact", False)
    print("\nuntrusted-code-isolation demo: %s" % ("PASS" if ok else "FAIL"))
    for name, g in sorted(verdict.get("gates", {}).items()):
        line = "  gate %s: %s" % (name, "pass" if g.get("pass") else "FAIL")
        if name == "containment":
            line += "  (%d/%d hostile contained)" % (g.get("contained", 0),
                                                     g.get("total", 0))
        if name == "benign":
            line += "  (%d/%d benign exact)" % (g.get("matched", 0),
                                                g.get("total", 0))
        print(line)
        for problem in (g.get("problems") or [])[:5]:
            print("    %s" % problem)
    runs = verdict.get("runs", {})
    print("  hostile verdicts:")
    for name in ("fork_bomb", "memory_balloon", "infinite_loop",
                 "disk_filler", "read_shadow", "write_outside",
                 "outbound_socket", "background_daemon", "huge_stdout",
                 "sleep_forever"):
        r = runs.get(name, {})
        print("    %-18s %-8s %-12s %s"
              % (name, r.get("verdict", "?"), r.get("reason", "?"),
                 "ok" if r.get("pass") else "FAIL"))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
