#!/usr/bin/env python3
"""Generate known-bad artifacts for the self-test by single edits of the good one.

Mutants change CONFIG only — the artifact can no longer carry results, so a
mutant survives or dies on what the judge measures when it runs the config.
Each mutant prints one "name<TAB>mode" line on stdout; mode is:

  cpu — kills without a GPU: the structure gate or the cpu-physics oracle
        (the judge runs the CPU reference on the config in cpu-check mode)
  gpu — needs the full mode: the failure is only observable by running the
        mujoco_warp sweep on a GPU slice (contact capacity, slice OOM)

The self-test grades every mutant whose mode the machine can observe, in the
same mode the known-good artifact was graded in.
"""

import copy
import json
import os
import sys


def main():
    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "examples", "good")
    with open(os.path.join(src_dir, "sweep.json")) as fh:
        good = json.load(fh)

    out_dir = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "mutants")
    os.makedirs(out_dir, exist_ok=True)

    mutants = []

    # The cheat this judge exists to reject: the artifact reports its own
    # results. Result keys are contraband -> structure gate.
    m = copy.deepcopy(good)
    m["cpu_steps_per_s"] = 5620
    m["cpu_mujoco_version"] = "3.8.1"
    m["points"] = [{"nworld": n, "steps_per_s": 999999, "qpos_finite": True}
                   for n in m["nworld_ladder"]]
    mutants.append(("smuggled_results", "cpu", m))

    # Scene edits break the canonical-scene contract -> structure gate.
    m = copy.deepcopy(good)
    m["scene"] = m["scene"].replace('gravity="0 0 -9.81"',
                                    'gravity="0 0 9.81"')
    mutants.append(("gravity_flipped", "cpu", m))

    # A missing config key -> structure gate.
    m = copy.deepcopy(good)
    del m["nconmax"]
    mutants.append(("missing_nconmax", "cpu", m))

    # dt=1e-4: the settle window is 0.08 s of sim time — the boxes are still
    # in the air and the arm has not converged at read-back. Observed on CPU
    # and GPU (dt=0.01 was measured stable under implicitfast, so the
    # timestep mutant goes the other way).
    m = copy.deepcopy(good)
    m["timestep"] = 0.0001
    mutants.append(("tiny_timestep", "cpu", m))

    # settle_steps=20: the oracle reads live state after 0.02 s — arm error
    # ~1.4 rad, boxes mid-air. Observed on CPU and GPU.
    m = copy.deepcopy(good)
    m["settle_steps"] = 20
    mutants.append(("short_settle", "cpu", m))

    # solver_iterations=1: the CPU reference's contact solver under-converges
    # and the boxes explode (measured: box speed > 17000 m/s) while the GPU
    # solver converges — cpu-physics kills on CPU, cpu-parity kills on GPU.
    m = copy.deepcopy(good)
    m["solver_iterations"] = 1
    mutants.append(("solver_iter_1", "cpu", m))

    # The headline bug: under-sized contact buffers. nconmax=8/njmax=32 drops
    # contacts once the 8 boxes land; measured tunnelling (box min z -5.7 at
    # nworld=64, and world-0 diverges from the CPU trajectory > 0.05 rad).
    # Only observable on GPU — CPU mj_step ignores these.
    m = copy.deepcopy(good)
    m["nconmax"] = 8
    m["njmax"] = 32
    mutants.append(("low_capacity", "gpu", m))

    # A ladder point past the 4 GiB slice's capacity: put_data fails to
    # allocate and the point is observed failing (clean OOM, not a crash).
    m = copy.deepcopy(good)
    m["nworld_ladder"] = m["nworld_ladder"] + [65536]
    mutants.append(("over_ladder", "gpu", m))

    for name, mode, data in mutants:
        path = os.path.join(out_dir, name + ".json")
        with open(path, "w") as fh:
            json.dump(data, fh, indent=2)
        print(f"{name}\t{mode}")


if __name__ == "__main__":
    main()
