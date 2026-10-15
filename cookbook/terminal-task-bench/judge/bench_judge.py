#!/usr/bin/env python3
"""terminal-task-bench judge engine.

Grades one agent directory against the ten task fixtures:

    bench_judge.py <agent-dir> [--seed N] [--json out.json]
                              [--tasks ID,ID,...] [--jobs N]

For each task the judge

  1. regenerates the fixture tree from the seed into a temp dir,
  2. runs the agent's solutions/<task>/apply.sh against a *copy* of the
     broken work/ tree, with cwd = the copy's parent,
  3. runs fixtures/<task>/verify.sh against the repaired copy,
  4. records pass/fail, wall time and the verifier's own output.

It then applies the gates from SPEC.md and prints one JSON verdict.  Exit 0
only if every gate passes.

The judge never runs the agent against the committed fixture tree, never
lets the agent write inside the judge, and never trusts a repair's exit
status: only verify.sh's exit status decides a task.

Standard library only.  Run with -I.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
FIXTURES = os.path.join(DEMO, "fixtures")
MAKE_FIXTURES = os.path.join(FIXTURES, "make_fixtures.py")

DEFAULT_SEED = 20261015
APPLY_TIMEOUT = 60.0
VERIFY_TIMEOUT = 60.0

TASKS = [
    "wal-repair",
    "git-lost-branch",
    "systemd-unit",
    "perms-maze",
    "csv-normalize",
    "json-config",
    "symlink-maze",
    "tar-restore",
    "bugfix-python",
    "cron-repair",
]

# Gate thresholds (SPEC.md)
SOLVE_FRACTION = 0.8        # G1: >= 80 % of the graded tasks (8 of 10)
MAX_TOTAL_VERIFY_SECONDS = 300.0


def sha256_tree(root: str) -> str:
    """Cheap integrity fingerprint of a directory tree."""
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            if name.endswith(".pyc"):
                continue
            p = os.path.join(dirpath, name)
            h.update(os.path.relpath(p, root).encode())
            try:
                with open(p, "rb") as fh:
                    h.update(fh.read())
            except OSError:
                h.update(b"<unreadable>")
    return h.hexdigest()


def run(cmd, cwd, timeout, env=None):
    """Run a command, never raising on failure; returns (rc, out, secs)."""
    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, env=env)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or ""), \
            time.monotonic() - start
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout:.0f}s", time.monotonic() - start
    except OSError as exc:
        return 125, f"could not run {cmd[0]!r}: {exc}", time.monotonic() - start


def build_fixtures(seed: int, dest: str) -> None:
    rc, out, _ = run([sys.executable, "-I", MAKE_FIXTURES, "--seed", str(seed),
                      "--out", dest], cwd=DEMO, timeout=600)
    if rc != 0:
        raise RuntimeError(f"fixture generation failed (exit {rc}):\n{out}")


def agent_solution(agent: str, task: str) -> str:
    return os.path.join(os.path.abspath(agent), "solutions", task, "apply.sh")


def grade_task(agent: str, fixtures: str, scratch_root: str, task: str):
    """Repair one task in its own copy of the fixture and verify it."""
    src = os.path.join(fixtures, task)
    dst = os.path.join(scratch_root, task)
    os.makedirs(dst, exist_ok=True)

    # the fixture's broken work/ tree is copied, never used in place
    shutil.copytree(os.path.join(src, "work"), os.path.join(dst, "work"),
                    symlinks=True)
    # The verifier and its expected.json live in the *generated* fixture
    # tree, which is where this run's oracle was written.  The committed
    # fixtures/ tree carries only task.md, verify.sh and the generator.
    verify = os.path.join(src, "verify.sh")

    apply_sh = agent_solution(agent, task)
    result = {"task": task, "apply_exit": None, "verify_exit": None,
              "solved": False, "apply_seconds": 0.0, "verify_seconds": 0.0,
              "apply_output": "", "verify_output": ""}

    if not os.path.isfile(apply_sh):
        result["apply_output"] = f"no solution at solutions/{task}/apply.sh"
        return result

    work = os.path.join(dst, "work")
    env = dict(os.environ)
    env["WORK"] = work
    env["PATH"] = env.get("PATH", "") + ":" + os.path.join(DEMO, "bin")

    rc, out, secs = run(["bash", apply_sh], cwd=dst, timeout=APPLY_TIMEOUT,
                        env=env)
    result["apply_exit"] = rc
    result["apply_output"] = out[-4000:]
    result["apply_seconds"] = round(secs, 3)

    vrc, vout, vsecs = run(["bash", verify, work], cwd=src,
                           timeout=VERIFY_TIMEOUT)
    result["verify_exit"] = vrc
    result["verify_output"] = vout[-4000:]
    result["verify_seconds"] = round(vsecs, 3)
    result["solved"] = vrc == 0
    return result


def check_pristine(fixtures: str, task: str):
    """G2: the broken tree must fail its own verifier."""
    taskdir = os.path.join(fixtures, task)
    verify = os.path.join(taskdir, "verify.sh")
    work = os.path.join(taskdir, "work")
    rc, out, _ = run(["bash", verify, work], cwd=taskdir,
                     timeout=VERIFY_TIMEOUT)
    return rc, out[-2000:]


def make_negative_control(dest: str) -> str:
    """G3: an agent that does nothing at all."""
    for task in TASKS:
        d = os.path.join(dest, "solutions", task)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "apply.sh"), "w") as fh:
            fh.write("#!/usr/bin/env bash\n"
                     "# negative control: touch nothing\n"
                     "true\n")
    return dest


def grade(agent: str, seed: int, tasks, jobs: int, verbose: bool) -> dict:
    workdir = tempfile.mkdtemp(prefix="ttb-judge-")
    try:
        fixtures = os.path.join(workdir, "fixtures")
        build_fixtures(seed, fixtures)

        # --- G2: pristine trees must fail ---------------------------------
        pristine = {}
        for task in tasks:
            rc, out = check_pristine(fixtures, task)
            pristine[task] = {"verify_exit": rc, "fails": rc != 0,
                              "output": out}

        # --- the agent under test ----------------------------------------
        scratch = os.path.join(workdir, "scratch")
        os.makedirs(scratch, exist_ok=True)
        judge_before = sha256_tree(HERE)
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {pool.submit(grade_task, agent, fixtures, scratch, t): t
                       for t in tasks}
            for fut in concurrent.futures.as_completed(futures):
                task = futures[fut]
                results[task] = fut.result()
                if verbose:
                    r = results[task]
                    print(f"judge: {task}: apply={r['apply_exit']} "
                          f"verify={r['verify_exit']} "
                          f"solved={r['solved']}", flush=True)
        judge_after = sha256_tree(HERE)

        # --- G3: the negative control must score 0/10 ---------------------
        negctl = make_negative_control(os.path.join(workdir, "negctl"))
        neg_scratch = os.path.join(workdir, "neg-scratch")
        os.makedirs(neg_scratch, exist_ok=True)
        neg_results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {pool.submit(grade_task, negctl, fixtures, neg_scratch,
                                   t): t for t in tasks}
            for fut in concurrent.futures.as_completed(futures):
                task = futures[fut]
                neg_results[task] = fut.result()
        neg_solved = sum(1 for r in neg_results.values() if r["solved"])

        # --- assemble the verdict ----------------------------------------
        task_rows = []
        for task in sorted(tasks):
            r = results[task]
            task_rows.append({
                "task": task,
                "solved": r["solved"],
                "apply_exit": r["apply_exit"],
                "verify_exit": r["verify_exit"],
                "pristine_verify_exit": pristine[task]["verify_exit"],
                "negative_control_verify_exit":
                    neg_results[task]["verify_exit"],
            })

        solved = sum(1 for r in results.values() if r["solved"])
        total_verify = round(sum(r["verify_seconds"] for r in results.values()),
                             3)
        total_apply = round(sum(r["apply_seconds"] for r in results.values()),
                            3)

        # G1 scales with the number of tasks graded, so a --tasks subset run
        # is judged by the same fraction as a full run.
        required = -(-len(tasks) * 8 // 10)   # ceil(len * 0.8)

        g1 = solved >= required
        bad_pristine = sorted(t for t in tasks if pristine[t]["fails"] is False)
        g2 = not bad_pristine
        g3 = neg_solved == 0
        g4 = total_verify <= MAX_TOTAL_VERIFY_SECONDS
        g5 = judge_before == judge_after

        gates = {
            "G1_solve_count": {
                "passed": g1, "solved": solved, "total": len(tasks),
                "required": required,
            },
            "G2_pristine_fails": {
                "passed": g2, "tasks": len(tasks),
                "accepted_broken_tree": bad_pristine,
            },
            "G3_negative_control": {
                "passed": g3, "negctl_solved": neg_solved,
                "required": 0,
            },
            # Every measured wall time lives under the `timing` key, so the
            # rest of the verdict is reproducible: the gate carries only the
            # decision and the limit, and the number it was decided on is
            # timing.total_verify_seconds.
            "G4_budget": {
                "passed": g4,
                "limit_seconds": MAX_TOTAL_VERIFY_SECONDS,
                "over_budget": total_verify > MAX_TOTAL_VERIFY_SECONDS,
            },
            "G5_judge_untouched": {
                "passed": g5, "judge_sha256_before": judge_before[:16],
                "judge_sha256_after": judge_after[:16],
            },
        }

        failed = [name for name, g in gates.items() if not g["passed"]]
        verdict = {
            "agent": agent,
            "seed": seed,
            "passed": not failed,
            "failed_gate": failed[0] if failed else None,
            "gates": gates,
            "tasks": task_rows,
            "timing": {
                "total_apply_seconds": total_apply,
                "total_verify_seconds": total_verify,
            },
        }
        if failed:
            verdict["reason"] = "; ".join(
                f"{name}: {json.dumps(gates[name])}" for name in failed)

        # the full per-task verifier output is kept for the receipt / README
        verdict["_outputs"] = {
            task: {"apply": results[task]["apply_output"],
                   "verify": results[task]["verify_output"]}
            for task in sorted(tasks)
        }
        return verdict
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def strip_for_determinism(verdict: dict) -> dict:
    """The verdict without wall times and without the free-form outputs."""
    out = {k: v for k, v in verdict.items()
           if k not in ("timing", "_outputs", "agent")}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent", help="agent directory holding solutions/<task>/")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--json", help="write the verdict JSON here")
    ap.add_argument("--tasks", help="comma-separated subset of task ids")
    ap.add_argument("--jobs", type=int, default=2,
                    help="parallel tasks (default 2, the sandbox's vCPUs)")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--outputs", action="store_true",
                    help="include per-task verifier output in the JSON")
    ap.add_argument("--strip", action="store_true",
                    help="emit the determinism form (no timing/outputs)")
    args = ap.parse_args()

    if not os.path.isdir(args.agent):
        print(f"judge: no such agent directory: {args.agent}", file=sys.stderr)
        return 2

    tasks = TASKS
    if args.tasks:
        tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
        unknown = [t for t in tasks if t not in TASKS]
        if unknown:
            print(f"judge: unknown task id(s): {unknown}", file=sys.stderr)
            return 2

    try:
        verdict = grade(args.agent, args.seed, tasks, args.jobs,
                        verbose=not args.quiet)
    except RuntimeError as exc:
        print(f"judge: {exc}", file=sys.stderr)
        return 2

    if args.strip:
        verdict = strip_for_determinism(verdict)
    elif not args.outputs:
        verdict.pop("_outputs", None)

    text = json.dumps(verdict, indent=2, sort_keys=True)
    if args.json:
        with open(args.json, "w") as fh:
            fh.write(text + "\n")
    print(text)
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
