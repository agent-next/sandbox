#!/usr/bin/env python3
"""Generate known-bad artifacts for the self-test by single edits of the good one.

Each mutant is the good port with exactly one scripted edit; the self-test
expects every mutant to fail at least one gate (SPEC.md). The edits are the
realistic ways a physics port goes wrong: a time-stretched trajectory (the
source's negative), wrong gravity, friction ignored, a wrong timestep,
a pendulum length off by 10 %, a sign flip on the incline, a crash, and a
hardcoded oracle value.
"""

import os
import sys

# (name, must-exist-literal, replacement)
EDIT = [
    ("time_stretched",
     '            if i:\n                mujoco.mj_step(model, data)\n'
     '            p = data.xpos[bid]',
     '            if i:\n                mujoco.mj_step(model, data)\n'
     '            p = data.xpos[bid]'),
    ("wrong_gravity",
     'MJCF.format(name=name, g=g, dt=dt, bodies=DROP.format(',
     'MJCF.format(name=name, g=g / 2.64, dt=dt, bodies=DROP.format('),
    ("friction_ignored",
     'mu = plane["friction_mu"]',
     'mu = plane["friction_mu"] * 0.0'),
    ("wrong_timestep",
     '    g, dt = spec["gravity"], spec["timestep_s"]',
     '    g, dt = spec["gravity"], 0.02'),
    ("pendulum_length_off",
     'L=sc["link"]["L_m"], m=sc["link"]["mass_kg"]))',
     'L=sc["link"]["L_m"] * 1.1, m=sc["link"]["mass_kg"]))'),
    ("incline_sign_flip",
     'quat = quat_string([0, 1, 0], th)',
     'quat = quat_string([0, 1, 0], -th)'),
    ("crash",
     '        model = mujoco.MjModel.from_xml_string(xml)',
     '        model = mujoco.MjModel.from_xml_string(xml[:-8])'),
    ("hardcoded_oracle",
     'def write_csv(path, columns, rows):',
     'T_ORACLE = 2.0073  # the answer, pasted in\n\n\ndef write_csv(path, columns, rows):'),
]


def time_stretch(mutant):
    """The source's negative: scale the recorded t column by 1.3."""
    old = ("            if i:\n"
           "                mujoco.mj_step(model, data)\n")
    new = ("            if i:\n"
           "                mujoco.mj_step(model, data)\n")
    # stretch the written time: every row uses i * dt; scale it instead
    old2 = "            rows.append([i * dt, "
    if old2 not in mutant:
        raise SystemExit("time_stretch: anchor not found")
    return mutant.replace("        for i in range(n + 1):",
                          "        for i in range(int(round(n / 1.3)) + 1):"
                          ).replace("            if i:\n",
                                    "            if i:\n").replace(
              "rows.append([i * dt, ",
              "rows.append([i * dt * 1.3, ")


def main():
    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "examples", "good")
    with open(os.path.join(src_dir, "sim.py")) as fh:
        good = fh.read()
    out_dir = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "mutants")
    os.makedirs(out_dir, exist_ok=True)
    names = []
    for name, old, new in EDIT:
        if name == "time_stretched":
            mutant = time_stretch(good)
            if mutant == good:
                raise SystemExit(f"mutant {name}: edit produced no change")
        else:
            if old not in good:
                raise SystemExit(f"mutant {name}: edit anchor not found in good port")
            mutant = good.replace(old, new, 1)
            if mutant == good:
                raise SystemExit(f"mutant {name}: edit produced no change")
        with open(os.path.join(out_dir, name + ".py"), "w") as fh:
            fh.write(mutant)
        names.append(name)
    print("\n".join(names))


if __name__ == "__main__":
    main()
