#!/usr/bin/env python3
"""Answer one task with one arm policy, in this process, and print JSON.

`judge/bench.py` runs one of these per (arm, task) pair -- 16 tasks x 2 arms,
plus 16 placebo pairs -- so every pair is answered in a fresh process with
nothing carried over from the pair before it.  That is the local stand-in for
"each pair runs in its own disposable sandbox": the isolation is real (a
fresh interpreter, no shared state), only the container is not.

    arm_runner.py <arm> <task_id> <tasks.json> <package_dir>

Prints one JSON object: {"answer": <str>, "ms": <number>} on success, or
{"error": <str>} and exit 1 when the arm cannot answer -- an arm that cannot
find its package must fail loudly, never quietly return an empty answer.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Loading the skill package must not leave a __pycache__ behind: the package
# is an artifact on the desk, and a stray .pyc would make two runs of the
# bench differ on disk for no experimental reason.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import arms  # noqa: E402


def _require_empty_desk(package_dir: Path) -> None:
    """The no-skill arm's desk must be empty; a stray package is an error.

    If a skill package were ever visible to this arm, the experiment would
    silently stop being an A/B test.
    """
    if not package_dir.is_dir():
        raise FileNotFoundError(f"no-skill desk is missing: {package_dir}")
    stray = sorted(p.name for p in package_dir.iterdir())
    if stray:
        raise ValueError(f"no-skill desk is not empty: {stray}")


def _load_placebo(package_dir: Path) -> None:
    """The placebo arm must actually read its package before it answers.

    The package is a README-only skill, so the check is: it exists, it has
    the README, and it carries no code to fall back on.  A missing package
    is an error, not a silent no-skill run.
    """
    readme = package_dir / "README.md"
    if not readme.is_file():
        raise FileNotFoundError(f"placebo package has no README.md: {readme}")
    code = sorted(p.name for p in package_dir.glob("*.py"))
    if code:
        raise ValueError(f"placebo package must not ship code, found {code}")


def main() -> int:
    if len(sys.argv) != 5:
        print("usage: arm_runner.py <arm> <task_id> <tasks.json> <package_dir>",
              file=sys.stderr)
        return 2
    arm, task_id, tasks_path, package_dir = sys.argv[1:5]
    package = Path(package_dir)

    with open(tasks_path, encoding="utf-8") as fh:
        tasks = {t["task_id"]: t for t in json.load(fh)["tasks"]}
    if task_id not in tasks:
        print(json.dumps({"error": f"no such task id {task_id!r}"}))
        return 1
    task = tasks[task_id]

    t0 = time.perf_counter()
    try:
        if arm == "skill":
            techniques = arms.load_skill(package)
            answer = arms.skill_answer(task, techniques)
        elif arm == "noskill":
            _require_empty_desk(package)
            answer = arms.noskill_answer(task)
        elif arm == "placebo":
            _load_placebo(package)
            answer = arms.placebo_answer(task)
        else:
            raise ValueError(f"unknown arm {arm!r}")
    except Exception as exc:                       # fail loudly, not empty
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        return 1
    ms = (time.perf_counter() - t0) * 1000.0

    if not isinstance(answer, str):
        print(json.dumps({"error": f"arm {arm} returned {type(answer).__name__}"}))
        return 1
    print(json.dumps({"answer": answer, "ms": ms}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
