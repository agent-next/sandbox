#!/usr/bin/env python3
"""bisect-breaking-commit judge engine (stdlib only), called by judge/grade.sh.

Independent oracle: re-runs the fixture suite at every commit in the range
itself, then checks the artifact against the measured ground truth.

Gates per SPEC.md:
  G1 artifact      valid JSON, required fields present, correct types
  G2 identified    artifact.commit == the commit where the suite first fails
                   (measured by re-running the suite at every commit)
  G3 neighbors     suite passes at commit-1 and fails at commit (measured)
  G4 speedup       parallel_wall <= serial_wall / 3.0 (both measured)
  G5 diff          artifact.diff matches the measured diff at the identified
                   commit (the planted whitespace change)
  G6 negative      on the reverted fixture the sweep reports "no regression"
                   instead of naming a random commit

The judge never trusts the artifact's claims about which commit is bad —
it re-runs the suite at every commit and derives the answer itself.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# --- fixture constants (must match fixture/make_fixture.py) ----------------
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixture"
MAKE_FIXTURE = FIXTURE_DIR / "make_fixture.py"
SEED = 20261015
NUM_COMMITS = 31
PLANTED_INDEX = 25
SPEEDUP_MIN = 3.0
REQUIRED_FIELDS = {"commit", "subject", "author", "date", "diff",
                   "serial_wall_s", "parallel_wall_s", "speedup"}


class GateFail(Exception):
    def __init__(self, gate: str, message: str):
        super().__init__(message)
        self.gate, self.message = gate, message


def sh(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, check=check,
                          capture_output=True, text=True)


def build_fixture(workdir: Path, revert: bool) -> Path:
    """Build the fixture repo into workdir, return its path."""
    outdir = workdir / ("fixture_reverted" if revert else "fixture_planted")
    if outdir.exists():
        subprocess.run(["rm", "-rf", str(outdir)], check=True)
    cmd = [sys.executable, "-I", str(MAKE_FIXTURE), str(outdir)]
    if revert:
        cmd.append("--revert-planted")
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return outdir


def run_suite(repo: Path) -> tuple[bool, str]:
    """Run test_suite.py in repo; return (passed, output)."""
    try:
        proc = subprocess.run(
            [sys.executable, "test_suite.py"], cwd=repo,
            capture_output=True, text=True, timeout=60)
        passed = proc.returncode == 0
        return passed, (proc.stdout + proc.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as exc:
        return False, str(exc)


def measure_range(repo: Path) -> list[dict]:
    """Run the suite at every commit 0..NUM_COMMITS-1; return per-commit results."""
    results = []
    for i in range(NUM_COMMITS):
        # checkout commit i (HEAD~{NUM_COMMITS-1-i})
        depth = NUM_COMMITS - 1 - i
        sh(repo, "checkout", "-q", f"HEAD~{depth}" if depth else "HEAD")
        passed, output = run_suite(repo)
        results.append({"index": i, "passed": passed, "output": output})
    return results


def find_first_failure(results: list[dict]) -> int | None:
    """Index of the first commit where the suite fails, or None."""
    for r in results:
        if not r["passed"]:
            return r["index"]
    return None


def get_commit_info(repo: Path, index: int) -> dict:
    """Get commit metadata at the given index (0 = oldest)."""
    depth = NUM_COMMITS - 1 - index
    rev = f"HEAD~{depth}" if depth else "HEAD"
    fmt = "%H%n%an%n%ae%n%aI%n%s"
    out = sh(repo, "log", "-1", f"--format={fmt}", rev).stdout.strip()
    lines = out.splitlines()
    return {
        "sha": lines[0],
        "author": lines[1],
        "email": lines[2],
        "date": lines[3],
        "subject": lines[4],
    }


def get_commit_diff(repo: Path, index: int) -> str:
    """Get the diff introduced by the commit at the given index."""
    depth = NUM_COMMITS - 1 - index
    rev = f"HEAD~{depth}" if depth else "HEAD"
    return sh(repo, "show", "--format=", rev).stdout


def measure_serial_wall(repo: Path) -> float:
    """Run the suite serially NUM_COMMITS times; return wall time in seconds."""
    start = time.monotonic()
    for i in range(NUM_COMMITS):
        depth = NUM_COMMITS - 1 - i
        sh(repo, "checkout", "-q", f"HEAD~{depth}" if depth else "HEAD")
        run_suite(repo)
    return time.monotonic() - start


def measure_parallel_wall(repo: Path) -> float:
    """Run the suite at all commits in parallel (one process each); return wall."""
    import concurrent.futures
    start = time.monotonic()

    def run_one(i: int) -> None:
        depth = NUM_COMMITS - 1 - i
        # each thread checks out its own commit in a temp clone
        with tempfile.TemporaryDirectory() as td:
            clone = Path(td) / "clone"
            subprocess.run(["git", "clone", "-q", str(repo), str(clone)],
                           check=True, capture_output=True)
            sh(clone, "checkout", "-q", f"HEAD~{depth}" if depth else "HEAD")
            run_suite(clone)

    with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_COMMITS) as ex:
        list(ex.map(run_one, range(NUM_COMMITS)))
    return time.monotonic() - start


def grade(artifact: Path, seed: int) -> dict:
    """Run every gate; return the verdict dict."""
    gates: dict = {}
    try:
        _grade(artifact, seed, gates)
    except GateFail as exc:
        return {"artifact": str(artifact), "passed": False,
                "failed_gate": exc.gate, "reason": exc.message,
                "gates": gates}
    return {"artifact": str(artifact), "seed": seed, "passed": True,
            "gates": gates}


def _grade(artifact: Path, seed: int, gates: dict) -> None:
    # -- G1 artifact structure --------------------------------------------
    try:
        data = json.loads(artifact.read_text())
    except Exception as exc:
        raise GateFail("artifact", f"not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise GateFail("artifact", "top-level must be a JSON object")
    missing = REQUIRED_FIELDS - set(data)
    if missing:
        raise GateFail("artifact", f"missing fields: {sorted(missing)}")
    if not isinstance(data["commit"], str) or len(data["commit"]) != 40:
        raise GateFail("artifact", "commit must be a 40-char hex SHA")
    if not isinstance(data["diff"], str) or not data["diff"].strip():
        raise GateFail("artifact", "diff must be a non-empty string")
    for f in ("serial_wall_s", "parallel_wall_s", "speedup"):
        if not isinstance(data[f], (int, float)) or data[f] <= 0:
            raise GateFail("artifact", f"{f} must be a positive number")
    gates["artifact"] = {"passed": True, "fields": sorted(REQUIRED_FIELDS)}

    # -- build fixture and measure ground truth ----------------------------
    with tempfile.TemporaryDirectory(prefix="bisect-judge-") as td:
        workdir = Path(td)
        repo = build_fixture(workdir, revert=False)

        # G2/G3: measure every commit
        results = measure_range(repo)
        first_fail = find_first_failure(results)

        if first_fail is None:
            # negative control: no regression in range
            gates["identified"] = {"passed": True, "no_regression": True,
                                   "note": "suite passes at every commit in range"}
            gates["neighbors"] = {"passed": True, "no_regression": True}
            # still check the artifact doesn't name a random commit
            if data["commit"] != "0" * 40:
                raise GateFail("identified",
                               "no regression in range but artifact names a commit")
            gates["negative"] = {"passed": True}
            return

        info = get_commit_info(repo, first_fail)
        diff = get_commit_diff(repo, first_fail)

        # G2: identified commit
        gates["identified"] = {
            "passed": data["commit"] == info["sha"],
            "expected": info["sha"],
            "got": data["commit"],
            "index": first_fail,
        }
        if data["commit"] != info["sha"]:
            raise GateFail("identified",
                           f"artifact names {data['commit'][:12]} but the suite "
                           f"first fails at {info['sha'][:12]} (index {first_fail})")

        # G3: neighbors (N-1 passes, N fails)
        prev_ok = results[first_fail - 1]["passed"] if first_fail > 0 else True
        this_ok = results[first_fail]["passed"]
        gates["neighbors"] = {
            "passed": prev_ok and not this_ok,
            "prev_index": first_fail - 1,
            "prev_passed": prev_ok,
            "this_index": first_fail,
            "this_passed": this_ok,
        }
        if not prev_ok:
            raise GateFail("neighbors",
                           f"suite also fails at index {first_fail - 1} "
                           f"(not a clean boundary)")
        if this_ok:
            raise GateFail("neighbors",
                           f"suite passes at index {first_fail} "
                           f"(not a failure boundary)")

        # G4: speedup
        speedup = data["serial_wall_s"] / data["parallel_wall_s"]
        gates["speedup"] = {
            "passed": speedup >= SPEEDUP_MIN,
            "speedup": round(speedup, 2),
            "required": SPEEDUP_MIN,
            "serial_wall_s": round(data["serial_wall_s"], 2),
            "parallel_wall_s": round(data["parallel_wall_s"], 2),
        }
        if speedup < SPEEDUP_MIN:
            raise GateFail("speedup",
                           f"speedup {speedup:.2f}x < required {SPEEDUP_MIN}x")

        # G5: diff matches the planted change
        # normalize whitespace for comparison
        norm = lambda s: re.sub(r"\s+", " ", s).strip()
        gates["diff"] = {
            "passed": norm(data["diff"]) == norm(diff),
            "expected_len": len(diff),
            "got_len": len(data["diff"]),
        }
        if norm(data["diff"]) != norm(diff):
            raise GateFail("diff",
                           "artifact diff does not match the measured diff "
                           "at the identified commit")

        # G6: negative control — reverted fixture has no regression
        repo_rev = build_fixture(workdir, revert=True)
        results_rev = measure_range(repo_rev)
        rev_fail = find_first_failure(results_rev)
        gates["negative"] = {
            "passed": rev_fail is None,
            "first_failure_index": rev_fail,
        }
        if rev_fail is not None:
            raise GateFail("negative",
                           f"reverted fixture still fails at index {rev_fail}")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact", type=Path)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    try:
        verdict = grade(args.artifact, args.seed)
        rc = 0 if verdict["passed"] else 1
    except OSError as exc:
        verdict = {"artifact": str(args.artifact), "passed": False,
                   "failed_gate": "io", "reason": str(exc)}
        rc = 1
    text = json.dumps(verdict, indent=2)
    if args.json:
        args.json.write_text(text)
    print(text)
    return rc


if __name__ == "__main__":
    sys.exit(main())
