#!/usr/bin/env bash
# json-config: parse the file tolerantly, repair the types, write it back as
# canonical JSON.
#
# The duplicate keys are collected with an object_pairs_hook (json's default
# decoder would silently keep the last one, hiding the problem), the
# offending values are converted, and the result is re-parsed and checked
# against the same invariants the verifier uses before it is written.
set -euo pipefail

WORK="${WORK:?WORK must point at the task work directory}"

python3 -I - "$WORK" <<'PY'
import json
import os
import re
import sys

work = sys.argv[1]
path = os.path.join(work, "config.json")

text = open(path, encoding="utf-8").read()
# a trailing comma is the one thing a tolerant parse cannot take; drop it
# only where it is illegal (right before a closing bracket)
text = re.sub(r",(\s*[\]}])", r"\1", text)

duplicates = []


def collect(pairs):
    keys = [k for k, _ in pairs]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        duplicates.append(dupes)
    # keep the last occurrence, which is what a scheduler reading this file
    # would effectively have used
    return dict(pairs)


cfg = json.loads(text, object_pairs_hook=collect)

name = cfg["name"]
version = str(cfg["version"])
if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    raise SystemExit(f"json-config: version {version!r} is not x.y.z")
retries = int(cfg["retries"])

enabled = cfg["enabled"]
if isinstance(enabled, str):
    enabled = enabled.strip().lower() == "true"
else:
    enabled = bool(enabled)

tags = sorted({str(t) for t in cfg.get("tags", [])})

weights = []
for row in cfg["weights"]:
    weights.append({"id": str(row["id"]), "weight": int(row["weight"])})
ids = [r["id"] for r in weights]
if len(ids) != len(set(ids)):
    raise SystemExit(f"json-config: weights ids are not unique: {ids}")
total = sum(r["weight"] for r in weights)
if total != 100:
    raise SystemExit(f"json-config: weights sum to {total}, expected 100")

out = {
    "name": name,
    "version": version,
    "retries": retries,
    "enabled": enabled,
    "tags": tags,
    "weights": weights,
}
rendered = json.dumps(out, indent=2) + "\n"

# re-parse what we are about to write and re-check the invariants
back = json.loads(rendered)
assert isinstance(back["retries"], int) and not isinstance(back["retries"], bool)
assert back["enabled"] is True or back["enabled"] is False
assert sorted({r["id"] for r in back["weights"]}) == sorted(ids)
assert sum(r["weight"] for r in back["weights"]) == 100
assert len(back["tags"]) == len(set(back["tags"])) == len(tags)

with open(path, "w", encoding="utf-8") as fh:
    fh.write(rendered)

print(f"json-config: valid JSON, removed {sum(len(d) for d in duplicates)} "
      f"duplicate key(s), weights sum to {total}")
PY
