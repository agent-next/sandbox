#!/usr/bin/env python3
"""One-command run for the viral-microgen cookbook demo (DEMO-STANDARD.md).

Creates a disposable agent-next sandbox, clones this repo into it, installs
the pinned judge tools, runs the judge self-test, grades the known-good
artifact, prints the verdict and a short summary, then always kills the
sandbox and confirms it is gone.  Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

Usage: python3 run.py [--ref main] [--seed 42] [--keep]

Exits 0 only if setup, the self-test and the grade all succeed.  Every step
that fails is reported with its exit code and its output tail; nothing is
reported as "ok" unless it exited 0.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO = "cookbook/viral-microgen"
ARTIFACT = "examples/good"
CLONE_DIR = "viral-demo-repo"
VENV = "$HOME/.viral-microgen-venv"


class Failure(RuntimeError):
    pass


# A dropped command stream is a transport error, not the command's exit: the
# sandbox may still be running the step.  These are the CLI's transport
# failures; anything else is a real exit code and is reported as such.
TRANSPORT_MARKERS = (
    "ConnectError", "ReadError", "RemoteProtocolError", "ConnectTimeout",
    "ReadTimeout", "PoolTimeout", "NetworkError", "Temporary failure",
    "Error reading content", "Connection reset", "Connection aborted",
)
RETRIES = 3
RETRY_SLEEP_S = 15.0


def sbx(*args: str, timeout: float = 120.0) -> subprocess.CompletedProcess:
    """Run one sbx CLI command; never raises, the caller checks exit code."""
    return subprocess.run(["sbx", *args], capture_output=True, text=True,
                          timeout=timeout)


def is_transport_error(proc: subprocess.CompletedProcess) -> bool:
    text = (proc.stdout or "") + (proc.stderr or "")
    return any(m in text for m in TRANSPORT_MARKERS)


def step(name: str, fn) -> subprocess.CompletedProcess:
    """Run a step, retrying the whole command when the stream drops.

    A transport error is not a process exit: the step is re-run from the
    start, and the retry is only accepted when it returns a real exit code.
    """
    start = time.monotonic()
    for attempt in range(1, RETRIES + 1):
        proc = fn()
        if proc.returncode == 0 or not is_transport_error(proc):
            break
        if attempt == RETRIES:
            break
        print(f"run: {name}: command stream dropped (attempt {attempt}); "
              f"reattaching in {RETRY_SLEEP_S:.0f}s", flush=True)
        time.sleep(RETRY_SLEEP_S)
    dt = time.monotonic() - start
    print(f"run: [{dt:6.1f}s] {name} -> exit {proc.returncode}", flush=True)
    if proc.returncode != 0:
        tail = (proc.stdout or "") + (proc.stderr or "")
        raise Failure(f"{name} failed (exit {proc.returncode}):\n"
                      f"{tail.strip()[-3000:]}")
    return proc


def show(proc: subprocess.CompletedProcess) -> None:
    """Echo a step's stdout so the user sees the judge's own lines (each
    'killed <mutant> (gate: ...)', the kill rate, the verdict)."""
    if proc.stdout:
        print(proc.stdout.rstrip(), flush=True)


def parse_verdict(stdout: str) -> dict:
    """Pull the verdict JSON out of a grade.sh run's stdout."""
    start = stdout.find("{")
    if start < 0:
        raise Failure("grade.sh printed no JSON verdict:\n"
                      + stdout.strip()[-1000:])
    try:
        return json.loads(stdout[start:])
    except json.JSONDecodeError as exc:
        raise Failure(f"could not parse the verdict JSON: {exc}\n"
                      + stdout[start:start + 1000]) from exc


