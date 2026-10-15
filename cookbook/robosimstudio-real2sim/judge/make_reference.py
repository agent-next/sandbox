#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the hidden reference rollout and the G2/G3 tolerances.

This is the only place the hidden parameters exist. It draws them from a fixed
seed, simulates two arm tracks (the training one the agent is shown, and a
held-out one it never sees), and writes:

    reference/truth.json          the hidden parameters          (judge only)
    reference/track_train.json    the training track             (shown to the agent)
    reference/track_heldout.json  the held-out track             (judge only)
    reference/ref_train.npz       the reference rollout          (positions only)
    reference/ref_heldout.npz     the held-out reference         (positions only)
    reference/thresholds.json     the calibrated tolerances      (judge only)
    reference/reference.mp4       the video the agent is shown

The tolerance is calibrated, not guessed: the hidden parameters are re-run
under a **different perturbation seed**, and the error between the two runs of
the *same* parameters is `truth_error_m`. G2 passes at `3 * truth_error_m`, so
"it ran" is never enough — the artifact has to land within three times the
noise floor of the truth itself.

    python3 make_reference.py [--seed 0] [--device cuda:0] [--out reference]
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# The hidden parameters, as offsets from the scene's own defaults. `TERRY_TOWELLING`
# is a 500 g/m^2 terry towel (examples/01_cloth/cloth.py); the truth is a
# different but physically ordinary towel, so the agent has a real inference to
# make rather than a lookup.
TRUTH = {
    "cloth": {
        "core_shear_modulus": 2.4e5,   # default 1.0e5: a stiffer drape
        "tri_ke": 1.0e4,               # default, nearly inextensible in-plane
        "core_damping": 3.0e-2,        # default 1.0e-2
        "edge_ke": 1.0e-4,             # default on the towel
    },
    "contact": {
        "friction": 0.25,              # default 0.25
        "contact_ke": 1.0e4,           # default
    },
    "shell": "slab",
}


def _seed_params(seed):
    """The hidden parameters, jittered by `seed`. Seed 0 is the truth exactly."""
    import random

    rng = random.Random(seed)
    params = json.loads(json.dumps(TRUTH))
    if seed == 0:
        return params
    # A perturbation that stays well inside every declared range: each field
    # moves by at most 4 % in log space, which is the run-to-run noise the
    # tolerance is calibrated against.
    for group in ("cloth", "contact"):
        for key, value in params[group].items():
            factor = 10 ** rng.uniform(-0.04, 0.04)
            params[group][key] = float(value) * factor
    return params


def _track(name, seed, steps):
    """A joint-space track: two arms, plus the grippers.

    `train` and `heldout` differ in how the right arm approaches and how far it
    carries, so an artifact fitted to one does not pass the other. Both start
    from the towel example's `over_edge` pose, which is where the scene puts the
    hand over the near edge.
    """
    import numpy as np

    over_edge = np.array([0.274, 2.114, 2.003, -1.459, 0.0, 0.274], dtype=np.float32)
    home = np.array([0.0, 1.047, 1.047, -0.0, 0.0, -0.0], dtype=np.float32)
    if name == "train":
        approach = over_edge
        lift, carry, drop = 0.05, 0.10, -0.04
    else:
        approach = over_edge + np.array([0.03, -0.05, 0.04, 0.0, 0.0, 0.0], dtype=np.float32)
        lift, carry, drop = 0.07, 0.16, -0.07

    rows = []
    for i in range(steps):
        t = i / max(steps - 1, 1)
        if t < 0.25:                       # approach
            q = home + (approach - home) * (t / 0.25)
        elif t < 0.45:                     # close on the edge
            q = approach
        elif t < 0.75:                     # lift and carry over
            u = (t - 0.45) / 0.30
            q = approach.copy()
            q[1] -= lift * u
            q[0] += carry * u
            q[2] += 0.2 * u
        else:                              # place
            u = (t - 0.75) / 0.25
            q = approach.copy()
            q[1] -= lift + drop * u
            q[0] += carry
            q[2] += 0.2 - 0.15 * u
        rows.append([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0] + [float(x) for x in q] + [0.0, 0.0])
    return {
        "name": name,
        "seed": seed,
        "settle_steps": 40,
        "sample_every": 2,
        "joint_targets": rows,
    }


def _run(env, params_path, track_path, out_path, device, timeout_s):
    cmd = [
        sys.executable, os.path.join(HERE, "rollout.py"),
        "--params", params_path, "--track", track_path, "--out", out_path,
        "--device", device,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, env=env)
    report = None
    for line in proc.stdout.splitlines():
        if line.startswith("ROLLOUT "):
            report = json.loads(line[len("ROLLOUT "):])
    if report is None:
        print(proc.stdout[-3000:], file=sys.stderr)
        print(proc.stderr[-3000:], file=sys.stderr)
        raise SystemExit(f"rollout failed for {params_path} on {track_path}")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--out", default=os.path.join(HERE, "reference"))
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--timeout", type=int, default=1800)
    args = ap.parse_args()

    import numpy as np

    os.makedirs(args.out, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [os.path.expanduser("~/rsssite"), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)

    truth_path = os.path.join(args.out, "truth.json")
    with open(truth_path, "w") as fh:
        json.dump(TRUTH, fh, indent=2, sort_keys=True)

    tracks = {}
    for name in ("train", "heldout"):
        track = _track(name, args.seed, args.steps)
        path = os.path.join(args.out, f"track_{name}.json")
        with open(path, "w") as fh:
            json.dump(track, fh)
        tracks[name] = path

    # The truth, and the same truth under a different seed: the difference is
    # the noise floor the tolerance is three of.
    jitter_path = os.path.join(args.out, "truth_seed1.json")
    with open(jitter_path, "w") as fh:
        json.dump(_seed_params(1), fh, indent=2, sort_keys=True)

    thresholds = {"seed": args.seed, "steps": args.steps}
    for name in ("train", "heldout"):
        ref = os.path.join(args.out, f"ref_{name}.npz")
        _run(env, truth_path, tracks[name], ref, args.device, args.timeout)
        other = os.path.join(args.out, f"ref_{name}_seed1.npz")
        _run(env, jitter_path, tracks[name], other, args.device, args.timeout)
        with np.load(ref) as a, np.load(other) as b:
            qa, qb = a["q"].astype("float64"), b["q"].astype("float64")
            settled = a["settled"].astype("float64")
            n = min(qa.shape[0], qb.shape[0])
            truth_error = float(np.sqrt(((qa[:n] - qb[:n]) ** 2).sum(axis=2)).mean())
            lo, hi = qa[-1].min(axis=0), qa[-1].max(axis=0)
            base = float(settled[:, 1].max() - settled[:, 1].min())
            fold_ratio = float((hi[1] - lo[1]) / base) if base > 1e-9 else 1.0
        thresholds[name] = {
            "truth_error_m": truth_error,
            "tolerance_m": 3.0 * truth_error,
            "reference_fold_ratio": fold_ratio,
            "fold_ratio_band": [max(0.0, fold_ratio - 0.15), min(1.0, fold_ratio + 0.15)],
            "frames": int(n),
        }
        os.remove(other)  # only the tolerance is kept; the seed-1 run is not
    thresholds["explosion_radius_m"] = 2.0

    with open(os.path.join(args.out, "thresholds.json"), "w") as fh:
        json.dump(thresholds, fh, indent=2, sort_keys=True)
    print(json.dumps(thresholds, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
