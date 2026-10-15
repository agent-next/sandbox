#!/usr/bin/env python3
"""Write known-bad single-edit mutants of the good artifacts.

Geometry mutants rebuild the part from a mutated copy of the agent's build
script (via freecadcmd from the extracted FreeCAD tree), so each bad artifact
is a realistic single-edit slip an agent could make. STL mutants edit the good
mesh directly (missing facets, flipped winding). Each mutant lands in
examples/bad/<name>/ and must fail at least one judge gate.
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GOOD = os.path.join(ROOT, "examples", "good")
BAD = os.path.join(ROOT, "examples", "bad")


def freecadcmd():
    d = os.environ.get("FREECAD_DIR", os.path.expanduser("~/freecad-1.0.1"))
    exe = os.path.join(d, "usr", "bin", "freecadcmd")
    if not os.path.isfile(exe):
        sys.exit("FATAL: freecadcmd not found at %s (run judge/setup.sh)" % exe)
    return exe


def build_mutant(name, script, replacements, extra_files=()):
    """Rebuild a part from the agent's script with single-line edits.

    extra_files are ("part", "filename") tuples copied verbatim from
    examples/good so the mutant still delivers a complete artifact set.
    """
    out_dir = os.path.join(BAD, name)
    os.makedirs(out_dir, exist_ok=True)
    for part, fname in extra_files:
        shutil.copy2(os.path.join(GOOD, part, fname),
                      os.path.join(out_dir, fname))
    mutated = script
    for old, new in replacements:
        assert old in mutated, "mutation anchor not found: %r" % old
        mutated = mutated.replace(old, new, 1)
    tmp = os.path.join(out_dir, "_mutant.py")
    with open(tmp, "w") as f:
        f.write("OUTPUT_DIR = %r\n" % out_dir)
        f.write(mutated)
    res = subprocess.run([freecadcmd(), tmp], capture_output=True, text=True,
                         timeout=600)
    os.unlink(tmp)
    if res.returncode != 0:
        print("  build FAILED for %s: %s" % (name, res.stdout[-200:] + res.stderr[-200:]))
    return res.returncode == 0


def stl_mutant(name, part, drop_facets=None, flip_facets=None):
    """Copy the good part and corrupt the STL: dropped or flipped facets."""
    out_dir = os.path.join(BAD, name)
    os.makedirs(out_dir, exist_ok=True)
    shutil.copy2(os.path.join(GOOD, part, part + ".step"),
                 os.path.join(out_dir, part + ".step"))
    src = os.path.join(GOOD, part, part + ".stl")
    dst = os.path.join(out_dir, part + ".stl")
    with open(src, "rb") as f:
        header = f.read(84)
        n = struct.unpack("<I", header[80:84])[0]
        tris = f.read()
    tris = bytearray(tris)
    for i in (drop_facets or []):
        # degenerate a triangle by zeroing two of its vertices -> hole
        off = i * 50
        tris[off:off + 36] = b"\x00" * 36
    for i in (flip_facets or []):
        off = i * 50
        v = tris[off + 12:off + 48]
        tris[off + 12:off + 24], tris[off + 24:off + 36] = v[12:24], v[0:12]
    with open(dst, "wb") as f:
        f.write(header)
        f.write(bytes(tris))
    return True


MUTANTS = [
    # (name, part, builder)
    ("bushing_bore_22", "bushing",
     lambda: build_mutant(
         "bushing_bore_22", open(os.path.join(ROOT, "agent", "build_bushing.py")).read(),
         [("BORE_D = 20.0", "BORE_D = 22.0")])),
    ("bushing_no_flange", "bushing",
     lambda: build_mutant(
         "bushing_no_flange", open(os.path.join(ROOT, "agent", "build_bushing.py")).read(),
         [("FLANGE_T = 8.0", "FLANGE_T = 0.0")])),
    ("plate_hole_count_5", "plate",
     lambda: build_mutant(
         "plate_hole_count_5", open(os.path.join(ROOT, "agent", "build_plate.py")).read(),
         [("BOLT_N = 6", "BOLT_N = 5")],
         extra_files=[("plate", "plate.dxf")])),
    ("plate_hole_drift", "plate",
     lambda: build_mutant(
         "plate_hole_drift", open(os.path.join(ROOT, "agent", "build_plate.py")).read(),
         [("BOLT_A0 = 0.0", "BOLT_A0 = 3.0")],
         extra_files=[("plate", "plate.dxf")])),
    ("plate_scale_25_4", "plate",
     lambda: build_mutant(
         "plate_scale_25_4", open(os.path.join(ROOT, "agent", "build_plate.py")).read(),
         [("PLATE_L = 100.0", "PLATE_L = 2540.0")],
         extra_files=[("plate", "plate.dxf")])),
    ("bracket_no_fillet", "bracket",
     lambda: build_mutant(
         "bracket_no_fillet", open(os.path.join(ROOT, "agent", "build_bracket.py")).read(),
         [("FILLET_R = 8.0", "FILLET_R = 0.001")])),
    ("bushing_stl_gap", "bushing",
     lambda: stl_mutant("bushing_stl_gap", "bushing",
                        drop_facets=[10, 400, 900, 1300])),
    ("bushing_stl_flip", "bushing",
     lambda: stl_mutant("bushing_stl_flip", "bushing",
                        flip_facets=[5, 300, 1200])),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None,
                    help="build only these mutants")
    args = ap.parse_args()
    if os.path.isdir(BAD):
        shutil.rmtree(BAD)
    os.makedirs(BAD, exist_ok=True)
    ok = 0
    for name, part, builder in MUTANTS:
        if builder is None:
            continue
        if args.only and name not in args.only:
            continue
        print("[mutants] building %s (%s)" % (name, part))
        if builder():
            ok += 1
    print("[mutants] built %d mutants under %s" % (ok, os.path.relpath(BAD, ROOT)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
