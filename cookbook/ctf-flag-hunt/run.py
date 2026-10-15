#!/usr/bin/env python3
"""One-command run for the ctf-flag-hunt cookbook demo (DEMO-STANDARD.md).

Creates a disposable agent-next sandbox, clones this repo into it, installs
the pinned tools, runs the judge self-test, grades the known-good range,
prints the verdict, then always kills the sandbox and confirms it is gone.
Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

Long steps (setup, selftest, grade) run detached inside the sandbox with
their output appended to a log file; this driver polls with short execs.
The exec stream would otherwise have to stay open for the whole step and a
gateway restart anywhere in it loses the run (see LESSONS.md).

Usage: python3 run.py [--ref main] [--keep]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO = "cookbook/ctf-flag-hunt"
ARTIFACT = "examples/good"
CLONE_DIR = "ctf-demo-repo"

# The longest step from outside the sandbox.  Detached runs poll instead,
# so this only bounds one lost poll or one stuck kill/list.
SBX_TIMEOUT = 180.0
POLL_INTERVAL = 15.0
STEP_DEADLINE = 900.0


class Failure(RuntimeError):
    pass


def sbx(*args: str, timeout: float = SBX_TIMEOUT) -> subprocess.CompletedProcess:
    """Run one sbx CLI command; never raises, caller checks exit code."""
    return subprocess.run(["sbx", *args], capture_output=True, text=True,
                          timeout=timeout)


def sh(sid: str, cmd: str) -> subprocess.CompletedProcess:
    return sbx("exec", sid, "--timeout", "60", "--", cmd)


def step(name: str, fn) -> subprocess.CompletedProcess:
    start = time.monotonic()
    proc = fn()
    dt = time.monotonic() - start
    print(f"run: [{dt:6.1f}s] {name} -> exit {proc.returncode}", flush=True)
    if proc.returncode != 0:
        tail = (proc.stdout or "") + (proc.stderr or "")
        raise Failure(f"{name} failed (exit {proc.returncode}):\n"
                      f"{tail.strip()[-2000:]}")
    return proc


def short_step(sid: str, name: str, cmd: str) -> subprocess.CompletedProcess:
    """A step that must finish inside one exec stream (one short command)."""
    return step(name, lambda: sh(sid, cmd))


def detached(sid: str, name: str, cmd: str, log: str) -> None:
    """Start `cmd` detached in the sandbox; its output goes to $log.

    `setsid` keeps it alive if the exec's shell is torn down; the log is
    the only record, so the run fails loudly if the step never completes.
    """
    short_step(sid, f"start {name} (detached, log {log})",
               f"cd {CLONE_DIR}/{DEMO} && setsid nohup bash -c "
               f"'{cmd}; echo __RC__$? >> {log}' >> {log} 2>&1 < /dev/null &")


def wait_step(sid: str, name: str, log: str,
              deadline: float = STEP_DEADLINE) -> None:
    """Poll the detached step's log until it prints __RC__<n> or time runs out."""
    start = time.monotonic()
    last = ""
    while time.monotonic() - start < deadline:
        time.sleep(POLL_INTERVAL)
        proc = sh(sid, f"cat {log} 2>/dev/null")
        if proc.returncode != 0:
            raise Failure(f"{name}: could not read {log} in the sandbox")
        text = proc.stdout
        if "__RC__" in text:
            rc_line = text.rstrip().rsplit("__RC__", 1)[1].strip().split()[0]
            try:
                rc = int(rc_line)
            except ValueError:
                raise Failure(f"{name}: unparsable exit marker in {log}: "
                              f"{rc_line!r}")
            print(f"run: [{time.monotonic() - start:6.1f}s] {name} -> exit {rc}",
                  flush=True)
            if rc != 0:
                raise Failure(f"{name} failed (exit {rc}):\n"
                              f"{text.strip()[-2000:]}")
            return
        if text != last:
            # progress of a long step: show its newest line as it arrives
            tail = [l for l in text.rstrip().splitlines() if l.strip()]
            if tail:
                print(f"run:   {name}: {tail[-1]}", flush=True)
            last = text
    raise Failure(f"{name}: no exit marker in {log} after "
                  f"{deadline:.0f}s; the step may still be running in the "
                  f"sandbox (sbx kill {sid} when done)")


def show(sid: str, log: str) -> None:
    """Echo a finished step's log so the user sees the judge's own lines."""
    proc = sh(sid, f"cat {log}")
    if proc.stdout:
        print(proc.stdout.rstrip(), flush=True)


