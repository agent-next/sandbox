#!/usr/bin/env python3
"""mutants.py — generate the known-bad scenes for the self-test.

Each mutant is a SINGLE-EDIT copy of examples/good/scene.usda: exactly one
contiguous block differs.  Every edit is a realistic authoring mistake (the
silent failure modes listed in the ovphysx authoring docs) or a deliberate
cheat attempt; every one loads without error, so each is killed by a judge
gate, never by a crash before grading.

  physics mutants (1-7)  — wrong physics, killed by the analytic gates
  cheat mutants (8-10)   — scenes that try to fool the judge itself:
                           kinematic animation, a joint scaffold, and a
                           hidden external reference; killed by G7_contract,
                           the gate that re-reads the artifact itself

Usage: mutants.py <good_scene.usda> <out_dir>
Writes <out_dir>/<name>/scene.usda plus <out_dir>/mutants.json.
"""

import json
import sys
from pathlib import Path

# name -> (description, old, new); `old` must match exactly one place.
MUTANTS = {
    # --- physics mutants: the silent authoring failure modes ---------------
    "gravity-flip": (
        "gravity direction points up instead of down",
        "        vector3f physics:gravityDirection = (0, -1, 0)",
        "        vector3f physics:gravityDirection = (0, 1, 0)",
    ),
    "mass-zero": (
        "box mass authored as 0 kg",
        "        float physics:mass = 4.0",
        "        float physics:mass = 0.0",
    ),
    "no-rigidbody": (
        "PhysicsRigidBodyAPI dropped from the box (a collider that never moves)",
        '    def Xform "Box" (\n'
        '        prepend apiSchemas = ["PhysicsRigidBodyAPI", "PhysicsMassAPI"]',
        '    def Xform "Box" (\n'
        '        prepend apiSchemas = ["PhysicsMassAPI"]',
    ),
    "no-ground-collision": (
        "ground has no PhysicsCollisionAPI (bodies fall through)",
        '    def Cube "Ground" (\n'
        '        prepend apiSchemas = ["PhysicsCollisionAPI", "MaterialBindingAPI"]\n'
        "    )",
        '    def Cube "Ground" (\n'
        '        prepend apiSchemas = ["MaterialBindingAPI"]\n'
        "    )",
    ),
    "spawn-inside-ground": (
        "box spawned at y=0.05, inside the ground plane",
        "        double3 xformOp:translate = (-0.5, 0.8, 0)",
        "        double3 xformOp:translate = (-0.5, 0.05, 0)",
    ),
    "restitution-over-unity": (
        "restitution authored as 1.2 (energy-gaining bounce)",
        "        float physics:restitution = 0.50",
        "        float physics:restitution = 1.20",
    ),
    "cm-units": (
        "stage authored in centimetres (metersPerUnit 0.01), numbers kept",
        "    metersPerUnit = 1",
        "    metersPerUnit = 0.01",
    ),
    # --- cheat mutants: try to fool the judge, not to solve the task -------
    # All three simulate without any error; the judge kills each by name via
    # G7_contract (which parses the artifact itself) and/or the physics
    # gates.  They exist so "the artifact ran and passed" can never be
    # confused with "the artifact is what it claims to be".
    "kinematic-cheat": (
        "cheat: ball switched to kinematic (animation instead of dynamics); "
        "G7_contract rejects kinematic flags",
        "        float physics:mass = 1.0\n"
        "        vector3f physics:velocity = (0, 0, 0)",
        "        float physics:mass = 1.0\n"
        "        bool physics:kinematicEnabled = 1\n"
        "        vector3f physics:velocity = (0, 0, 0)",
    ),
    "joint-scaffold": (
        "cheat: box welded to the ground with a PhysicsFixedJoint; "
        "G7_contract rejects joints",
        "    # --- dynamic box: 4 kg, half-extent 0.10 m, dropped from 0.80 m ---",
        "    # --- dynamic box: 4 kg, half-extent 0.10 m, dropped from 0.80 m ---\n"
        '    def PhysicsFixedJoint "CheatJoint"\n'
        "    {\n"
        "        rel physics:body0:bodyRel = </World/Box>\n"
        "        rel physics:body1:bodyRel = </World/Ground>\n"
        "    }",
    ),
    "hidden-reference": (
        "cheat: scene pulls in an external file via a references arc — "
        "physics is unchanged and passes, only G7_contract (self-contained "
        "artifact rule) kills it",
        'def Xform "World"\n'
        "{",
        'def Xform "World"\n'
        "(\n"
        "    prepend references = @./not-in-this-repo.usda@\n"
        ")\n"
        "{",
    ),
}


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    good = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = good.read_text().splitlines()

    made = {}
    for name, (desc, old, new) in MUTANTS.items():
        old_lines = old.splitlines()
        new_lines = new.splitlines()
        hits = []
        for i in range(len(lines) - len(old_lines) + 1):
            if lines[i:i + len(old_lines)] == old_lines:
                hits.append(i)
        if len(hits) != 1:
            print(f"mutants: ERROR: pattern for '{name}' matched {len(hits)} "
                  f"places (need exactly 1)", file=sys.stderr)
            return 1
        mutated = lines[:hits[0]] + new_lines + lines[hits[0] + len(old_lines):]
        d = out_dir / name
        d.mkdir(exist_ok=True)
        (d / "scene.usda").write_text("\n".join(mutated) + "\n")
        made[name] = desc

    (out_dir / "mutants.json").write_text(json.dumps(made, indent=2) + "\n")
    print(f"[mutants] wrote {len(made)} single-edit mutants to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
