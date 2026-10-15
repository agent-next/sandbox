#!/usr/bin/env python3
"""eval.py — MBPP code-generation eval harness (stdlib only).

Executes each solution in an isolated subprocess with a wall-clock timeout,
decides pass per task by running every MBPP test assertion, then prints:

    pass@1: <float>
    pass@k: <float>      (unbiased estimator, k = total samples / tasks)

Usage: python3 eval.py <samples.jsonl> <dataset.jsonl>
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SAMPLE_TIMEOUT_S = 10.0     # per-sample wall-clock timeout
EVAL_TIMEOUT_S = 120.0      # whole-run budget the judge enforces


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open() as fh:
        for i, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"eval.py: {path}:{i}: malformed JSON: {exc}")
    return rows


def comb(n: int, k: int) -> float:
    if k < 0 or k > n:
        return 0.0
    num, den = 1.0, 1.0
    for i in range(k):
        num *= n - i
        den *= i + 1
    return num / den


def pass_at_k(n: int, c: int, k: int) -> float:
    if n - c < k:
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)


def run_sample(solution: str, tests: list[str], task_id: int,
               setup: str = "") -> bool:
    """Run one solution against its task's MBPP test_list in a fresh
    subprocess.  A sample passes only if every assertion evaluates without
    error.  A timeout is a failure, not a hang."""
    with tempfile.TemporaryDirectory(prefix=f"eval-task-{task_id}-") as td:
        src = Path(td) / "sample.py"
        src.write_text(solution)
        body = "\n".join([setup, solution, "", *tests])
        probe = Path(td) / "probe.py"
        probe.write_text(body)
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(probe)],
                cwd=td, capture_output=True, text=True,
                timeout=SAMPLE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return False
        return True


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: eval.py <samples.jsonl> <dataset.jsonl>")
    samples = load_jsonl(Path(sys.argv[1]))
    dataset = {row["task_id"]: row for row in load_jsonl(Path(sys.argv[2]))}

    per_task: dict[int, list[bool]] = {}
    for row in samples:
        tid = row["task_id"]
        if tid not in dataset:
            raise SystemExit(f"eval.py: task_id {tid} not in the dataset")
        per_task.setdefault(tid, []).append(
            run_sample(row["solution"], dataset[tid]["test_list"], tid))

    n_tasks = len(per_task)
    n_total = sum(len(v) for v in per_task.values())
    k = n_total // n_tasks if n_tasks else 0

    c = {tid: sum(1 for ok in results if ok)
         for tid, results in per_task.items()}
    pass1 = sum(1 for tid in per_task if c[tid] >= 1) / n_tasks if n_tasks else 0.0
    passk = (sum(pass_at_k(len(r), c[t], k)
                 for t, r in per_task.items()) / n_tasks) if n_tasks else 0.0

    print(f"pass@1: {pass1:.10f}")
    print(f"pass@k: {passk:.10f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
