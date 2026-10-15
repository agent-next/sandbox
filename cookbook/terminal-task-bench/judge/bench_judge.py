#!/usr/bin/env python3
"""terminal-task-bench judge engine.

Grades one agent directory against the ten task fixtures:

    bench_judge.py <agent-dir> [--seed N] [--json out.json]
                              [--tasks ID,ID,...]

For each task the judge

  1. regenerates the fixture tree from the seed into a temp dir,
  2. runs the agent's solutions/<task>/apply.sh against a *copy* of the
     broken work/ tree, with cwd = the copy's parent and a minimal
     environment (only PATH, LANG, HOME, TMPDIR and WORK -- nothing that
     names the judge, the seed or the seeded tree),
  3. runs the seeded fixtures/<task>/verify.sh against the repaired copy,
  4. records pass/fail, wall time and the verifier's own output.

Gate G5 checksums judge/, the committed fixtures/ tree and the seeded
fixture tree before and after the agent runs -- and, stronger, each
task's oracle (verify.sh + expected.json) is fingerprinted before the
agent runs, copied to a private staging dir only after the agent's whole
process group is dead, byte-compared against the fingerprint, and only
then executed.  A verifier that was rewritten, moved or replaced while
the agent ran fails the run however convincing its exit status is.

Tasks are graded one at a time on purpose: the oracle is fingerprinted
around each apply.sh, and apply.sh is killed as a process group so no
surviving child can touch the oracle between the snapshot and the check.

It then applies the gates from SPEC.md and prints one JSON verdict.  Exit 0
only if every gate passes.

The judge never runs the agent against the committed fixture tree, never
lets the agent write inside the judge, and never trusts a repair's exit
status: only verify.sh's exit status decides a task.

Standard library only.  Run with -I.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
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

# apply.sh runs with only these variables -- nothing that names the judge,
# the seeded tree or the seed is passed to the agent under test.
AGENT_ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "HOME", "TMPDIR")


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


def run_pgroup(cmd, cwd, timeout, env=None):
    """Run a command in its own session and reap everything it left.

    apply.sh (the only thing this is used for) gets its own session, so
    after it exits the judge can wait for -- and kill -- every process in
    that session, daemonized grandchildren included.  Nothing the agent
    started is allowed to still be running when the oracle is checked.
    Returns (rc, output, seconds); never raises.
    """
    start = time.monotonic()
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                env=env, start_new_session=True)
    except OSError as exc:
        return 125, f"could not run {cmd[0]!r}: {exc}", 0.0
    try:
        out, _ = proc.communicate(timeout=timeout)
        rc, out = proc.returncode, out or ""
    except subprocess.TimeoutExpired:
        _kill_session(proc.pid)
        try:
            out, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            out = ""
        rc, out = 124, (out or "") + f"\ntimed out after {timeout:.0f}s"
    reap_session(proc.pid)
    return rc, out, time.monotonic() - start


def session_members(sid: int) -> list:
    """PIDs still running in session `sid` (Linux /proc; [] elsewhere)."""
    members = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return members
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", "rb") as fh:
                stat = fh.read()
            # pid (comm) state ppid pgrp session ... -- comm may hold spaces
            rest = stat[stat.rindex(b")") + 2:].split()
            if int(rest[3]) == sid:
                members.append(int(entry))
        except (OSError, ValueError, IndexError):
            continue
    return members


def _kill_session(sid: int) -> None:
    for pid in session_members(sid):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def reap_session(sid: int, timeout: float = 10.0) -> None:
    """Wait for every process in session `sid` to exit; SIGKILL the rest.

    A child that called setsid(2) itself escapes its session -- that is
    the one thing a same-user judge cannot reach, and why the oracle is
    also byte-checked before it executes.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and session_members(sid):
        time.sleep(0.05)
    _kill_session(sid)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and session_members(sid):
        time.sleep(0.05)


