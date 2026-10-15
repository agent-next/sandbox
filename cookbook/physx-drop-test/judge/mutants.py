#!/usr/bin/env python3
"""mutants.py — generate the known-bad scenes for the self-test.

Each mutant is a SINGLE-EDIT copy of examples/good/scene.usda: exactly one
contiguous block differs, or (for planted-verdict) exactly one thing is
added to the artifact directory.  Every edit is a realistic authoring
mistake (the silent failure modes listed in the ovphysx authoring docs) or
a deliberate cheat attempt; every one loads without error, so each is
killed by a judge gate, never by a crash before grading.

  physics mutants (1-7)  — wrong physics, killed by the analytic gates
  cheat mutants (8-11)   — artifacts that try to fool the judge itself:
                           kinematic animation, a joint scaffold, a hidden
                           external reference, and forged judge outputs
                           planted beside the scene; killed by G7_contract,
                           the gate that re-reads the artifact itself

Usage: mutants.py <good_scene.usda> <out_dir>
Writes <out_dir>/<name>/scene.usda (plus any planted files) and
<out_dir>/mutants.json.
"""

import io
import json
import math
import struct
import sys
import zipfile
from pathlib import Path

G = 9.81
DT = 1.0 / 240.0
STEPS = 2400
Y_REST = 0.10
E_REST = 0.50


def _npy_bytes(values):
    """A 1-D float64 .npy in the v1 header format (stdlib only, so this
    script runs on a bare python3 the way selftest.sh calls it)."""
    arr = b"".join(struct.pack("<d", v) for v in values)
    header = ("{'descr': '<f8', 'fortran_order': False, 'shape': (%d,)}"
              % len(values)).encode("ascii")
    pad = 64 - (10 + len(header)) % 64 or 64
    return (b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header) + pad)
            + header + b" " * pad + arr)


def _analytic_bounce(h0):
    """Perfect closed-form drop/bounce/rest samples for one body: exactly
    what G2-G6 want, which is what makes the forged outputs a real cheat
    (a judge that read files from beside the scene would pass them)."""
    ys, vs = [], []
    apex, t_apex = h0, 0.0
    for k in range(STEPS):
        t = k * DT
        while True:
            t_fall = math.sqrt(2.0 * max(apex - Y_REST, 0.0) / G)
            if t < t_apex + t_fall - 1e-12 or apex - Y_REST < 5e-4:
                break
            v_up = E_REST * math.sqrt(2.0 * G * (apex - Y_REST))
            t_apex = t_apex + t_fall + v_up / G
            apex = Y_REST + v_up * v_up / (2.0 * G)
        if apex - Y_REST < 5e-4:
            ys.append(Y_REST)
            vs.append(0.0)
            continue
        dt_a = t - t_apex
        ys.append(apex - 0.5 * G * dt_a * dt_a)
        vs.append(-G * dt_a)
    return ys, vs


def forged_outputs():
    """(traj.npz bytes, meta.json text) that pass every gate if read."""
    box_y, box_vy = _analytic_bounce(0.80)
    ball_y, ball_vy = _analytic_bounce(1.20)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for name, values in (("box_y", box_y), ("box_vy", box_vy),
                             ("ball_y", ball_y), ("ball_vy", ball_vy)):
            zf.writestr(f"{name}.npy", _npy_bytes(values))
    meta = {
        "dt": DT, "steps": STEPS,
        "bodies": {p: {"mass": 4.0 if p.endswith("Box") else 1.0,
                       "staticFriction": 0.6, "dynamicFriction": 0.4,
                       "restitution": 0.5, "shapeCount": 1.0}
                   for p in ("/World/Box", "/World/Ball")},
        "sampled": {"/World/Box": True, "/World/Ball": True},
        "missing": [],
    }
    return buf.getvalue(), json.dumps(meta, indent=2) + "\n"


# name -> (description, old, new); `old` must match exactly one place.
# `old is None` marks a mutant that adds files instead of editing text.
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
    # the scene itself is unmodified: the single edit is the two files this
    # mutant adds beside it.  If the judge ever read its inputs from the
    # artifact's own directory, these would pass every gate — that is the
    # cheat being tested, and G7_contract names it.
    "planted-verdict": (
        "cheat: forged judge outputs (a perfect analytic traj.npz + meta.json) "
        "planted beside the scene — the scene passes, the plant would too; "
        "G7_contract rejects judge-output files in the artifact directory",
        None,
        None,
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
        d = out_dir / name
        d.mkdir(exist_ok=True)
        if old is None:                      # a file-planting mutant
            (d / "scene.usda").write_text("\n".join(lines) + "\n")
            npz, meta = forged_outputs()
            (d / "traj.npz").write_bytes(npz)
            (d / "meta.json").write_text(meta)
            made[name] = desc
            continue
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
        (d / "scene.usda").write_text("\n".join(mutated) + "\n")
        made[name] = desc

    (out_dir / "mutants.json").write_text(json.dumps(made, indent=2) + "\n")
    print(f"[mutants] wrote {len(made)} single-edit mutants to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
