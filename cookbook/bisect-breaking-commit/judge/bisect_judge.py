#!/usr/bin/env python3
"""bisect-breaking-commit judge engine (stdlib only), called by judge/grade.sh.

Independent oracle (SPEC.md): the judge never trusts the artifact's claims.
It rebuilds the fixture at the pinned seed (byte-identical SHAs by
construction), re-runs the suite at every commit in the sweep range in fresh
clones, and derives the culprit itself.  The same sweep code path is run on
the reverted fixture as the negative control: it must report
"no regression in range" rather than naming a random commit.

Gates (checked in order, first failure wins):
  G1 structure          valid JSON, required fields, correct types
  G2 timing_arithmetic  speedup == serial_seconds / parallel_seconds (1 %)
  G3 identified         identified_commit == planted SHA, index == PLANTED_INDEX
  G4 neighbours         suite passes at N-1, fails at N (measured); the
                        artifact's evidence booleans must match
  G5 diff               artifact.diff == git show at the planted commit
                        (whitespace-normalised both sides)
  G6 negative_control   the judge's own sweep on the reverted fixture reports
                        "no regression in range"
  G7 speedup            artifact speedup >= 3.0 AND the judge's own measured
                        serial/parallel sweep ratio >= 3.0
  G8 sandboxes          sandboxes_used == one sandbox per suspect commit (11)

Measured walls are reported only under the verdict's "timing" key, so two
grades of the same artifact are byte-identical apart from that key (the one
timing-derived verdict bit is the G7 pass flag; the fixture's settle delay
gives >= 2x margin over the 3.0 threshold on 2 vCPU).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# --- fixture constants (must match fixture/make_fixture.py) ----------------
DEMO_DIR = Path(__file__).resolve().parent.parent
MAKE_FIXTURE = DEMO_DIR / "fixture" / "make_fixture.py"
SEED = 20261015
NUM_COMMITS = 31
PLANTED_INDEX = 25
SWEEP_FIRST, SWEEP_LAST = 20, 30          # 11 suspect commits
N_SANDBOXES = SWEEP_LAST - SWEEP_FIRST + 1
SPEEDUP_MIN = 3.0
REQUIRED_FIELDS = ("identified_commit", "identified_index", "evidence", "diff",
                   "serial_seconds", "parallel_seconds", "speedup",
                   "sandboxes_used")


class GateFail(Exception):
    def __init__(self, gate: str, message: str):
        super().__init__(message)
        self.gate, self.message = gate, message


def sh(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True)


def build_fixture(workdir: Path, revert: bool) -> Path:
    """Build the fixture repo into workdir at the pinned seed; return path."""
    outdir = workdir / ("fixture_reverted" if revert else "fixture_planted")
    if outdir.exists():
        subprocess.run(["rm", "-rf", str(outdir)], check=True)
    cmd = [sys.executable, "-I", str(MAKE_FIXTURE), str(outdir)]
    if revert:
        cmd.append("--revert-planted")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"make_fixture.py failed: {proc.stderr.strip()}")
    return outdir


def run_suite(repo: Path) -> tuple[bool, str]:
    """Run test_suite.py in repo; return (passed, output).

    No -I here: the suite imports caseparser from its own directory, and
    the fixture is code this demo generates itself, not downloaded data.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "test_suite.py"], cwd=repo,
            capture_output=True, text=True, timeout=120)
        return proc.returncode == 0, (proc.stdout + proc.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except OSError as exc:
        return False, str(exc)


def _rev_at_head_depth(index: int) -> str:
    """Rev of `index` counted from the oldest commit, relative to a fresh
    clone whose HEAD is the newest commit (NUM_COMMITS-1)."""
    depth = (NUM_COMMITS - 1) - index
    return f"HEAD~{depth}" if depth else "HEAD"


def sweep(workdir: Path, fixture: Path, serial: bool) -> dict:
    """Test every commit in the sweep range in a fresh clone each — the same
    thing one sandbox per commit does — and return
    {"results": {index: passed}, "wall_s": float}.

    The negative-control property lives here: if no commit fails, the sweep
    reports "no regression in range" and never names a commit.
    """
    results: dict[int, bool] = {}
    start = time.monotonic()

    def one(index: int) -> None:
        with tempfile.TemporaryDirectory(prefix=f"commit{index}-") as td:
            clone = Path(td) / "clone"
            subprocess.run(["git", "clone", "-q", str(fixture), str(clone)],
                           check=True, capture_output=True)
            sh(clone, "checkout", "-q", _rev_at_head_depth(index))
            passed, _ = run_suite(clone)
            results[index] = passed

    if serial:
        for i in range(SWEEP_FIRST, SWEEP_LAST + 1):
            one(i)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=N_SANDBOXES) as ex:
            list(ex.map(one, range(SWEEP_FIRST, SWEEP_LAST + 1)))

    wall = time.monotonic() - start
    first_fail = next((i for i in sorted(results) if not results[i]), None)
    return {"results": results, "wall_s": wall, "first_fail": first_fail,
            "report": "no regression in range" if first_fail is None
            else f"first failing commit: index {first_fail}"}


