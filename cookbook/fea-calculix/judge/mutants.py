#!/usr/bin/env python3
"""Generate known-bad artifacts as single-edit mutants of examples/good.

Usage: mutants.py <out_dir>
Writes <out_dir>/<name>/design.json + beam.inp for each mutant.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOOD = os.path.join(HERE, "..", "examples", "good")


def load_good():
    with open(os.path.join(GOOD, "design.json")) as f:
        design = json.load(f)
    with open(os.path.join(GOOD, "beam.inp")) as f:
        deck = f.read()
    return design, deck


def emit(outdir, name, design, deck):
    d = os.path.join(outdir, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "design.json"), "w") as f:
        json.dump(design, f, indent=2)
    with open(os.path.join(d, "beam.inp"), "w") as f:
        f.write(deck)


def main():
    outdir = sys.argv[1]
    design, deck = load_good()
    made = []

    # wrong units: dimensions written in metres instead of millimetres
    m = dict(design)
    for k in ("L", "b", "h", "mesh_size"):
        m[k] = m[k] / 1000.0
    emit(outdir, "units-in-metres", m, deck); made.append("units-in-metres")

    # wrong boundary condition: prop the tip as well (propped cantilever)
    emit(outdir, "propped-tip", design,
         deck.replace("NFIX, 1, 3", "NFIX, 1, 3\nNTIP, 3, 3"))
    made.append("propped-tip")

    # load on the wrong node set: -250 N on every tip-face node, not 4 corners
    emit(outdir, "load-on-ntip", design,
         deck.replace("NLOAD, 3,", "NTIP, 3,"))
    made.append("load-on-ntip")

    # too-coarse mesh: rejected — fewer than 2 elements across the width
    m = dict(design); m["mesh_size"] = float(min(design["b"], design["h"]))
    emit(outdir, "coarse-mesh", m, deck); made.append("coarse-mesh")

    # legal but not converged: nz=4 through the height vs nz=8 refined
    m = dict(design); m["b"] = 30.0; m["h"] = 60.0; m["mesh_size"] = 15.0
    emit(outdir, "unconverged", m, deck); made.append("unconverged")

    # load in the wrong direction: +Y instead of -Z
    emit(outdir, "load-wrong-dof", design,
         deck.replace("NLOAD, 3,", "NLOAD, 2,"))
    made.append("load-wrong-dof")

    # wrong load magnitude: -2500 per corner node = 10 kN total
    emit(outdir, "overload-10x", design,
         deck.replace("NLOAD, 3, -250.", "NLOAD, 3, -2500."))
    made.append("overload-10x")

    # under-sized cross-section: stress and deflection exceed the spec
    m = dict(design); m["b"] = 8.0; m["h"] = 40.0
    emit(outdir, "undersized", m, deck); made.append("undersized")

    # missing output request: judge cannot read stresses
    emit(outdir, "no-stress-output", design,
         deck.replace("*EL FILE, ELSET=EMEAS\nS\n", ""))
    made.append("no-stress-output")

    print("\n".join(made))


if __name__ == "__main__":
    main()
