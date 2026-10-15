#!/usr/bin/env python3
"""Derive the 8 known-bad artifacts for selftest from the known-good one.

Each mutant is a single scripted edit of examples/good/exercises (see
SPEC.md for which gate kills which). Usage:

    python3 judge/mutants.py <output-dir>

writes <output-dir>/<name>/ for each mutant and prints the names, one
per line.
"""

import shutil
import sys
from pathlib import Path


def edit(path, old, new):
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"mutants.py: {path.name}: pattern not found: {old!r}")
    path.write_text(text.replace(old, new, 1))


def make(good, out, name, fn):
    dst = out / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(good, dst)
    fn(dst)
    print(name)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    out = Path(sys.argv[1])
    good = Path(__file__).resolve().parent.parent / "examples/good/exercises"
    out.mkdir(parents=True, exist_ok=True)

    def m_resubmit_sorry(d):
        edit(d / "Exercises/Ex01.lean", "1 + n = n + 1 := by omega",
             "1 + n = n + 1 := by sorry")

    def m_admit_token(d):
        edit(d / "Exercises/Ex02.lean", "c + b + a := by omega",
             "c + b + a := by admit")

    def m_axiom_cheat(d):
        edit(d / "Exercises/Ex03.lean",
             "theorem exercise_le_refl (n : Nat) : n ≤ n := Nat.le_refl n",
             "axiom exercise_le_refl (n : Nat) : n ≤ n")

    def m_native_decide_cheat(d):
        edit(d / "Exercises/Ex05.lean", "* 2 = 4 := by decide",
             "* 2 = 4 := by native_decide")

    def m_binder_swap(d):
        # statement still compiles and is true — only the statement
        # freeze (gate 1) catches it
        edit(d / "Exercises/Ex07.lean",
             "theorem exercise_add_twice (a b : Nat) : a + 2 * b = 2 * b + a",
             "theorem exercise_add_twice (b a : Nat) : a + 2 * b = 2 * b + a")

    def m_syntax_error(d):
        edit(d / "Exercises/Ex08.lean", "intro n",
             "intro n !!")

    def m_missing_file(d):
        (d / "Exercises/Ex09.lean").unlink()

    def m_broken_proof(d):
        edit(d / "Exercises/Ex10.lean", " := by\n  constructor\n",
             " := by\n  rfl\n  constructor\n")

    for name, fn in [
        ("resubmit_sorry", m_resubmit_sorry),
        ("admit_token", m_admit_token),
        ("axiom_cheat", m_axiom_cheat),
        ("native_decide_cheat", m_native_decide_cheat),
        ("binder_swap", m_binder_swap),
        ("syntax_error", m_syntax_error),
        ("missing_file", m_missing_file),
        ("broken_proof", m_broken_proof),
    ]:
        make(good, out, name, fn)


if __name__ == "__main__":
    main()
