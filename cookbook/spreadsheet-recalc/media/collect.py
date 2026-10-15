#!/usr/bin/env python3
"""Keep compact judge evidence in media/data/ for the figures and video.

Usage (run by make_media.sh with the judge venv python):

    python collect.py <workdir> <outdir>

workdir holds grade.json (verdict for examples/good/dcf_model.xlsx) and
selftest.txt (captured judge/selftest.sh output) plus the good artifact
itself; outdir receives:

    grade.json    the verdict, minus timing keys (byte-stable)
    selftest.json known-good result, per-mutant killing gates, kill rate
    model.json    the artifact's cell layout (labels, inputs, formulas)

Everything is asserted, not trusted: a malformed or failed judge output
raises instead of producing partial figures.
"""

import json
import re
import sys
from pathlib import Path

import openpyxl

RATES = (8, 10, 12)


def die(msg):
    raise SystemExit(f"collect: {msg}")


def main():
    work, out = map(Path, sys.argv[1:3])
    verdict = json.loads((work / "grade.json").read_text())
    if verdict.get("pass") is not True:
        die("known-good verdict is not a pass")
    if verdict.get("seed") != 0:
        die("grade.json must come from seed 0")
    gates = verdict.get("gates")
    if not isinstance(gates, dict) or not gates or not all(gates.values()):
        die(f"bad gates in grade.json: {gates!r}")
    for pct in RATES:
        for key in (f"npv_{pct}_computed", f"npv_{pct}_oracle",
                    f"npv_{pct}_err_pct"):
            if not isinstance(verdict["metrics"].get(key), (int, float)):
                die(f"metric {key} missing from grade.json")
    move = verdict["metrics"].get("negative_control_move_pct")
    if not isinstance(move, (int, float)) or move < 1.0:
        die(f"negative control did not move: {move!r}")

    text = (work / "selftest.txt").read_text()
    if "selftest: known-good: PASS" not in text:
        die("selftest known-good did not pass")
    if "selftest: determinism: OK" not in text:
        die("selftest determinism check missing")
    rows = re.findall(r"^selftest: mutant (\w+): killed \(gate: ([^)]+)\)$",
                      text, re.M)
    if not rows:
        die("no killed-mutant rows in selftest output")
    killed, total, rate = map(int, re.search(
        r"selftest: kill rate: (\d+)/(\d+) = (\d+)%", text).groups())
    if killed != total or len(rows) != total:
        die(f"kill rows ({len(rows)}) do not match kill rate ({killed}/{total})")
    if rate < 90:
        die(f"kill rate {rate}% below the 90% standard")

    wb = openpyxl.load_workbook(
        work / "examples/good/dcf_model.xlsx", data_only=False)
    sheets = {}
    for name in wb.sheetnames:
        sheets[name] = [
            [c.value for c in row] for row in wb[name].iter_rows()
            if any(c.value is not None for c in row)]

    (out / "grade.json").write_text(
        json.dumps(verdict, indent=2, sort_keys=True) + "\n")
    (out / "selftest.json").write_text(json.dumps({
        "known_good": "PASS",
        "mutants": [{"name": n, "killed_by": g.split(",")} for n, g in rows],
        "kill_rate": f"{killed}/{total}",
        "kill_rate_pct": rate,
    }, indent=2, sort_keys=True) + "\n")
    (out / "model.json").write_text(json.dumps(
        {"sheets": sheets}, indent=2, sort_keys=True) + "\n")
    print(f"collect: grade PASS, kill rate {killed}/{total} = {rate}%")


if __name__ == "__main__":
    main()
