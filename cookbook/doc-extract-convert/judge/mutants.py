#!/usr/bin/env python3
"""Generate the known-bad artifacts for the self-test.

Each mutant is the known-good extractor with exactly one edit -- a mistake
real extractors actually make.  Every mutant must fail at least one gate;
the self-test proves the judge is not a rubber stamp.

    m01 total-as-float       one total printed via float() -- the cents
                             get dropped (6420.80 -> "6420.8")
    m03 box-on-whitespace    points every bbox at a blank margin strip --
                             correct values, ungrounded boxes
    m03b whole-page-box      points every bbox at the whole page
    m04 quarantine-everything  refuses every page -- accuracy 0
    m05 wrong-date-format    emits DD/MM/YYYY instead of YYYY-MM-DD
    m06 accept-bad-date      parse_date "succeeds" on anything, so
                             inv-08's "SEE ATTACHED" date becomes a record
                             with an invented date instead of quarantine
    m07 wrong-ink-threshold  (judge-guard mutant, applied to the *judge*,
                             see selftest.sh) -- not generated here

Usage:
    python3 mutants.py --src examples/good --out examples/bad
"""

import os
import re
import shutil
import sys

MUTANTS = {

    "m01-total-as-float": (
        # total goes through float and back with one fraction digit: the
        # cents are silently dropped (6420.80 -> "6420.8"), which fails
        # both the exact-2-decimal schema check and the Decimal comparison.
        '        "total": normalise_total(raw["total"][0]),',
        '        "total": (lambda t: "%.1f" % float(t) if t else None)('
        'normalise_total(raw["total"][0])),'),

    "m03-box-on-whitespace": (
        # values all correct, but every box points at the blank left margin
        '    fields = {}\n'
        '    for name in ("vendor", "invoice_no", "date", "total"):\n'
        '        _, bbox, conf = raw[name]',
        '    fields = {}\n'
        '    for name in ("vendor", "invoice_no", "date", "total"):\n'
        '        _, bbox, conf = raw[name]\n'
        '        bbox = [2, 2, 20, 20]'),

    "m03b-whole-page-box": (
        # every box covers the whole page: the area bound (8%) fails.
        '    fields = {}\n'
        '    for name in ("vendor", "invoice_no", "date", "total"):\n'
        '        _, bbox, conf = raw[name]',
        '    fields = {}\n'
        '    for name in ("vendor", "invoice_no", "date", "total"):\n'
        '        _, bbox, conf = raw[name]\n'
        '        bbox = [0, 0, w, h]'),

    "m04-quarantine-everything": (
        # refuses every page: G1 accuracy 0, and G4 sees 12 quarantined
        # where only 3 are legitimate.
        '    missing = [f for f in ("vendor", "invoice_no", "date", "total")\n'
        '               if f not in raw]',
        '    raw = {}   # refuse everything\n'
        '    missing = [f for f in ("vendor", "invoice_no", "date", "total")\n'
        '               if f not in raw]'),

    "m05-wrong-date-format": (
        # normalises to DD/MM/YYYY instead of YYYY-MM-DD
        '            if 1 <= mo <= 12 and 1 <= d <= 31:\n'
        '                return "%04d-%02d-%02d" % (y, mo, d)',
        '            if 1 <= mo <= 12 and 1 <= d <= 31:\n'
        '                return "%02d/%02d/%04d" % (d, mo, y)'),

    "m06-accept-bad-date": (
        # parse_date "succeeds" on anything: inv-08's "SEE ATTACHED"
        # becomes a record with an invented date instead of quarantine
        '    m = TEXT_DATE_RE.match(t)\n'
        '    if m:\n'
        '        mon = MONTHS.get(m.group(2)[:3].lower())\n'
        '        if mon:\n'
        '            return "%04d-%02d-%02d" % (int(m.group(3)), mon, int(m.group(1)))\n'
        '    return None',
        '    m = TEXT_DATE_RE.match(t)\n'
        '    if m:\n'
        '        mon = MONTHS.get(m.group(2)[:3].lower())\n'
        '        if mon:\n'
        '            return "%04d-%02d-%02d" % (int(m.group(3)), mon, int(m.group(1)))\n'
        '    return t'),
}


def apply_one(src_text, old, new):
    """Apply exactly one edit; fail loudly if the anchor is not there."""
    hits = src_text.count(old)
    if hits != 1:
        raise SystemExit("mutants.py: anchor appears %d times, expected 1: %r"
                         % (hits, old[:60]))
    return src_text.replace(old, new)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="generate known-bad artifacts")
    ap.add_argument("--src", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    demo = os.path.dirname(os.path.abspath(__file__)) + "/.."
    src = args.src or os.path.join(demo, "examples", "good")
    out = args.out or os.path.join(demo, "examples", "bad")
    src_file = os.path.join(src, "extract.py")
    with open(src_file) as f:
        base = f.read()

    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    made = []
    for name, (old, new) in sorted(MUTANTS.items()):
        d = os.path.join(out, name)
        os.makedirs(d)
        with open(os.path.join(d, "extract.py"), "w") as f:
            f.write(apply_one(base, old, new))
        made.append(name)
        print("[mutants] %s" % name)
    print("[mutants] %d mutant(s) -> %s" % (len(made), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
