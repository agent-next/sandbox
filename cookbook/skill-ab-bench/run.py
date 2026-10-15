#!/usr/bin/env python3
"""skill-ab-bench demo: one command, one disposable sandbox, one verdict.

Creates an agent-next sandbox, clones this repository inside it, installs the
pinned judge toolchain, runs the skill A/B bench, runs the judge's self-test,
grades the experiment the bench just produced, and prints the verdict -- then
always kills the sandbox and confirms it is gone.

    python3 cookbook/skill-ab-bench/run.py [--ref main] [--keep]
                                           [--seed N] [--bootstrap N]

Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

Isolation: the bench answers every (arm, task) pair in its own fresh
interpreter with its own working directory, inside the sandbox -- the pairs
cannot see each other's work.  The sandbox is the disposable outer boundary
(pinned toolchain, no host state, destroyed afterwards); it is not one
sandbox per pair, which would mean re-cloning this repository 48 times to
re-run 48 deterministic policy scripts that share no state.

Standard library only.  Wall time is printed per step.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/skill-ab-bench"
DEFAULT_SEED = 20261014

# sbx exec's default timeout is 60 s; every step below needs more, because a
# cold sandbox pays for the clone and the tool install.  The bench itself is
# 48 short-lived interpreters, so it gets the largest budget.
STEP_TIMEOUTS = {
    "clone": 300,
    "setup": 600,
    "bench": 900,
    "selftest": 900,
    "grade": 300,
    "grade-good": 300,
}


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main",
                    help="repository ref to clone inside the sandbox")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox up and print its id")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED,
                    help="seed for the bench and the bootstrap CI")
    ap.add_argument("--bootstrap", type=int, default=10000,
                    help="bootstrap resamples the judge uses")
    args = ap.parse_args()

    total0 = time.monotonic()
    need_sbx()

    proc, _ = run("create", "sbx", "create", "--timeout-min", "30",
                  timeout=120, capture=True)
    if proc.returncode != 0:
        die(f"sbx create failed: {proc.stderr.strip()}")
    sbx_id = proc.stdout.strip().splitlines()[-1]
    if not sbx_id:
        die("sbx create printed no sandbox id")
    print(f"sandbox: {sbx_id} (template default)")

    verdict = None
    good_verdict = None
    bench_summary = []
    try:
        def exec_step(name, cmd, capture=False, allowed=(0,)):
            """Run one command in the sandbox; `allowed` exit codes pass.

            A grade is expected to exit 1 when a gate fails: that is a
            verdict, not a broken step, and it must be reported rather than
            swallowed.  Anything outside `allowed` is a real failure.
            """
            proc, _ = run(name, "sbx", "exec", sbx_id,
                          "--timeout", str(STEP_TIMEOUTS[name]), "--", *cmd,
                          capture=capture)
            if proc.returncode not in allowed:
                detail = (proc.stderr or proc.stdout or "").strip()[-400:]
                die(f"step {name} failed in sandbox {sbx_id} "
                    f"(exit {proc.returncode}): {detail}")
            return proc

        exec_step("clone", [
            "git", "clone", "--depth", "1", "-b", args.ref, REPO, "sandbox"])
        exec_step("setup", ["bash", f"sandbox/{DEMO_DIR}/judge/setup.sh"])

        # The bench: 16 tasks x 3 arms, each pair in its own process.
        bench = exec_step("bench", [
            "python3", "-I", f"sandbox/{DEMO_DIR}/judge/bench.py",
            "/tmp/bench", "--seed", str(args.seed)], capture=True)
        bench_summary = [ln for ln in bench.stdout.splitlines()
                         if ln.startswith(("bench:", "  "))]
        for line in bench_summary:
            print(f"    {line}")

        exec_step("selftest", ["bash", f"sandbox/{DEMO_DIR}/judge/selftest.sh"])

        # Grade the record the bench just produced, and the committed one.
        # exit 1 is a "fail" verdict and is reported below, not raised here.
        for step, target, out in (("grade", "/tmp/bench", "/tmp/verdict.json"),
                                  ("grade-good", f"sandbox/{DEMO_DIR}/examples/good",
                                   "/tmp/verdict-good.json")):
            exec_step(step, [
                "bash", f"sandbox/{DEMO_DIR}/judge/grade.sh", target,
                "--seed", str(args.seed), "--bootstrap", str(args.bootstrap),
                "--json", out], allowed=(0, 1))

        for name, target in (("verdict", "/tmp/verdict.json"),
                             ("good", "/tmp/verdict-good.json")):
            proc, _ = run(f"cat-{name}", "sbx", "exec", sbx_id,
                          "--timeout", "60", "--", "cat", target, capture=True)
            if proc.returncode != 0 or not proc.stdout.strip():
                die(f"could not read {target} back from sandbox {sbx_id}")
            try:
                parsed = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                die(f"{target} is not valid JSON: {exc}")
            if name == "verdict":
                verdict = parsed
            else:
                good_verdict = parsed
    finally:
        if args.keep:
            print(f"run.py: --keep: sandbox {sbx_id} left running; "
                  f"kill it with: sbx kill {sbx_id}")
        else:
            run("kill", "sbx", "kill", sbx_id, timeout=120)
            proc, _ = run("list", "sbx", "list", timeout=60, capture=True)
            if proc.returncode != 0:
                die(f"cleanup unconfirmed for sandbox {sbx_id}: `sbx list` "
                    f"failed (exit {proc.returncode}); run: sbx kill {sbx_id}")
            if sbx_id in (proc.stdout or ""):
                die(f"cleanup not confirmed: sandbox {sbx_id} is still live; "
                    f"kill it with: sbx kill {sbx_id}")
            print(f"cleanup: sandbox {sbx_id} killed and confirmed gone")

    print(f"total: {time.monotonic() - total0:.0f} s")

    if verdict is None:
        die("no verdict JSON returned from the sandbox")
    if good_verdict is None:
        die("no verdict for the committed example returned from the sandbox")

    for label, v in (("bench record (fresh)", verdict),
                     ("committed example", good_verdict)):
        gates = v.get("gates", {})
        ok = v.get("verdict") == "pass" and all(
            g.get("pass") for g in gates.values())
        print(f"\nskill-ab-bench {label}: {'PASS' if ok else 'FAIL'}"
              f"  (seed {v.get('seed')})")
        for name, g in sorted(gates.items()):
            extra = ""
            if name == "G5_power":
                extra = (f"  p = {g.get('fisher_p'):.3g}"
                         f"  ({g.get('skill_passes')}/{g.get('n')} vs "
                         f"{g.get('noskill_passes')}/{g.get('n')})")
            elif name == "G6_effect_size":
                ci = g.get("ci", {})
                extra = (f"  delta = {g.get('delta_pts'):+.1f} pts"
                         f"  CI [{ci.get('lo'):.3f}, {ci.get('hi'):.3f}]")
            elif name == "G7_placebo_control":
                ci = g.get("ci", {})
                extra = (f"  delta = {g.get('delta_pts'):+.1f} pts"
                         f"  CI [{ci.get('lo'):.3f}, {ci.get('hi'):.3f}]")
            elif g.get("problems"):
                extra = f"  {g['problems'][0]}"
            print(f"  {name}: {'pass' if g.get('pass') else 'FAIL'}{extra}")
        if not ok:
            print(f"  failed gate: {v.get('failed_gate')}")

    ok = (verdict.get("verdict") == "pass" and good_verdict.get("verdict") == "pass")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
