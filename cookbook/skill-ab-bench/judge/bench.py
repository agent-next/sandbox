#!/usr/bin/env python3
"""Run the skill A/B bench and write one experiment record.

    bench.py <outdir> [--seed N] [--arms skill,noskill[,placebo]]
             [--bootstrap N] [--tasks N]

Every (arm, task) pair is answered by `judge/arm_runner.py` in its own fresh
process, so no pair can see another's work -- the local stand-in for "one
sandbox per pair".  The bench writes `<outdir>/results.json` in the shape
SPEC.md defines and nothing else; the judge (`judge/grade.py`) re-runs every
verifier itself, so the verdicts this file records are only *claims* until
they are replayed.

The bench deliberately does not grade itself: it records what each arm
answered, and whether that answer matched the pinned reference.  A bench that
graded its own answers would be the thing under test and the judge at once.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

JDIR = Path(__file__).resolve().parent
DEMO = JDIR.parent
sys.path.insert(0, str(JDIR))       # -I drops the script dir from sys.path
TASKS_JSON = JDIR / "tasks.json"
RUNNER = JDIR / "arm_runner.py"

SCHEMA = "skill-ab-bench/1"
DEFAULT_SEED = 20261014
ARM_LABELS = {
    "skill": "skill:regex-cookbook",
    "noskill": "noskill:first-attempt",
    "placebo": "placebo:readme-only",
}
# A pair that cannot be answered must not become a silent "wrong answer":
# the bench fails loudly instead (SPEC.md, "Fail loudly").
PAIR_TIMEOUT_S = 60


def _load_tasks() -> list[dict]:
    with open(TASKS_JSON, encoding="utf-8") as fh:
        return json.load(fh)["tasks"]


def run_pair(arm: str, task_id: str, package_dir: Path) -> dict:
    """Answer one (arm, task) pair in a fresh process."""
    proc = subprocess.run(
        [sys.executable, "-I", str(RUNNER), arm, task_id,
         str(TASKS_JSON), str(package_dir)],
        capture_output=True, text=True, timeout=PAIR_TIMEOUT_S)
    if proc.returncode != 0:
        detail = proc.stdout.strip() or proc.stderr.strip()
        raise RuntimeError(f"arm {arm} could not answer {task_id}: {detail}")
    try:
        got = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"arm {arm} on {task_id} printed non-JSON: "
                           f"{proc.stdout[:200]!r}") from exc
    if "answer" not in got or "ms" not in got:
        raise RuntimeError(f"arm {arm} on {task_id} printed {got!r}")
    return got


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--arms", default="skill,noskill,placebo")
    ap.add_argument("--bootstrap", type=int, default=10000,
                    help="resamples the judge will use (recorded only)")
    ap.add_argument("--tasks", type=int, default=0,
                    help="answer only the first N tasks (default: all 16)")
    args = ap.parse_args()

    arm_names = [a.strip() for a in args.arms.split(",") if a.strip()]
    for arm in arm_names:
        if arm not in ARM_LABELS:
            raise SystemExit(f"bench: unknown arm {arm!r}")

    import gen_skill  # noqa: E402  (sibling module, same directory)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    # The packages are scratch, and they must never land inside the artifact
    # directory: the artifact holds exactly one file, results.json (SPEC.md).
    scratch = Path(tempfile.mkdtemp(prefix="skill-ab-bench-pkgs-"))
    packages = gen_skill.build(scratch)

    tasks = _load_tasks()
    if args.tasks:
        tasks = tasks[:args.tasks]
    want_placebo = "placebo" in arm_names

    t0 = time.perf_counter()
    records = []
    for task in tasks:
        rec = {"task_id": task["task_id"], "placebo_flag": want_placebo}
        for arm in ("skill", "noskill"):
            if arm not in arm_names:
                raise SystemExit(f"bench: arm {arm!r} is required for every record")
            got = run_pair(arm, task["task_id"], packages[arm])
            rec[arm] = {
                "passed": got["answer"] == task["answer"],
                "answer": got["answer"],
                "ms": round(got["ms"], 3),
                "policy": ARM_LABELS[arm],
            }
        if want_placebo:
            got = run_pair("placebo", task["task_id"], packages["placebo"])
            rec["placebo"] = {
                "passed": got["answer"] == task["answer"],
                "answer": got["answer"],
                "ms": round(got["ms"], 3),
                "policy": ARM_LABELS["placebo"],
            }
        records.append(rec)

    record = {
        "schema": SCHEMA,
        "arms": {a: ARM_LABELS[a] for a in arm_names},
        "seed": args.seed,
        "tasks": records,
    }
    out = outdir / "results.json"
    out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")

    shutil.rmtree(scratch, ignore_errors=True)
    wall = time.perf_counter() - t0
    n = len(records)
    counts = {a: sum(1 for r in records if r[a]["passed"]) for a in arm_names}
    print(f"bench: {n} tasks x {len(arm_names)} arms = {n * len(arm_names)} "
          f"pairs in {wall:.1f} s")
    for arm in arm_names:
        print(f"  {arm:8s} {counts[arm]}/{n} pass "
              f"({100.0 * counts[arm] / n:.1f} pts)")
    print(f"bench: delta skill-noskill = "
          f"{100.0 * (counts['skill'] - counts['noskill']) / n:+.1f} pts")
    print(f"bench: wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
