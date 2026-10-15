#!/usr/bin/env python3
"""One-command run for the code-interpreter-charts cookbook demo
(DEMO-STANDARD.md).

Creates a disposable agent-next sandbox, clones this repo into it, installs
the pinned Python stack, runs the judge self-test and grades the known-good
analysis artifact, prints the verdict, then always kills the sandbox and
confirms it is gone.  Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

Usage: python3 run.py [--ref main] [--keep]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO = "cookbook/code-interpreter-charts"
ARTIFACT = "examples/good"
CLONE_DIR = "charts-demo-repo"

# A sandbox step whose command never ran: the connect to the sandbox failed,
# not the command.  The CLI prints these as `sbx: <ExceptionType>: ...` with
# exit 1 — the same exit a real command failure gives — so run.py must tell
# them apart by error text before retrying (LESSONS.md: a transport error is
# not a process exit; reattach instead of failing).  Every step run.py sends
# is an idempotent shell line, so retrying the whole step is safe: a step
# that really ran keeps its real failure once the gateway answers.
TRANSIENT_HINTS = (
    "ConnectError",     # httpx could not reach the sandbox gateway
    "ConnectTimeout",   # connect timed out before the tunnel was up
    "tunnel error",     # the sandbox's connect tunnel refused the exec
    "connection error", # e2b SDK wording for a dropped connection
    "ReadTimeout",      # reply lost in transit
    "502", "503", "504",  # gateway blips
    "429",              # quota/rate limit: back off, then retry
)
RETRIES = 4                 # retries after the first attempt
BACKOFFS = (5, 15, 30, 60)  # seconds slept before each retry


class Failure(RuntimeError):
    pass


def sbx(*args: str, timeout: float = 120.0) -> subprocess.CompletedProcess:
    """Run one sbx CLI command; never raises, caller checks exit code."""
    return subprocess.run(["sbx", *args], capture_output=True, text=True,
                          timeout=timeout)


def transient(proc: subprocess.CompletedProcess) -> bool:
    """True when an sbx failure looks like the gateway, not the command.

    The CLI exits 1 both for "your command failed" and for "the sandbox was
    never reached"; only the latter is retried.  The hints match the
    exception type or gateway wording the CLI prints on stderr.
    """
    if proc.returncode == 0:
        return False
    tail = ((proc.stderr or "") + (proc.stdout or "")).lower()
    return any(hint.lower() in tail for hint in TRANSIENT_HINTS)


def step(name: str, fn) -> subprocess.CompletedProcess:
    """Run one step, retrying transport-level failures with backoff."""
    start = time.monotonic()
    proc = fn()
    attempt = 0
    while proc.returncode != 0 and transient(proc) and attempt < RETRIES:
        wait = BACKOFFS[min(attempt, len(BACKOFFS) - 1)]
        why = ((proc.stderr or "") + (proc.stdout or "")).strip()
        print(f"run: {name}: transport error (retry {attempt + 1}/{RETRIES} "
              f"in {wait}s): {why.splitlines()[-1][:200] if why else '?'}",
              flush=True)
        time.sleep(wait)
        attempt += 1
        proc = fn()
    dt = time.monotonic() - start
    print(f"run: [{dt:6.1f}s] {name} -> exit {proc.returncode}", flush=True)
    if proc.returncode != 0:
        tail = (proc.stdout or "") + (proc.stderr or "")
        raise Failure(f"{name} failed (exit {proc.returncode}):\n"
                      f"{tail.strip()[-2000:]}")
    return proc


def show(proc: subprocess.CompletedProcess) -> None:
    """Echo a step's stdout so the user sees the judge's own lines
    (each 'killed <mutant> (gate: ...)', the kill rate, the verdict)."""
    if proc.stdout:
        print(proc.stdout.rstrip(), flush=True)


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

    sid = None
    fail = False
    try:
        created = step("sbx create --timeout-min 30",
                       lambda: sbx("create", "--timeout-min", "30"))
        sid = created.stdout.strip().splitlines()[-1].strip()
        print(f"run: sandbox {sid}", flush=True)

        # Clone is retried on transport errors, so it must be idempotent:
        # a tunnel drop mid-clone can leave a partial tree behind.
        step("git clone",
             lambda: sbx("exec", sid, "--timeout", "300", "--",
                         "rm", "-rf", CLONE_DIR, "&&",
                         "git", "clone", "--depth", "1", "-b", args.ref,
                         REPO, CLONE_DIR))

        def in_sandbox(name: str, cmd: str, timeout: float,
                       echo: bool = False) -> subprocess.CompletedProcess:
            # Local subprocess timeout must exceed the sandbox-side --timeout
            # so the sandbox command can finish before the local process is
            # killed; add 60 s for CLI round-trip overhead.
            proc = step(name, lambda: sbx(
                "exec", sid, "--timeout", str(timeout), "--",
                f"cd {CLONE_DIR}/{DEMO} && {cmd}",
                timeout=timeout + 60))
            if echo:
                show(proc)
            return proc

        in_sandbox("judge/setup.sh", "bash judge/setup.sh", 900)
        in_sandbox("judge/selftest.sh", "bash judge/selftest.sh", 900,
                   echo=True)
        graded = in_sandbox(
            f"judge/grade.sh {ARTIFACT}",
            f"bash judge/grade.sh {ARTIFACT} --json /tmp/verdict.json", 600,
            echo=True)

        try:
            verdict = json.loads(graded.stdout[graded.stdout.index("{"):])
        except (ValueError, json.JSONDecodeError) as exc:
            raise Failure(f"could not parse the verdict JSON: {exc}\n"
                          f"{graded.stdout[-1000:]}") from exc
        gates = verdict.get("gates", {})
        answers = gates.get("G2", {})
        images = gates.get("G3", {})

        def got(section, key):
            entry = section.get(key) or {}
            return entry.get("got") if isinstance(entry, dict) else None

        print("run: SUMMARY passed={} trend={} ppm/yr amplitude={} ppm "
              "total={} Gt C2_plot_var={} artifact_run={}s".format(
                  verdict.get("passed"),
                  got(answers, "mauna_loa_trend_ppm_per_year"),
                  got(answers, "mauna_loa_seasonal_amplitude_ppm"),
                  got(answers, "owid_world_emissions_2024_gt"),
                  (images.get("C2") or {}).get("plot_area_variance"),
                  (verdict.get("timing") or {}).get("artifact_run_s")),
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
                # Kill with retries (a kill lost to a gateway blip leaves
                # the sandbox holding a quota slot), then confirm via list.
                # sbx kill is idempotent: an already-gone id is not an error.
                killed = None
                try:
                    for attempt in range(RETRIES):
                        killed = sbx("kill", sid, timeout=180)
                        if killed.returncode == 0 or not transient(killed):
                            break
                        print(f"run: kill attempt {attempt + 1} hit a "
                              f"transport error, retrying in "
                              f"{BACKOFFS[min(attempt, len(BACKOFFS) - 1)]}s",
                              file=sys.stderr, flush=True)
                        time.sleep(BACKOFFS[min(attempt, len(BACKOFFS) - 1)])
                    else:
                        killed = sbx("kill", sid, timeout=180)
                    if killed.returncode != 0:
                        print(f"run: WARNING kill exit {killed.returncode}",
                              file=sys.stderr)
                    listing = sbx("list", timeout=120)
                except subprocess.TimeoutExpired:
                    print(f"run: FAILED cleanup: sbx kill/list timed out; "
                          f"run sbx kill {sid}", file=sys.stderr)
                    sys.exit(1)
                if sid in (listing.stdout or ""):
                    print(f"run: FAILED cleanup: sandbox {sid} still live; "
                          "run sbx kill for this id", file=sys.stderr)
                    sys.exit(1)
                print(f"run: killed and confirmed gone: {sid}", flush=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
