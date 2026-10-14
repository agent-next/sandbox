#!/usr/bin/env python3
"""Generate the known-bad family: single-edit mutants of the good parts.

Usage: mutants.py [--out DIR]   (default: $TMPDIR/aicad-mutants-<pid>)

Each mutant is ONE scripted edit of the good artifact, either of
model.py (geometry mutant, rebuilt with the pinned tool) or of the
delivered STL (mesh mutant, byte-edited in place).  Every mutant must
fail at least one judge gate (selftest.sh proves it).  The edit is the
whole story: nothing else differs from the known-good part.
"""
from __future__ import annotations

import argparse
import shutil
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GOOD = REPO / "examples" / "good"

# one-line model.py edits: (name, part, old, new)
MODEL_EDITS = [
    ("plate-hole-count",      "adapter_plate", "N_BOLT_HOLES = 4",     "N_BOLT_HOLES = 3"),
    ("plate-hole-diameter",   "adapter_plate", "BOLT_HOLE_D = 6.5",    "BOLT_HOLE_D = 5.0"),
    ("plate-hole-drift",      "adapter_plate", "FIRST_ANGLE_DEG = 45.0", "FIRST_ANGLE_DEG = 53.0"),
    ("bracket-missing-fillet", "bracket",
     "bd.CenterArc((LEG_T + FILLET_R, LEG_T + FILLET_R), FILLET_R, -90, -90)",
     "bd.Line((LEG_T + FILLET_R, LEG_T), (LEG_T, LEG_T + FILLET_R))"),
    ("bracket-fillet-radius", "bracket", "FILLET_R = 5.0", "FILLET_R = 2.0"),
    ("bushing-scale-25_4",   "bushing", "SHAFT_D = 20.0", "SHAFT_D = 20.0 * 25.4"),
]

# delivered-STL byte edits: (name, part, edit_fn)
STL_EDITS = [
    ("bushing-non-watertight", "bushing", "drop_triangle"),
    ("plate-flipped-facet",    "adapter_plate", "flip_facet"),
]


# ---------------------------------------------------------------------------
def drop_triangle(stl: bytes) -> bytes:
    """Binary STL: remove the first facet record (50 bytes) after the header."""
    n = struct.unpack("<I", stl[80:84])[0]
    body = bytearray(stl[84:84 + 50 * n])
    del body[:50]                      # drop one whole facet
    new_n = n - 1
    return stl[:80] + struct.pack("<I", new_n) + bytes(body) + stl[84 + 50 * n:]


def flip_facet(stl: bytes) -> bytes:
    """Binary STL: swap two vertices of the first facet -> flipped winding."""
    n = struct.unpack("<I", stl[80:84])[0]
    body = bytearray(stl[84:84 + 50 * n])
    v1 = bytes(body[12:24])            # facet = normal(12) + v1..v3(36) + attr(2)
    v2 = bytes(body[24:36])
    body[12:24], body[24:36] = v2, v1  # swap v1/v2
    return stl[:80] + struct.pack("<I", n) + bytes(body) + stl[84 + 50 * n:]


# ---------------------------------------------------------------------------
def build(out: Path, venv_py: Path) -> list[str]:
    built = []
    for name, part, old, new in MODEL_EDITS:
        src_dir = GOOD / part
        dst = out / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src_dir, dst,
                        ignore=shutil.ignore_patterns("model.step", "model.stl"))
        model = dst / "model.py"
        text = model.read_text()
        assert old in text, f"{name}: edit anchor not found in {part}/model.py"
        model.write_text(text.replace(old, new, 1))
        (dst / "part.txt").write_text(f"{part}\n")  # judge reads the part identity
        # rebuild with the pinned tool -> mutated DELIVERED files
        import subprocess
        env = dict(__import__("os").environ, CADGEN_DAEMON="0")
        r = subprocess.run([str(venv_py), "model.py"], cwd=dst, env=env,
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0 or not (dst / "model.step").is_file() \
                or not (dst / "model.stl").is_file():
            print(f"[mutants] {name}: tool run failed:", file=sys.stderr)
            print("\n".join((r.stderr or r.stdout).splitlines()[-4:]), file=sys.stderr)
            continue
        built.append(name)
        print(f"[mutants] built {name} ({part}, model.py edit)")

    for name, part, edit in STL_EDITS:
        src_dir = GOOD / part
        dst = out / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src_dir, dst)
        (dst / "part.txt").write_text(f"{part}\n")  # judge reads the part identity
        stl_path = dst / "model.stl"
        stl_path.write_bytes(globals()[edit](stl_path.read_bytes()))
        built.append(name)
        print(f"[mutants] built {name} ({part}, STL byte edit)")

    return built


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=Path("/tmp/aicad-mutants"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    venv = Path(__import__("os").environ.get(
        "AICAD_JUDGE_VENV", str(Path.home() / ".venvs/aicad-judge"))) / "bin" / "python"
    built = build(args.out, venv)
    print(f"[mutants] {len(built)} mutants in {args.out}")
    return 0 if built else 1


if __name__ == "__main__":
    sys.exit(main())
