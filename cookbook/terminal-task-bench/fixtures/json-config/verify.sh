#!/usr/bin/env bash
# Verifier for task json-config.
#
# Oracle: spec mask + invariant.  The mask is the documented schema; the
# invariant (unique ids, weights summing to 100, sorted unique tags) is
# checked numerically and independently of how the file was produced.
set -euo pipefail

WORK="${1:?usage: verify.sh <work-dir>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 -I - "$WORK" "$HERE/expected.json" <<'PY'
import json
import os
import re
import sys

work, exp_path = sys.argv[1], sys.argv[2]
exp = json.load(open(exp_path))
path = os.path.join(work, exp["config"])
problems = []


def bad(msg):
    problems.append(msg)
    print("FAIL:", msg)


if not os.path.isfile(path):
    bad(f"{exp['config']} is missing")
    sys.exit(1)

raw = open(path, "rb").read().decode("utf-8")
if not raw.endswith("\n") or raw.endswith("\n\n"):
    bad("the file must end with exactly one newline")

# 1. it has to be valid JSON, and duplicate keys have to be gone: the
#    standard decoder silently keeps the last duplicate, so check with a
#    hook that records every key seen at each level.
seen_dupes = []


def no_dupes(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        seen_dupes.append(sorted({k for k in keys if keys.count(k) > 1}))
    return dict(pairs)


try:
    cfg = json.loads(raw, object_pairs_hook=no_dupes)
except json.JSONDecodeError as exc:
    bad(f"not valid JSON: {exc}")
    sys.exit(1)
if seen_dupes:
    bad(f"duplicate keys remain: {seen_dupes}")

if not isinstance(cfg, dict):
    bad("the top level must be an object")
    sys.exit(1)

# 2. schema mask
if cfg.get("name") != exp["name"]:
    bad(f"name={cfg.get('name')!r}, expected {exp['name']!r}")
version = cfg.get("version")
if not isinstance(version, str) or not re.fullmatch(exp["version_regex"], version):
    bad(f"version={version!r} does not match {exp['version_regex']}")
elif version != exp["version"]:
    bad(f"version={version!r}, expected {exp['version']!r}")
retries = cfg.get("retries")
if not isinstance(retries, int) or isinstance(retries, bool):
    bad(f"retries={retries!r} is not an integer")
elif retries != exp["retries"]:
    bad(f"retries={retries!r}, expected {exp['retries']!r}")
if cfg.get("enabled") is not True:
    bad(f"enabled={cfg.get('enabled')!r} is not the boolean true")

tags = cfg.get("tags")
if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
    bad("tags must be an array of strings")
else:
    if len(tags) != len(set(tags)):
        bad(f"tags still contain duplicates: {tags}")
    if tags != sorted(tags):
        bad(f"tags are not sorted: {tags}")
    if sorted(set(tags)) != exp["tags"]:
        bad(f"tags are {sorted(set(tags))!r}, expected {exp['tags']!r}")

# 3. weights invariant
weights = cfg.get("weights")
if not isinstance(weights, list) or not weights:
    bad("weights must be a non-empty array")
else:
    ids, total = [], 0
    ok = True
    for i, row in enumerate(weights):
        if not isinstance(row, dict):
            bad(f"weights[{i}] is not an object")
            ok = False
            continue
        if not isinstance(row.get("id"), str):
            bad(f"weights[{i}].id is not a string")
            ok = False
        else:
            ids.append(row["id"])
        w = row.get("weight")
        if not isinstance(w, int) or isinstance(w, bool):
            bad(f"weights[{i}].weight={w!r} is not an integer")
            ok = False
        else:
            total += w
    if ok:
        if len(ids) != len(set(ids)):
            bad(f"weights ids are not unique: {ids}")
        if total != exp["weights_sum"]:
            bad(f"weights sum to {total}, expected {exp['weights_sum']}")
        got = {r["id"]: r["weight"] for r in weights}
        if got != exp["weights"]:
            bad(f"weights are {got}, expected {exp['weights']}")

# 4. formatting: 2-space indent, and either key order is accepted
canonical = {json.dumps(cfg, indent=2) + "\n",
             json.dumps(cfg, indent=2, sort_keys=True) + "\n"}
if raw not in canonical:
    bad("the file is not 2-space indented JSON with one trailing newline")

if problems:
    print(f"json-config: {len(problems)} problem(s)")
    sys.exit(1)
print(f"json-config: OK (valid JSON, no duplicate keys, "
      f"weights sum to {exp['weights_sum']})")
PY