def summary_lines(verdict: dict) -> list[str]:
    """The short human summary printed after the verdict."""
    gates = verdict.get("gates", {})
    lines = [f"run: SUMMARY passed={verdict.get('passed')} "
             f"seed={verdict.get('seed')} "
             f"qr_expected={verdict.get('qr_expected')}"]
    for name in ("wav_format", "shepard_property", "gif_animation",
                 "ball_bounces", "qr_scans", "palette_match"):
        g = gates.get(name)
        if g is None:
            lines.append(f"run:   {name:18s} (not run)")
            continue
        lines.append(f"run:   {name:18s} "
                     f"{'PASS' if g.get('passed') else 'FAIL'}  "
                     f"{g.get('reason', '')}")
    sp = gates.get("shepard_property", {})
    if sp.get("passed"):
        lines.append("run:   shepard: "
                     f"span={sp.get('span_octaves')} oct, "
                     f"slope={sp.get('slope_oct_per_s')} oct/s, "
                     f"R^2={sp.get('fit_r2')}, "
                     f"return={sp.get('return_octaves')} oct, "
                     f"mid/tail={sp.get('mid_tail_db')} dB")
    bb = gates.get("ball_bounces", {})
    if bb.get("passed"):
        lines.append("run:   ball: "
                     f"{bb.get('n_bounces')} bounces, "
                     f"rise={bb.get('max_rise_px')} px, "
                     f"travel={bb.get('x_travel_px')} px, "
                     f"floor row={bb.get('floor_row')}")
    ga = gates.get("gif_animation", {})
    if ga.get("passed"):
        lines.append("run:   gif: "
                     f"{ga.get('n_frames')} frames, "
                     f"{ga.get('distinct_colours')} colours, "
                     f"loop={ga.get('loop')}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main",
                    help="repo ref to clone (default main)")
    ap.add_argument("--seed", type=int, default=42,
                    help="grading seed; sets the planted QR string")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox up and print its id")
    args = ap.parse_args()

    if sbx("--version").returncode != 0:
        print("run: the sbx CLI is required: pip install "
              '"git+https://github.com/agent-next/sandbox#subdirectory=cli"',
              file=sys.stderr)
        return 1

    sid = None
    fail = False
    try:
        created = step("sbx create --timeout-min 30",
                       lambda: sbx("create", "--timeout-min", "30"))
        sid = created.stdout.strip().splitlines()[-1].strip()
        print(f"run: sandbox {sid}", flush=True)

        step("git clone",
             lambda: sbx("exec", sid, "--timeout", "300", "--",
                         "git", "clone", "--depth", "1", "-b", args.ref,
                         REPO, CLONE_DIR))

        def in_sandbox(name: str, cmd: str, timeout: float,
                       echo: bool = False) -> subprocess.CompletedProcess:
            # the local subprocess must outlive the sandbox-side timeout, or
            # the CLI call is killed before the sandbox answers
            proc = step(name, lambda: sbx(
                "exec", sid, "--timeout", str(timeout), "--",
                f"cd {CLONE_DIR}/{DEMO} && {cmd}", timeout=timeout + 180))
            if echo:
                show(proc)
            return proc

        in_sandbox("judge/setup.sh", "bash judge/setup.sh", 1800)
        in_sandbox("judge/selftest.sh", "bash judge/selftest.sh", 1800,
                   echo=True)
        graded = in_sandbox(
            f"judge/grade.sh {ARTIFACT}",
            f"bash judge/grade.sh {ARTIFACT} --seed {args.seed} "
            f"--json /tmp/verdict.json", 900, echo=True)

        verdict = parse_verdict(graded.stdout)
        for line in summary_lines(verdict):
            print(line, flush=True)
        if not verdict.get("passed"):
            raise Failure(
                f"judge did not pass: failed gate(s) "
                f"{verdict.get('failed_gates') or verdict.get('failed_gate')}"
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
                try:
                    killed = sbx("kill", sid, timeout=180)
                    if killed.returncode != 0:
                        print(f"run: WARNING kill exit {killed.returncode}: "
                              f"{(killed.stderr or '').strip()}",
                              file=sys.stderr)
                    listing = sbx("list", timeout=120)
                except subprocess.TimeoutExpired:
                    print(f"run: FAILED cleanup: sbx kill/list timed out; "
                          f"run sbx kill {sid}", file=sys.stderr)
                    sys.exit(1)
                if sid in (listing.stdout or ""):
                    print(f"run: FAILED cleanup: sandbox {sid} is still "
                          "live; run sbx kill for this id", file=sys.stderr)
                    sys.exit(1)
                print(f"run: killed and confirmed gone: {sid}", flush=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
