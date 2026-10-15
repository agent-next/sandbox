#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate the known-bad artifacts: single-edit mutants of the good one.

Every mutant is one edit of `examples/good/params.json`, so a gate that fails
them is failing on the edit and not on a rewrite. `--out DIR` writes one JSON
file per mutant plus `manifest.json`, which names the edit and the gate each is
expected to fail; `selftest.sh` checks that expectation.

    python3 mutants.py --good examples/good/params.json --out /tmp/mutants
"""

import argparse
import copy
import json
import os

# (name, what it does, which gate it must fail)
MUTANTS = [
    ("stiff_x10", "core_shear_modulus x10 -- cardboard", "G2"),
    ("stiff_div10", "core_shear_modulus /10 -- limp rag", "G2"),
    ("stretch_x100", "tri_ke x100 -- nearly rigid in-plane", "G2"),
    ("friction_zero", "friction = 0 -- the pads cannot hold the edge", "G4"),
    ("damping_huge", "core_damping x100 -- the sheet stops moving", "G2"),
    ("wrong_shell", "shell = membrane -- the model, not the numbers", "G2"),
    ("constraint_fixed", "the paper's Sec. 4.3 edit: a body free in the good "
                         "artifact is pinned, so the fold cannot happen", "G4"),
]


def _set(params, group, key, value):
    params.setdefault(group, {})[key] = value
    return params


def build(good):
    """The mutants, as (name, expected_fail_gate, params)."""
    made = []

    for name, mult, gate in (("stiff_x10", 10.0, "G2"), ("stiff_div10", 0.1, "G2")):
        p = copy.deepcopy(good)
        base = p.get("cloth", {}).get("core_shear_modulus", 1.0e5)
        made.append((name, gate, _set(p, "cloth", "core_shear_modulus", float(base) * mult)))

    p = copy.deepcopy(good)
    base = p.get("cloth", {}).get("tri_ke", 1.0e4)
    made.append(("stretch_x100", "G2", _set(p, "cloth", "tri_ke", float(base) * 100.0)))

    p = copy.deepcopy(good)
    made.append(("friction_zero", "G4", _set(p, "contact", "friction", 0.0)))

    # x100, not x1000: at x1000 the value leaves RSS's declared range (3e-2 * 1000
    # = 30 > 10) and the mutant would be killed by G1 for being unphysical rather
    # than by G2 for being wrong. A mutant has to be legal to be a physics test.
    p = copy.deepcopy(good)
    base = p.get("cloth", {}).get("core_damping", 1.0e-2)
    made.append(("damping_huge", "G2", _set(p, "cloth", "core_damping", float(base) * 100.0)))

    p = copy.deepcopy(good)
    p["shell"] = "membrane"
    made.append(("wrong_shell", "G2", p))

    # The paper's Sec. 4.3 edit, in this scene's terms. The good artifact leaves
    # the scene's own constraint entries alone: one-way coupling with full-surface
    # contact, which is what lets the pads pinch the sheet. Turning the contact
    # model off is "a constraint that is fixed in simulation but free in reality",
    # backwards -- the hand can push the towel but never hold it, so the fold
    # cannot happen while every parameter stays right.
    p = copy.deepcopy(good)
    p["constraint"] = {"coupling": "off", "full_surface_contact": False}
    made.append(("constraint_fixed", "G4", p))

    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--good", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.good) as fh:
        good = json.load(fh)
    os.makedirs(args.out, exist_ok=True)
    manifest = []
    for name, gate, params in build(good):
        path = os.path.join(args.out, f"{name}.json")
        with open(path, "w") as fh:
            json.dump(params, fh, indent=2, sort_keys=True)
            fh.write("\n")
        manifest.append({"name": name, "expected_fail": gate, "path": path})
    with open(os.path.join(args.out, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"{len(manifest)} mutants in {args.out}")
    for row in manifest:
        print(f"  {row['name']:18s} expects {row['expected_fail']}")


if __name__ == "__main__":
    main()
