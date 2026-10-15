#!/usr/bin/env python3
"""Generate known-bad single-edit mutants of the good actions.py artifact.

Each mutant is exactly one textual edit (one line replaced or inserted) of
examples/good/actions.py.  Used by judge/selftest.sh to prove the judge
fails bad inputs.  Output: <outdir>/<name>.py plus a summary line per
mutant naming the edit.

Kill targets (SPEC.md "Known-bad artifact family"):
  wrong-cell       computed column targets C*C instead of B*C
  wrong-format     saves via a .csv/CSV path instead of .xlsx
  wrong-sum-range  SUM over B2:B{N-1} instead of B2:B{N}
  no-save          skips the save step entirely
  crash-midway     raises after opening the CSV but before saving
  wrong-total-label  total row labelled TOTAL instead of total
"""

import sys
from pathlib import Path

REPLACEMENTS = [
    ("wrong-cell",
     '        type_text(f"=B{row}*C{row}")',
     '        type_text(f"=C{row}*C{row}")'),
    ("wrong-format",
     'XLSX = f"{CU_DIR}/report.xlsx"',
     'XLSX = f"{CU_DIR}/report.csv"'),
    ("wrong-sum-range",
     '        type_text(f"=SUM(B2:B{last})")',
     '        type_text(f"=SUM(B2:B{last - 1})")'),
    ("no-save",
     '    press("ctrl+shift+s")',
     '    pass  # save skipped: no dialog, no file'),
    ("crash-midway",
     '    last = n + 1          # row of the last data row',
     '    raise SystemExit("actions: simulated crash before saving")'),
    ("wrong-total-label",
     '        type_text("total")',
     '        type_text("TOTAL")'),
]

INSERTIONS = [
    ("no-display-check", '    wid = search_window("soffice")',
     '    raise SystemExit("actions: no DISPLAY, gave up")',
     "aborts immediately: nothing runs, nothing saves"),
]


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: mutants.py <good.py> <outdir>", file=sys.stderr)
        return 2
    good = Path(sys.argv[1]).read_text()
    lines = good.splitlines()
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)

    made = 0
    for name, old, new in REPLACEMENTS:
        hit = [i for i, ln in enumerate(lines) if ln == old]
        if len(hit) != 1:
            print(f"mutants: anchor line {old!r} not found exactly once",
                  file=sys.stderr)
            return 1
        mutated = list(lines)
        mutated[hit[0]] = new
        (outdir / f"{name}.py").write_text("\n".join(mutated) + "\n")
        print(f"mutants: {name}.py  edit: {old!r} -> {new!r}")
        made += 1

    for name, anchor, inserted, note in INSERTIONS:
        hit = [i for i, ln in enumerate(lines) if ln == anchor]
        if len(hit) != 1:
            print(f"mutants: anchor line {anchor!r} not found exactly once",
                  file=sys.stderr)
            return 1
        mutated = lines[:hit[0]] + [inserted] + lines[hit[0]:]
        (outdir / f"{name}.py").write_text("\n".join(mutated) + "\n")
        print(f"mutants: {name}.py  edit: +{inserted!r} ({note})")
        made += 1

    print(f"mutants: wrote {made} mutants to {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