def grade(artifact: Path, seed: int) -> dict:
    gates: dict = {}
    timing: dict = {}
    try:
        _grade(artifact, seed, gates, timing)
    except GateFail as exc:
        return {"artifact": str(artifact), "seed": seed, "passed": False,
                "failed_gate": exc.gate, "reason": exc.message,
                "gates": gates, "timing": timing}
    return {"artifact": str(artifact), "seed": seed, "passed": True,
            "gates": gates, "timing": timing}


def _grade(artifact: Path, seed: int, gates: dict, timing: dict) -> None:
    # -- G1 structure -------------------------------------------------------
    try:
        data = json.loads(artifact.read_text())
    except (OSError, ValueError) as exc:
        raise GateFail("structure", f"not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise GateFail("structure", "top-level must be a JSON object")
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        raise GateFail("structure", f"missing fields: {missing}")
    if not (isinstance(data["identified_commit"], str)
            and re.fullmatch(r"[0-9a-f]{40}", data["identified_commit"])):
        raise GateFail("structure",
                       "identified_commit must be a 40-char hex SHA string")
    if not isinstance(data["identified_index"], int) or \
            isinstance(data["identified_index"], bool):
        raise GateFail("structure", "identified_index must be an int")
    ev = data["evidence"]
    if not (isinstance(ev, dict)
            and isinstance(ev.get("n_minus_1_passes"), bool)
            and isinstance(ev.get("n_fails"), bool)):
        raise GateFail("structure",
                       "evidence must be {n_minus_1_passes: bool, n_fails: bool}")
    if not (isinstance(data["diff"], str) and data["diff"].strip()):
        raise GateFail("structure", "diff must be a non-empty string")
    for f in ("serial_seconds", "parallel_seconds", "speedup"):
        if not isinstance(data[f], (int, float)) or isinstance(data[f], bool) \
                or data[f] <= 0:
            raise GateFail("structure", f"{f} must be a positive number")
    if not (isinstance(data["sandboxes_used"], int)
            and not isinstance(data["sandboxes_used"], bool)):
        raise GateFail("structure", "sandboxes_used must be an int")
    gates["structure"] = {"passed": True, "fields": sorted(REQUIRED_FIELDS)}

    # -- G2 timing arithmetic (no invented numbers) --------------------------
    ratio = data["serial_seconds"] / data["parallel_seconds"]
    err = abs(data["speedup"] - ratio) / ratio
    gates["timing_arithmetic"] = {
        "passed": err <= 0.01,
        "recomputed": round(ratio, 3),
        "claimed": data["speedup"],
        "rel_err": round(err, 5),
    }
    if err > 0.01:
        raise GateFail("timing_arithmetic",
                       f"speedup {data['speedup']:.3f} != serial/parallel "
                       f"{ratio:.3f} (rel err {err:.2%} > 1%)")

    # -- G3 identified: rebuild the fixture, derive the planted SHA ----------
    with tempfile.TemporaryDirectory(prefix="bisect-judge-") as td:
        fixture = build_fixture(Path(td), revert=False)
        planted_sha = sh(fixture, "rev-parse",
                         _rev_at_head_depth(PLANTED_INDEX)).stdout.strip()
        gates["identified"] = {
            "passed": data["identified_commit"] == planted_sha
            and data["identified_index"] == PLANTED_INDEX,
            "planted_sha": planted_sha,
            "claimed_sha": data["identified_commit"],
            "planted_index": PLANTED_INDEX,
            "claimed_index": data["identified_index"],
        }
        if data["identified_commit"] != planted_sha:
            raise GateFail("identified",
                           f"artifact names {data['identified_commit'][:12]} "
                           f"but the planted regression is {planted_sha[:12]} "
                           f"(index {PLANTED_INDEX})")
        if data["identified_index"] != PLANTED_INDEX:
            raise GateFail("identified",
                           f"identified_index {data['identified_index']} != "
                           f"{PLANTED_INDEX}")

        # -- G4 neighbours: the judge sweeps the range itself ----------------
        par = sweep(Path(td), fixture, serial=False)
        timing["parallel_sweep_s"] = round(par["wall_s"], 3)
        res = par["results"]
        prev_ok, this_bad = res[PLANTED_INDEX - 1], not res[PLANTED_INDEX]
        gates["neighbours"] = {
            "passed": prev_ok and this_bad
            and data["evidence"]["n_minus_1_passes"] == res[PLANTED_INDEX - 1]
            and data["evidence"]["n_fails"] == (not res[PLANTED_INDEX]),
            "n_minus_1_passed_measured": prev_ok,
            "n_fails_measured": this_bad,
            "claimed": data["evidence"],
            "sweep_first_fail": par["first_fail"],
        }
        if not prev_ok:
            raise GateFail("neighbours",
                           f"suite also fails at index {PLANTED_INDEX - 1}: "
                           "not a clean regression boundary")
        if not this_bad:
            raise GateFail("neighbours",
                           f"suite passes at index {PLANTED_INDEX}: the "
                           "planted commit does not fail here")
        if data["evidence"]["n_minus_1_passes"] != res[PLANTED_INDEX - 1] or \
                data["evidence"]["n_fails"] != (not res[PLANTED_INDEX]):
            raise GateFail("neighbours",
                           f"artifact evidence {data['evidence']} contradicts "
                           "the judge's measurements "
                           f"(n-1 passed={res[PLANTED_INDEX - 1]}, "
                           f"n failed={not res[PLANTED_INDEX]})")

        # -- G5 diff: compare with git show at the planted commit ------------
        expected_diff = sh(fixture, "show", "--format=", planted_sha).stdout
        norm = lambda s: re.sub(r"\s+", " ", s).strip()
        gates["diff"] = {
            "passed": norm(data["diff"]) == norm(expected_diff),
            "expected_sha": planted_sha,
            "expected_len": len(expected_diff),
            "claimed_len": len(data["diff"]),
        }
        if norm(data["diff"]) != norm(expected_diff):
            raise GateFail("diff",
                           "artifact diff does not match `git show` at the "
                           "planted commit")

        # -- G6 negative control: same sweep on the reverted fixture ---------
        fixture_rev = build_fixture(Path(td), revert=True)
        neg = sweep(Path(td), fixture_rev, serial=False)
        timing["negative_control_sweep_s"] = round(neg["wall_s"], 3)
        gates["negative_control"] = {
            "passed": neg["first_fail"] is None,
            "sweep_report": neg["report"],
            "commits_tested": len(neg["results"]),
        }
        if neg["first_fail"] is not None:
            raise GateFail("negative_control",
                           f"sweep on the reverted fixture still names index "
                           f"{neg['first_fail']} — the oracle must report "
                           "'no regression in range' when none exists")

        # -- G7 speedup: artifact receipts AND the judge's own measurement ---
        ser = sweep(Path(td), fixture, serial=True)
        timing["serial_sweep_s"] = round(ser["wall_s"], 3)
        judge_speedup = ser["wall_s"] / par["wall_s"]
        timing["judge_measured_speedup"] = round(judge_speedup, 2)
        gates["speedup"] = {
            "passed": data["speedup"] >= SPEEDUP_MIN
            and judge_speedup >= SPEEDUP_MIN,
            "required_min": SPEEDUP_MIN,
            "artifact_speedup": data["speedup"],
            "artifact_serial_s": data["serial_seconds"],
            "artifact_parallel_s": data["parallel_seconds"],
        }
        if data["speedup"] < SPEEDUP_MIN:
            raise GateFail("speedup",
                           f"artifact speedup {data['speedup']:.2f}x < "
                           f"{SPEEDUP_MIN}x (the sweep's own receipts)")
        if judge_speedup < SPEEDUP_MIN:
            raise GateFail("speedup",
                           f"judge-measured speedup {judge_speedup:.2f}x < "
                           f"{SPEEDUP_MIN}x (serial {ser['wall_s']:.1f}s vs "
                           f"parallel {par['wall_s']:.1f}s)")

    # -- G8 sandboxes: one sandbox per suspect commit ------------------------
    gates["sandboxes"] = {
        "passed": data["sandboxes_used"] == N_SANDBOXES,
        "expected": N_SANDBOXES,
        "claimed": data["sandboxes_used"],
    }
    if data["sandboxes_used"] != N_SANDBOXES:
        raise GateFail("sandboxes",
                       f"sandboxes_used {data['sandboxes_used']} != "
                       f"{N_SANDBOXES} (one sandbox per suspect commit)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact", type=Path)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    verdict = grade(args.artifact, args.seed)
    text = json.dumps(verdict, indent=2) + "\n"
    if args.json:
        args.json.write_text(text)
    print(text)
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