def fetch(sid: str, remote: str, local: str) -> None:
    """Read a small file back from the sandbox (the verdict JSON)."""
    proc = sh(sid, f"cat {remote}")
    if proc.returncode != 0 or not proc.stdout:
        raise Failure(f"could not read {remote} from the sandbox: "
                      f"{(proc.stderr or '').strip()[-300:]}")
    with open(local, "w") as f:
        f.write(proc.stdout)


def kill_and_confirm(sid: str) -> None:
    """Kill the sandbox and verify with sbx list that the id is gone."""
    try:
        killed = sbx("kill", sid)
        if killed.returncode != 0:
            print(f"run: WARNING kill exit {killed.returncode}: "
                  f"{(killed.stderr or '').strip()[-300:]}", file=sys.stderr)
        listing = sbx("list")
    except subprocess.TimeoutExpired:
        print(f"run: FAILED cleanup: sbx kill/list timed out; "
              f"run sbx kill {sid}", file=sys.stderr)
        sys.exit(1)
    if sid in (listing.stdout or ""):
        print(f"run: FAILED cleanup: sandbox {sid} still live; "
              "run sbx kill for this id", file=sys.stderr)
        sys.exit(1)
    print(f"run: killed and confirmed gone: {sid}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main",
                    help="repo ref to clone (default main)")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox up and print its id")
    args = ap.parse_args()

    if sbx("--version").returncode != 0:
        print("run: the sbx CLI is required: pip install "
              '"git+https://github.com/agent-next/sandbox#subdirectory=cli"',
              file=sys.stderr)
        return 1
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        print("run: export SBX_API_KEY (or E2B_API_KEY) first",
              file=sys.stderr)
        return 1

    sid = None
    fail = False
    verdict_path = os.path.abspath("ctf-flag-hunt-verdict.json")
    try:
        created = step("sbx create --timeout-min 30",
                       lambda: sbx("create", "--timeout-min", "30"))
        sid = created.stdout.strip().splitlines()[-1].strip()
        print(f"run: sandbox {sid}", flush=True)

        short_step(sid, "git clone",
                   f"git clone --depth 1 -b {args.ref} {REPO} {CLONE_DIR}")

        detached(sid, "judge/setup.sh", "bash judge/setup.sh", "setup.log")
        wait_step(sid, "judge/setup.sh", "setup.log")

        detached(sid, "judge/selftest.sh", "bash judge/selftest.sh",
                 "selftest.log")
        wait_step(sid, "judge/selftest.sh", "selftest.log")
        show(sid, "selftest.log")

        detached(sid, f"judge/grade.sh {ARTIFACT}",
                 f"bash judge/grade.sh {ARTIFACT} --json /tmp/verdict.json",
                 "grade.log")
        wait_step(sid, f"judge/grade.sh {ARTIFACT}", "grade.log")
        fetch(sid, "/tmp/verdict.json", verdict_path)
        with open(verdict_path) as f:
            verdict_text = f.read()
        show(sid, "grade.log")
        try:
            verdict = json.loads(verdict_text[verdict_text.index("{"):])
        except (ValueError, json.JSONDecodeError) as exc:
            raise Failure(f"could not parse the verdict JSON: {exc}\n"
                          f"{verdict_text[-1000:]}") from exc
        gates = verdict.get("gates", {})
        flags = gates.get("flags", {})
        oracle = gates.get("oracle", {})
        neg = gates.get("negative_control", {})
        blast = gates.get("blast_radius", {})
        print("run: SUMMARY "
              f"passed={verdict.get('passed')} "
              f"flags={flags.get('captured')}/{flags.get('required')} "
              f"oracle={oracle.get('passed')}/{oracle.get('required')} "
              f"neg_control={neg.get('captured')}/{neg.get('required')} "
              f"blast_radius={'clean' if blast.get('passed') else 'DIRTY'}",
              flush=True)
        if not verdict.get("passed"):
            raise Failure(f"judge did not pass: {verdict.get('failed_gate')}"
                          f" -- {verdict.get('reason')}")
    except Failure as exc:
        print(f"run: FAILED: {exc}", file=sys.stderr)
        fail = True
    except subprocess.TimeoutExpired as exc:
        print(f"run: FAILED: sbx command timed out: {exc}", file=sys.stderr)
        fail = True
    finally:
        if sid is not None:
            if args.keep:
                print(f"run: --keep: sandbox {sid} left running "
                     "(remember: sbx kill when done)", flush=True)
            else:
                kill_and_confirm(sid)
        try:
            os.remove(verdict_path)
        except OSError:
            pass
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