def sha256_bytes(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def hash_or_gone(path: str) -> str:
    try:
        return sha256_bytes(path)
    except OSError:
        return "<gone>"


def stage_oracle(taskdir: str, stage: str) -> tuple:
    """Copy the oracle (verify.sh + expected.json, nothing else) out of the
    generated fixture tree into a private staging dir and fingerprint every
    staged byte.  Returns ({relpath: sha256}, {relpath: staged-path}).

    Called before apply.sh runs, so the fingerprint is of the oracle as
    the generator wrote it, before any agent could touch it.
    """
    hashes, staged = {}, {}
    os.makedirs(stage, exist_ok=True)
    for name in ("verify.sh", "expected.json"):
        dst = os.path.join(stage, name)
        shutil.copy2(os.path.join(taskdir, name), dst)
        os.chmod(dst, 0o700)
        hashes[name] = sha256_bytes(dst)
        staged[name] = dst
    return hashes, staged


def verify_with_staged_oracle(before: dict, staged: dict, work: str,
                              exec_root: str) -> tuple:
    """Verify one repaired tree against the oracle staged before apply.sh
    ran (see stage_oracle).  In order:

    1. re-fingerprint the staged bytes: identical to the pre-agent
       fingerprint, or the run fails without executing anything;
    2. copy each staged file to a private execution dir and run the
       verifier from there;
    3. re-fingerprint the executed bytes afterwards: identical again, or
       the run fails.

    So the bytes that decide the task are compared against the authentic
    oracle twice -- once before they run, once after -- and a rewrite
    anywhere in between fails the run.  Returns
    (verify_exit, verify_output, seconds, oracle_ok).
    """
    after = {name: hash_or_gone(p) for name, p in staged.items()}
    if after != before:
        return 1, ("oracle tampered while the agent ran: staged bytes "
                   "changed -- refusing to execute the verifier"), 0.0, False

    execdir = os.path.join(exec_root, "exec")
    os.makedirs(execdir, exist_ok=True)
    executed = {}
    for name, src in staged.items():
        dst = os.path.join(execdir, name)
        shutil.copy2(src, dst)
        os.chmod(dst, 0o700)
        executed[name] = dst
    rc, out, secs = run(["bash", executed["verify.sh"], work],
                        cwd=execdir, timeout=VERIFY_TIMEOUT)

    final = {name: hash_or_gone(p) for name, p in executed.items()}
    if final != before:
        return 1, ("oracle tampered during the run: executed verifier "
                   "bytes changed"), secs, False
    return rc, out, secs, True


def build_fixtures(seed: int, dest: str) -> None:
    rc, out, _ = run([sys.executable, "-I", MAKE_FIXTURES, "--seed", str(seed),
                      "--out", dest], cwd=DEMO, timeout=600)
    if rc != 0:
        raise RuntimeError(f"fixture generation failed (exit {rc}):\n{out}")


def agent_solution(agent: str, task: str) -> str:
    return os.path.join(os.path.abspath(agent), "solutions", task, "apply.sh")


def agent_env(work: str) -> dict:
    """The only environment apply.sh sees: the workdir plus five variables.

    The judge, the seeded tree and the seed itself are not named anywhere
    in this environment, and the scratch workdir is 0700 so no other local
    user can find or touch it either.
    """
    env = {k: v for k, v in os.environ.items() if k in AGENT_ENV_ALLOWLIST}
    env["WORK"] = work
    env["TMPDIR"] = os.path.dirname(work)
    return env


def reset_dir(path: str) -> None:
    """Make `path` an empty directory this run owns.  A previous task's
    apply.sh may have planted a directory, a file or a symlink there (its
    cwd is a sibling); nothing it left survives into this task's grading."""
    if os.path.islink(path) or (os.path.lexists(path)
                                and not os.path.isdir(path)):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path)


def grade_task(agent: str, fixtures: str, scratch_root: str, task: str):
    """Repair one task in its own copy of the fixture and verify it.

    The order is the security property.  The oracle for this task
    (verify.sh + expected.json) is copied out and fingerprinted BEFORE
    apply.sh runs; the agent runs alone in its own session, which is then
    reaped; the staged bytes are re-checked; and only then does the
    verifier execute, from the judge's staged copy.  See
    verify_with_staged_oracle for what that rules out.
    """
    src = os.path.join(fixtures, task)
    dst = os.path.join(scratch_root, task)
    oracle_root = os.path.join(scratch_root, ".oracle", task)
    reset_dir(dst)
    reset_dir(oracle_root)

    # the fixture's broken work/ tree is copied, never used in place
    shutil.copytree(os.path.join(src, "work"), os.path.join(dst, "work"),
                    symlinks=True)

    apply_sh = agent_solution(agent, task)
    result = {"task": task, "apply_exit": None, "verify_exit": None,
              "solved": False, "apply_seconds": 0.0, "verify_seconds": 0.0,
              "apply_output": "", "verify_output": "", "oracle_ok": True}

    # stage the authentic oracle before the agent can act at all
    try:
        before, staged = stage_oracle(src, os.path.join(oracle_root, "stage"))
    except OSError as exc:
        result["oracle_ok"] = False
        result["verify_output"] = f"oracle unreadable before apply ran: {exc}"
        return result

    if not os.path.isfile(apply_sh):
        result["apply_output"] = f"no solution at solutions/{task}/apply.sh"
        return result

    work = os.path.join(dst, "work")
    rc, out, secs = run_pgroup(["bash", apply_sh], cwd=dst,
                               timeout=APPLY_TIMEOUT, env=agent_env(work))
    result["apply_exit"] = rc
    result["apply_output"] = out[-4000:]
    result["apply_seconds"] = round(secs, 3)

    vrc, vout, vsecs, ok = verify_with_staged_oracle(before, staged, work,
                                                     oracle_root)
    result["verify_exit"] = vrc
    result["verify_output"] = vout[-4000:]
    result["verify_seconds"] = round(vsecs, 3)
    result["oracle_ok"] = ok
    result["solved"] = ok and vrc == 0
    return result


