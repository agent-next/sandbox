#!/usr/bin/env python3
"""judge/mutants.py — generate the known-bad artifacts for the self-test.

Each mutant is a SINGLE edit of the known-good examples/good/eval.py.
Writes one directory per mutant into examples/bad/<name>/ containing the
mutated eval.py and a copy of the good samples.jsonl (so every mutant is
graded against the same, valid samples file — the kill is the edit).
"""

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOOD_DIR = HERE.parent / "examples" / "good"
BAD_DIR = HERE.parent / "examples" / "bad"

# (name, old, new) — old must appear exactly once in good/eval.py
MUTANTS = [
    ("m1_wrong_pass1_formula",
     'pass1 = sum(1 for tid in per_task if c[tid] >= 1) / n_tasks if n_tasks else 0.0',
     'pass1 = sum(c[tid] for tid in per_task) / n_total if n_total else 0.0'),
    ("m2_timeout_counts_as_pass",
     '        except subprocess.TimeoutExpired:\n            return False',
     '        except subprocess.TimeoutExpired:\n            return True'),
    ("m3_metrics_on_stderr",
     '    print(f"pass@1: {pass1:.10f}")',
     '    sys.stderr.write(f"pass@1: {pass1:.10f}\\n")'),
    ("m4_tests_ignored",
     '        return proc.returncode == 0',
     '        return True'),
    ("m5_off_by_one_index",
     '    for i in range(k):\n        num *= n - i',
     '    for i in range(k - 1):\n        num *= n - i'),
]


def main():
    GOOD_EVAL = GOOD_DIR / "eval.py"
    GOOD_SAMPLES = GOOD_DIR / "samples.jsonl"
    src = GOOD_EVAL.read_text()
    if BAD_DIR.exists():
        shutil.rmtree(BAD_DIR)
    BAD_DIR.mkdir(parents=True)
    written = 0
    for name, old, new in MUTANTS:
        count = src.count(old)
        if count != 1:
            print(f"mutants: pattern for {name} found {count}x — must be exactly 1",
                  file=sys.stderr)
            return 1
        d = BAD_DIR / name
        d.mkdir()
        (d / "eval.py").write_text(src.replace(old, new, 1))
        shutil.copy2(GOOD_SAMPLES, d / "samples.jsonl")
        written += 1
    print(f"mutants: wrote {written} single-edit mutants to {BAD_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
