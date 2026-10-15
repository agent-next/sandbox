#!/usr/bin/env python3
"""Generate known-bad go1-walk artifacts as single-edit mutants of the
known-good one. numpy + stdlib only (no torch needed).

    python3 mutants.py examples/good /tmp/go1-mutants

Each mutant is a directory containing policy.npz; mutants that also need a
non-default judge condition carry an args.json {"extra_args": [...]} which
selftest.py appends to the grade call. Prints the mutant names to stdout.
"""

from __future__ import annotations

import json
import os
import shutil
import sys

import numpy as np


def load(path):
    z = np.load(os.path.join(path, "policy.npz"), allow_pickle=False)
    return {k: np.asarray(z[k]) for k in z.files}


def save(dst, arrays, args=None, src_cfg=None):
    os.makedirs(dst, exist_ok=True)
    np.savez(os.path.join(dst, "policy.npz"), **arrays)
    if src_cfg and os.path.exists(src_cfg):
        shutil.copy(src_cfg, os.path.join(dst, "train_config.json"))
    if args:
        with open(os.path.join(dst, "args.json"), "w") as fh:
            json.dump({"extra_args": args}, fh)


def last_layer_idx(a):
    return max(int(k[1:]) for k in a if k.startswith("w"))


def main():
    good, outroot = sys.argv[1], sys.argv[2]
    base = load(good)
    cfg = os.path.join(good, "train_config.json")
    li = last_layer_idx(base)
    rng = np.random.default_rng(20260707)
    names = []

    def put(name, arrays, args=None):
        save(os.path.join(outroot, name), arrays, args, cfg)
        names.append(name)

    # 1. untrained: every weight re-drawn from N(0, 0.3) — a step-0 policy
    a = dict(base)
    for k in a:
        if k.startswith(("w", "b")):
            a[k] = rng.normal(0.0, 0.3, a[k].shape).astype(np.float32)
    put("untrained", a)

    # 2. zero-output: final layer zeroed -> actions pinned at 0 -> stand still
    a = dict(base)
    a[f"w{li}"] = np.zeros_like(a[f"w{li}"])
    a[f"b{li}"] = np.zeros_like(a[f"b{li}"])
    put("zero-output", a)

    # 3. negated: final layer sign-flipped -> mirrored gait
    a = dict(base)
    a[f"w{li}"] = -a[f"w{li}"]
    a[f"b{li}"] = -a[f"b{li}"]
    put("negated-output", a)

    # 4. shuffled-output: permute the 12 output rows -> wrong joints
    a = dict(base)
    perm = rng.permutation(a[f"w{li}"].shape[0])
    a[f"w{li}"] = a[f"w{li}"][perm]
    a[f"b{li}"] = a[f"b{li}"][perm]
    put("shuffled-output", a)

    # 5. noisy: N(0, 0.2) added to every weight -> degraded gait / falls
    a = dict(base)
    for k in a:
        if k.startswith(("w", "b")):
            a[k] = (a[k] + rng.normal(0.0, 0.2, a[k].shape)).astype(np.float32)
    put("noisy-weights", a)

    # 6. saturating: final layer x8 -> actions railed at +-1 -> torque hits cap
    a = dict(base)
    a[f"w{li}"] = a[f"w{li}"] * 8.0
    a[f"b{li}"] = a[f"b{li}"] * 8.0
    put("saturating", a)

    # 7. weak-output: final layer x0.15 -> tiny PD offsets -> barely moves
    a = dict(base)
    a[f"w{li}"] = a[f"w{li}"] * 0.15
    a[f"b{li}"] = a[f"b{li}"] * 0.15
    put("weak-output", a)

    # 8. heavy-robot: the good policy graded against a 2x-mass Go1
    put("mass2x", dict(base), args=["--mass-scale", "2.0"])

    print(" ".join(names))


if __name__ == "__main__":
    main()
