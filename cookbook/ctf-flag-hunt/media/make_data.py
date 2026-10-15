"""Real verdict data for the ctf-flag-hunt media: regrade the range.

Grades examples/good, all judge mutants, and a deterministic three-stage
agent loop (broken -> fixed -> good), writing one verdict JSON per run to
the directory given on the command line.  make_media.sh turns these into
the figures and the video; nothing here is invented.

usage: python3 -I make_data.py <outdir> [--seed N]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
JUDGE = HERE.parent / "judge"
GOOD = HERE.parent / "examples" / "good"

# The agent loop, replayed: the same agent that produced examples/good,
# shown at the gates it failed while iterating (all real judge verdicts).
#  1. broken   -- the five files but the vulnerability patched away
#  2. partial  -- vulnerabilities in, the crypto mixer still wrong
#  3. good     -- the committed examples/good
LOOP = [("01-broken", "broken", "fixes the off-by-one"),
        ("02-partial", "partial", "weak mixer"),
        ("03-good", "good", "committed range")]


def run_grade(artifact: Path, out: Path, seed: int, extra: list[str]) -> bool:
    proc = subprocess.run(
        ["bash", str(JUDGE / "grade.sh"), str(artifact),
         "--seed", str(seed), "--json", str(out), *extra],
        capture_output=True, text=True, cwd=str(JUDGE.parent))
    return proc.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--seed", type=int, default=20261015)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    verdicts = outdir / "verdicts"
    verdicts.mkdir(parents=True, exist_ok=True)

    # 1. the good range
    ok = run_grade(GOOD, verdicts / "03-good.json", args.seed, [])
    print(f"make_data: good range grade exit {0 if ok else 1}")

    # 2. the mutants (the self-test kill matrix)
    mutants = outdir / "mutants"
    subprocess.run([sys.executable, "-I", str(JUDGE / "mutants.py"),
                    str(GOOD), str(mutants)], check=True,
                   capture_output=True, text=True, cwd=str(JUDGE.parent))
    killed = 0
    total = 0
    for m in sorted(mutants.iterdir()):
        if not m.is_dir():
            continue
        total += 1
        if not run_grade(m, verdicts / f"mutant-{m.name}.json", args.seed, []):
            killed += 1
    print(f"make_data: mutants killed {killed}/{total}")

    # 3. the agent loop stages: single-edit mutations of examples/good
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        broken = td / "broken"
        shutil.copytree(GOOD, broken)
        p = broken / "notes.c"
        src = p.read_text()
        assert src.count("if (id < 0 || id > n) {") == 1
        p.write_text(src.replace("if (id < 0 || id > n) {",
                                 "if (id < 0 || id >= n) {"))
        run_grade(broken, verdicts / "01-broken.json", args.seed, [])

        partial = td / "partial"
        shutil.copytree(GOOD, partial)
        p = partial / "token.c"
        src = p.read_text()
        assert src.count("x ^= (t << 7);") == 1
        p.write_text(src.replace("x ^= (t << 7);",
                                 "x ^= ((t ^ 0x9e3779b97f4a7c15ULL) << 7);"))
        run_grade(partial, verdicts / "02-partial.json", args.seed, [])

    print(f"make_data: wrote {len(list(verdicts.iterdir()))} verdicts to "
          f"{verdicts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
