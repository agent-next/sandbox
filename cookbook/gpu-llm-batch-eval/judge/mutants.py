#!/usr/bin/env python3
"""Generate known-bad bundles for the self-test by single edits of the good one.

Every mutant is `examples/good/bundle.json` with exactly one scripted edit
(plus, where noted, the matching self-report so the mutant is internally
consistent — a bundle that is inconsistent by accident would be caught by
a different gate than the one the mutant targets). The self-test expects
every mutant to fail at least one gate (SPEC.md).

Failure classes, from the brief:

    first_number        answer extraction takes the first number
    inflated_accuracy   reported accuracy above what the generations support
    deflated_accuracy   reported accuracy below it (the band is two-sided)
    truncated           generations cut off by a tiny max_new_tokens
    misaligned          problems shifted against generations
    nondeterministic    temperature > 0, greedy false
    invented_throughput wall time too small for the token count
    cpu_claimed_as_gpu  device says cuda, throughput is a CPU rate
    gpu_rate_on_cpu     device says cpu, throughput is a GPU rate
    empty_generation    one generation is an empty string
    bad_hash            problems_sha256 of a different problem set
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract  # noqa: E402


def load_good():
    path = os.path.join(HERE, "..", "examples", "good", "bundle.json")
    with open(path) as fh:
        return json.load(fh)


def _first_number_accuracy(bundle):
    """What the artifact would report if its extractor took the first number."""
    with open(os.path.join(HERE, "problems.json")) as fh:
        gold = {p["i"]: p["gold"] for p in json.load(fh)["problems"]}
    hits = 0
    for g in bundle["generations"]:
        got = extract.first_number(g["generation"])
        if got is not None and got == gold[g["i"]]:
            hits += 1
    return round(hits / len(bundle["generations"]), 4)


def _set_rate(bundle, tok_s, device):
    """Make the bundle self-consistently report `tok_s` on `device`."""
    bundle["wall_time_s"] = round(bundle["generated_tokens"] / tok_s, 6)
    bundle["throughput_tok_s"] = round(
        bundle["generated_tokens"] / bundle["wall_time_s"], 6)
    bundle["device"] = device


def mutate(name, bundle):
    b = json.loads(json.dumps(bundle))  # deep copy
    if name == "first_number":
        # the artifact's own extractor is wrong, so its reported accuracy is
        # wrong too; the judge re-extracts and disagrees
        b["reported_accuracy"] = _first_number_accuracy(bundle)
        for g in b["generations"]:
            g.pop("extracted_answer", None)
    elif name == "inflated_accuracy":
        b["reported_accuracy"] = min(0.99, round(b["reported_accuracy"] + 0.35, 4))
    elif name == "deflated_accuracy":
        b["reported_accuracy"] = max(0.0, round(b["reported_accuracy"] - 0.35, 4))
    elif name == "truncated":
        b["max_new_tokens"] = 8
        for g in b["generations"]:
            g["generation"] = g["generation"][:20]
            g["max_new_tokens"] = 8
    elif name == "misaligned":
        qs = [g["question"] for g in b["generations"]]
        for g in b["generations"]:
            g["question"] = qs[(g["i"] + 1) % len(qs)]
    elif name == "nondeterministic":
        b["temperature"] = 0.7
        b["greedy"] = False
    elif name == "invented_throughput":
        b["wall_time_s"] = round(b["wall_time_s"] / 1000.0, 6)
    elif name == "cpu_claimed_as_gpu":
        # the artifact reports device "cuda" while its own numbers are a CPU
        # rate: the device claim and the measured rate disagree
        _set_rate(b, 2.0, "cuda")
    elif name == "gpu_rate_on_cpu":
        # the other direction: device says "cpu", the timing is a GPU rate
        _set_rate(b, 2000.0, "cpu")
    elif name == "empty_generation":
        b["generations"][7]["generation"] = ""
    elif name == "bad_hash":
        b["problems_sha256"] = "0" * 64
    else:
        raise SystemExit(f"unknown mutant {name}")
    return b


NAMES = ["first_number", "inflated_accuracy", "deflated_accuracy", "truncated",
         "misaligned", "nondeterministic", "invented_throughput",
         "cpu_claimed_as_gpu", "gpu_rate_on_cpu", "empty_generation",
         "bad_hash"]


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "mutants")
    os.makedirs(out_dir, exist_ok=True)
    good = load_good()
    names = []
    for name in NAMES:
        mutant = mutate(name, good)
        if mutant == good:
            raise SystemExit(f"mutant {name}: edit produced no change")
        with open(os.path.join(out_dir, name + ".json"), "w") as fh:
            json.dump(mutant, fh, indent=1, sort_keys=True)
        names.append(name)
    print("\n".join(names))


if __name__ == "__main__":
    main()