def check_pristine(fixtures: str, task: str, scratch_root: str):
    """G2: the broken tree must fail its own verifier.

    Run against a throwaway copy, for the same reason agent work is: a
    verifier may have side effects on the tree it is given (`git status`
    refreshes the index, the WAL check touches db side files), and the
    seeded fixture tree is this run's oracle -- it must stay exactly as
    the generator wrote it, or the before/after tree hashes mean nothing.
    """
    taskdir = os.path.join(fixtures, task)
    copy_root = os.path.join(scratch_root, f"pristine-{task}")
    oracle_root = os.path.join(scratch_root, ".oracle", f"pristine-{task}")
    reset_dir(copy_root)
    reset_dir(oracle_root)
    work = os.path.join(copy_root, "work")
    shutil.copytree(os.path.join(taskdir, "work"), work, symlinks=True)

    before, staged = stage_oracle(taskdir, os.path.join(oracle_root, "stage"))
    rc, out, _, _ = verify_with_staged_oracle(before, staged, work,
                                              oracle_root)
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



def grade(agent: str, seed: int, tasks, verbose: bool) -> dict:
    workdir = tempfile.mkdtemp(prefix="ttb-judge-")
    try:
        fixtures = os.path.join(workdir, "fixtures")
        build_fixtures(seed, fixtures)

        scratch = os.path.join(workdir, "scratch")
        os.makedirs(scratch, exist_ok=True)

        # --- G2: pristine trees must fail (against copies; see above) ----
        pristine = {}
        for task in tasks:
            rc, out = check_pristine(fixtures, task, scratch)
            pristine[task] = {"verify_exit": rc, "fails": rc != 0,
                              "output": out}

        # --- snapshot the oracle trees before the agent runs --------------
        # G5 checksums all three: judge/, the committed fixtures/ tree, and
        # the seeded fixture tree.  Any change to any of them during the
        # run fails the gate -- on top of the per-task staged-oracle
        # checks in grade_task, which compare the bytes that actually
        # decided each task.
        judge_before = sha256_tree(HERE)
        fixtures_before = sha256_tree(FIXTURES)
        seeded_before = sha256_tree(fixtures)

        # --- the agent under test, one task at a time --------------------
        # (serial on purpose: the oracle is fingerprinted around each
        # apply.sh, and only one agent session is alive at a time)
        results = {}
        for task in tasks:
            results[task] = grade_task(agent, fixtures, scratch, task)
            if verbose:
                r = results[task]
                print(f"judge: {task}: apply={r['apply_exit']} "
                      f"verify={r['verify_exit']} "
                      f"solved={r['solved']}"
                      + ("" if r["oracle_ok"] else "  ORACLE TAMPERED"),
                      flush=True)

        # --- G3: the negative control must score 0/10 ---------------------
        negctl_root = os.path.join(workdir, "negctl")
        reset_dir(negctl_root)
        negctl = make_negative_control(negctl_root)
        neg_scratch = os.path.join(workdir, "neg-scratch")
        os.makedirs(neg_scratch, exist_ok=True)
        neg_results = {}
        for task in tasks:
            neg_results[task] = grade_task(negctl, fixtures, neg_scratch, task)
        neg_solved = sum(1 for r in neg_results.values() if r["solved"])

        # --- snapshot the oracle trees again after everything ran ---------
        judge_after = sha256_tree(HERE)
        fixtures_after = sha256_tree(FIXTURES)
        seeded_after = sha256_tree(fixtures)

        # --- assemble the verdict ----------------------------------------
        task_rows = []
        for task in sorted(tasks):
            r = results[task]
            task_rows.append({
                "task": task,
                "solved": r["solved"],
                "apply_exit": r["apply_exit"],
                "verify_exit": r["verify_exit"],
                "oracle_intact": r["oracle_ok"],
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
        tampered = sorted(t for t in tasks if not results[t]["oracle_ok"])
        g5 = (judge_before == judge_after
              and fixtures_before == fixtures_after
              and seeded_before == seeded_after
              and not tampered)

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
                "passed": g5,
                "judge_sha256_before": judge_before[:16],
                "judge_sha256_after": judge_after[:16],
                "fixtures_sha256_before": fixtures_before[:16],
                "fixtures_sha256_after": fixtures_after[:16],
                "seeded_sha256_before": seeded_before[:16],
                "seeded_sha256_after": seeded_after[:16],
                # every task's oracle was staged before apply.sh ran and
                # byte-verified before the verifier executed (and again
                # after); tasks where that failed:
                "oracle_bytes_verified": len(tasks) - len(tampered),
                "tampered_tasks": tampered,
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
        verdict = grade(args.agent, args.seed, tasks, verbose=not args.quiet)
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
