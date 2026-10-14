#!/usr/bin/env python3
"""Generates known-bad artifacts by single-edit mutation of the good example.

Usage:
    python judge/mutants.py generate   # write mutants into examples/bad/
    python judge/mutants.py list
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOOD = os.path.normpath(os.path.join(HERE, "..", "examples", "good",
                                     "antenna.py"))
BAD_DIR = os.path.normpath(os.path.join(HERE, "..", "examples", "bad"))

# (filename, human description, mutator(src)->src)
MUTANTS = [
    ("bad_substrate_er.py",
     "wrong substrate permittivity (er=2.2, outside FR-4 sanity range)",
     lambda s: re.sub(r"^er\s*=.*$", "er           = 2.2", s,
                      count=1, flags=re.M)),
    ("bad_patch_length.py",
     "wrong patch length (22 mm moves the resonance to ~3.1 GHz)",
     lambda s: re.sub(r"^patch_L\s*=.*$", "patch_L      = 22.0", s,
                      count=1, flags=re.M)),
    ("bad_no_ground.py",
     "ground-plane box deleted (no return path -> no patch resonance)",
     lambda s: re.sub(r"metal\.AddBox\(\[-sub_m[^#]*# ground\n?",
                      "", s)),
    ("bad_feed_center.py",
     "feed near the patch centre (a TM010 voltage node -> no match)",
     lambda s: re.sub(r"^feed_inset\s*=.*$", "feed_inset   = 12.0", s,
                      count=1, flags=re.M)),
    ("bad_coarse_mesh.py",
     "mesh too coarse (mesh_res=2.4 mm, outside the sanity range)",
     lambda s: re.sub(r"^mesh_res\s*=.*$", "mesh_res     = 2.4", s,
                      count=1, flags=re.M)),
    ("bad_nan_er.py",
     "permittivity set to NaN (parameter no longer a literal constant)",
     lambda s: re.sub(r"^er\s*=.*$", 'er           = float("nan")', s,
                      count=1, flags=re.M)),
    ("bad_thick_substrate.py",
     "substrate too thick (3.5 mm, outside the sanity range)",
     lambda s: re.sub(r"^sub_h\s*=.*$", "sub_h        = 3.5", s,
                      count=1, flags=re.M)),
]


def main():
    src = open(GOOD).read()
    os.makedirs(BAD_DIR, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        for name, desc, _ in MUTANTS:
            print(f"{name:28s} {desc}")
        return
    out = []
    for name, desc, fn in MUTANTS:
        dst = os.path.join(BAD_DIR, name)
        mutated = fn(src)
        if mutated == src:
            raise SystemExit(f"mutant {name}: mutation did not apply!")
        open(dst, "w").write(mutated)
        out.append(dst)
    print(f"generated {len(out)} mutants into {BAD_DIR}")


if __name__ == "__main__":
    main()
