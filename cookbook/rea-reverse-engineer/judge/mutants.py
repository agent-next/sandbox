#!/usr/bin/env python3
"""mutants.py -- known-bad artifacts, each a single-edit mutant of
examples/good/.  Used by judge/selftest.sh.

    mutants.py make-all <outdir>      write one sub-dir per mutant
    mutants.py list                   print mutant names

Each mutant differs from the good artifact by exactly one edit and must fail
at least one judge gate.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
GOOD = os.path.join(DEMO, "examples", "good")
SYMS = os.path.join(HERE, "ground_truth", "build", "symbols.json")


def _edit(path, old, new):
    text = open(path).read()
    assert text.count(old) == 1, "anchor %r not found once in %s" % (old, path)
    open(path, "w").write(text.replace(old, new))


def mut_reimpl_off_by_one(d):
    _edit(os.path.join(d, "checksum", "reimpl.py"),
          "(h << 5) | (h >> 59)", "(h << 6) | (h >> 58)")


def mut_payload_order_swap(d):
    _edit(os.path.join(d, "proto", "reimpl.py"),
          "p[off + 3 + i] * (i + 1)", "p[off + 3 + i] * (ln - i)")


def mut_wrong_key(d):
    _edit(os.path.join(d, "keycheck", "key.txt"),
          "AAAAA-KAYAA-AAAAY", "AAAAA-AAAAA-AAAAA")


def mut_phantom_function(d):
    p = os.path.join(d, "checksum", "report.json")
    r = json.load(open(p))
    r["functions"].append({"label": "FUN_00c0ffee",
                           "address": "0xc0ffee",
                           "role": "does not exist"})
    json.dump(r, open(p, "w"), indent=2)


def mut_missing_target(d):
    shutil.rmtree(os.path.join(d, "proto"))


def mut_fake_evidence(d):
    rea = os.path.join(d, "checksum", "rea")
    for name in sorted(os.listdir(rea)):
        p = os.path.join(rea, name)
        e = json.load(open(p))
        if e.get("operation") == "binary_overview":
            sha = e["subject"]["digest"]["sha256"]
            e["subject"]["digest"]["sha256"] = \
                ("0" if sha[0] != "0" else "1") + sha[1:]
            json.dump(e, open(p, "w"), indent=2)
            return
    raise AssertionError("no binary_overview evidence found")


def mut_wrong_core_addr(d):
    # Point core_function.address at a real but different function so only
    # core_addr fails (no_phantom still passes).
    p = os.path.join(d, "checksum", "report.json")
    r = json.load(open(p))
    syms = json.load(open(SYMS))["checksum"]
    other = next(s for s in syms
                 if not s["name"].startswith("checksum_update")
                 and s["end"] > s["start"])
    r["core_function"]["address"] = hex(other["start"])
    json.dump(r, open(p, "w"), indent=2)


# name -> (apply, gate meant to catch it, why)
MUTANTS = {
    "reimpl-off-by-one":  (mut_reimpl_off_by_one,  "differential", "rotate 5->6"),
    "payload-order-swap": (mut_payload_order_swap, "differential", "reversed payload weights"),
    "wrong-key":          (mut_wrong_key,          "key",          "invalid key string"),
    "phantom-function":   (mut_phantom_function,   "no_phantom",   "claims FUN_00c0ffee"),
    "missing-target":     (mut_missing_target,     "targets",      "proto/ removed"),
    "fake-evidence":      (mut_fake_evidence,      "evidence",     "evidence sha256 edited"),
    "wrong-core-addr":    (mut_wrong_core_addr,    "core",         "core addr moved"),
}


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "list":
        for n in sorted(MUTANTS):
            print(n)
        return
    if len(sys.argv) == 3 and sys.argv[1] == "make-all":
        outdir = sys.argv[2]
        os.makedirs(outdir, exist_ok=True)
        for name, (apply_, _g, _w) in sorted(MUTANTS.items()):
            dst = os.path.join(outdir, name)
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(GOOD, dst)
            apply_(dst)
        return
    sys.exit(__doc__)


if __name__ == "__main__":
    main()
