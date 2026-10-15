#!/usr/bin/env python3
"""Record the self-test result as JSON for the loop figure.

    make_selftest_data.py <demo_dir> <out.json> [--seed N]

Runs `judge/mutants.py` to write the known-bad set, grades each mutant with
`judge/grade.sh`, and records the gate that killed it.  The figure then draws
measured kill data, not a hand-written table.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGE = os.path.join(HERE, "..", "judge")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("demo_dir")
    ap.add_argument("out_json")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    demo = os.path.abspath(args.demo_dir)
    good = os.path.join(demo, "examples", "good")
    judge = os.path.join(demo, "judge")
    venv = os.environ.get("VIRAL_VENV",
                          os.path.expanduser("~/.viral-microgen-venv"))
    py = os.path.join(venv, "bin", "python")
    if not os.path.exists(py):
        print(f"make_selftest_data: {py} missing -- run judge/setup.sh first",
              file=sys.stderr)
        return 2

    work = tempfile.mkdtemp(prefix="viral-selftest-")
    try:
        mut_dir = os.path.join(work, "mutants")
        subprocess.run([py, os.path.join(judge, "mutants.py"), good, mut_dir,
                        "--seed", str(args.seed)], check=True,
                       stdout=subprocess.DEVNULL)
        index = json.load(open(os.path.join(mut_dir, "mutants.json")))

        good_json = os.path.join(work, "good.json")
        rc = subprocess.run(["bash", os.path.join(judge, "grade.sh"), good,
                             "--seed", str(args.seed), "--json", good_json],
                            stdout=subprocess.DEVNULL).returncode
        good_verdict = json.load(open(good_json))
        if rc != 0 or not good_verdict.get("passed"):
            print("make_selftest_data: the known-good artifact did not pass",
                  file=sys.stderr)
            return 1

        mutants = []
        killed = 0
        for m in index:
            p = os.path.join(work, m["name"] + ".json")
            rc = subprocess.run(
                ["bash", os.path.join(judge, "grade.sh"),
                 os.path.join(mut_dir, m["name"]), "--seed", str(args.seed),
                 "--json", p], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL).returncode
            v = json.load(open(p))
            is_killed = rc != 0 and not v.get("passed")
            killed += int(is_killed)
            mutants.append(dict(
                name=m["name"], expected_gate=m["expected_gate"],
                killed=is_killed,
                failed_gate=v.get("failed_gate"),
                failed_gates=v.get("failed_gates") or [],
                reason=v.get("reason")))
        out = dict(seed=args.seed, good_passed=True, total=len(mutants),
                   killed=killed,
                   kill_rate=f"{killed / len(mutants):.0%}"
                   if mutants else "n/a",
                   mutants=mutants)
        with open(args.out_json, "w") as f:
            json.dump(out, f, indent=2)
        print(f"make_selftest_data: {killed}/{len(mutants)} killed -> "
              f"{args.out_json}")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
