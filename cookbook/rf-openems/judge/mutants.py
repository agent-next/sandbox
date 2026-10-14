#!/usr/bin/env python3
"""Generates known-bad artifacts by single-edit mutation of the good example.

Usage:
    python judge/mutants.py generate   # write mutants into examples/bad/
    python judge/mutants.py list
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOOD = os.path.normpath(os.path.join(HERE, "..", "examples", "good", "antenna.py"))
BAD_DIR = os.path.normpath(os.path.join(HERE, "..", "examples", "bad"))

# (filename, human description, mutator(src)->src)
MUTANTS = [
    ("bad_substrate_er.py", "wrong substrate permittivity",
     lambda s: re.sub(r"^er\s*=.*$", "er = 3.2", s, count=1, flags=re.M)),
    ("bad_patch_length.py", "wrong patch length, resonance moved",
     lambda s: re.sub(r"^patch_L\s*=.*$", "patch_L = 24.0", s, count=1, flags=re.M)),
    ("bad_no_ground.py", "missing ground plane",
     lambda s: s.replace('mp.Block(center=mp.Vector3(0, 0, z0 - 0.05),\n                   size=mp.Vector3(sx, sy, 0.1), material=mp.metal)',
                         'None') if 'z0 - 0.05' in s else
            re.sub(r"^(.*ground.*)$", r"# \1", s, flags=re.M)),
    ("bad_feed_center.py", "feed at the patch centre (voltage node)",
     lambda s: re.sub(r"^feed_inset\s*=.*$", "feed_inset = 15.0", s, count=1, flags=re.M)),
    ("bad_coarse_mesh.py", "mesh too coarse to converge",
     lambda s: re.sub(r"^resolution\s*=.*$", "resolution = 4", s, count=1, flags=re.M)),
    ("bad_nan_er.py", "permittivity is NaN",
     lambda s: re.sub(r"^er\s*=.*$", 'er = float("nan")', s, count=1, flags=re.M)),
]


def main():
    out = []
    src = open(GOOD).read()
    os.makedirs(BAD_DIR, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        for name, desc, _ in MUTANTS:
            print(f"{name:28s} {desc}")
        return
    for name, desc, fn in MUTANTS:
        dst = os.path.join(BAD_DIR, name)
        open(dst, "w").write(fn(src))
        out.append(dst)
    print(f"generated {len(out)} mutants into {BAD_DIR}")


if __name__ == "__main__":
    main()
