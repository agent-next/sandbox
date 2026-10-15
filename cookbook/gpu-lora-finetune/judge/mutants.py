#!/usr/bin/env python3
"""Derive the known-bad artifacts for the judge self-test (SPEC.md).

  judge/mutants.py [--out DIR]      (default: ../examples/bad, gitignored)

Each mutant is a single scripted edit or rebuild of the known-good artifact
(examples/good/artifact) and must fail at least one gate. All eight are
listed in SPEC.md "Known-bad examples"; selftest.sh grades them all and
prints the kill rate.
"""

import argparse
import base64
import csv
import json
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
GOOD = os.path.join(DEMO, "examples", "good", "artifact")

MUTANTS = [
    "adapter_not_applied",   # 1  zero-filled adapter (gates 6 + 3)
    "empty_adapter",         # 2  4-byte header-only file (gates 1 + 6)
    "leakage_test_is_train", # 3  predictions on train inputs (gate 2)
    "shuffled_predictions",  # 4  rows reordered (gate 2 order match)
    "no_loss_drop",          # 5  flat noisy losses (gate 5)
    "loss_spike",            # 6  one epoch jump > 0.5 (gate 5)
    "predictions_wrong_format",  # 7  raw template dates (gate 1 regex)
    "copy_of_train_metrics", # 8  claims 0.95, adapter zeroed (gates 3-4)
]


def load_good():
    with open(os.path.join(GOOD, "metrics.json")) as fh:
        return json.load(fh)


def clone(out, name):
    dst = os.path.join(out, name)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(GOOD, dst)
    return dst


def write_json(path, obj):
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)


def zeroed_adapter(dst):
    """Same tensor names/shapes/dtypes as the good adapter, all zeros."""
    import sys as _sys
    _sys.path.insert(0, HERE)
    from safetensors.torch import save_file
    import torch
    from safetensors import safe_open

    src = os.path.join(GOOD, "adapter", "adapter_model.safetensors")
    tensors = {}
    with safe_open(src, framework="pt") as f:
        for k in f.keys():
            tensors[k] = torch.zeros_like(f.get_tensor(k))
    save_file(tensors, os.path.join(dst, "adapter", "adapter_model.safetensors"))


def read_rows():
    with open(os.path.join(GOOD, "predictions.csv"), newline="") as fh:
        return list(csv.reader(fh))


def write_rows(dst, rows):
    with open(os.path.join(dst, "predictions.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerows(rows)


def mutate(out):
    metrics = load_good()
    rows = read_rows()

    # 1. adapter_not_applied — real run's evidence, adapter contributes nothing
    dst = clone(out, MUTANTS[0])
    zeroed_adapter(dst)

    # 2. empty_adapter — header-only safetensors (8-byte header length 0 + 4)
    dst = clone(out, MUTANTS[1])
    st = os.path.join(dst, "adapter", "adapter_model.safetensors")
    with open(st, "wb") as fh:                    # empty header dict, no data
        fh.write(struct.pack("<Q", 0) + b"\0\0\0\0")

    # 3. leakage_test_is_train — "test" predictions on train inputs
    dst = clone(out, MUTANTS[2])
    sys.path.insert(0, HERE)
    import task
    train = task.train_set()
    leak = [["input", "prediction"]] + [
        [t[0], t[1]] for t in train[:len(rows) - 1]]
    write_rows(dst, leak)

    # 4. shuffled_predictions — same rows, inputs no longer in test order
    dst = clone(out, MUTANTS[3])
    body = rows[1:]
    body = body[32:] + body[:32]                  # rotated by 32 rows
    write_rows(dst, [rows[0]] + body)

    # 5. no_loss_drop — flat noisy curve around the first loss
    dst = clone(out, MUTANTS[4])
    m = dict(metrics)
    first = m["losses"][0]
    m["losses"] = [round(first + 0.02 * ((i * 37) % 11) / 11, 5)
                   for i in range(len(m["losses"]))]
    write_json(os.path.join(dst, "metrics.json"), m)

    # 6. loss_spike — one epoch-to-epoch jump > 0.5 in an otherwise good curve
    dst = clone(out, MUTANTS[5])
    m = json.loads(json.dumps(metrics))
    mid = len(m["losses"]) // 2
    m["losses"][mid] = m["losses"][mid - 1] + 0.75
    write_json(os.path.join(dst, "metrics.json"), m)

    # 7. predictions_wrong_format — answers in the input templates, not ISO
    dst = clone(out, MUTANTS[6])
    bad = [["input", "prediction"]] + [
        [r[0], r[0]] for r in rows[1:]]
    write_rows(dst, bad)

    # 8. copy_of_train_metrics — claims 0.95 finetuned, adapter zeroed
    dst = clone(out, MUTANTS[7])
    zeroed_adapter(dst)
    m = dict(metrics)
    m["finetuned_accuracy"] = 0.95
    write_json(os.path.join(dst, "metrics.json"), m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(DEMO, "examples", "bad"))
    args = ap.parse_args()
    if not os.path.isdir(os.path.join(GOOD)):
        raise SystemExit(f"mutants.py: known-good artifact missing at {GOOD}")
    os.makedirs(args.out, exist_ok=True)
    mutate(args.out)
    for name in MUTANTS:
        if not os.path.isdir(os.path.join(args.out, name)):
            raise SystemExit(f"mutants.py: {name} was not generated")
    print(" ".join(MUTANTS))


if __name__ == "__main__":
    sys.exit(main())
