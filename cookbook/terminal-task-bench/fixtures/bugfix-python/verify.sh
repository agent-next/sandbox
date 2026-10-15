#!/usr/bin/env bash
# Verifier for task bugfix-python.
#
# Oracle: an independent test.  The verifier carries its own reference
# implementation and checks the module against it over the full window range
# (including the boundary window == len(values) that the shipped test never
# touches).  The shipped test passing proves nothing, so it is not used.
set -euo pipefail

WORK="${1:?usage: verify.sh <work-dir>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 -I - "$WORK" "$HERE/expected.json" <<'PY'
import importlib.util
import json
import os
import sys

work, exp_path = sys.argv[1], sys.argv[2]
exp = json.load(open(exp_path))
module_path = os.path.join(work, exp["module"])
problems = []


def bad(msg):
    problems.append(msg)
    print("FAIL:", msg)


if not os.path.isfile(module_path):
    bad(f"{exp['module']} is missing")
    sys.exit(1)

spec = importlib.util.spec_from_file_location("rolling_under_test", module_path)
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
except Exception as exc:                       # noqa: BLE001
    bad(f"{exp['module']} does not import: {type(exc).__name__}: {exc}")
    sys.exit(1)

values = exp["values"]
n = len(values)
window = exp["window"]

# 1. the documented length contract, over every valid window
for w in range(1, n + 1):
    want_mean = [sum(values[i:i + w]) / w for i in range(n - w + 1)]
    want_max = [max(values[i:i + w]) for i in range(n - w + 1)]
    for name, want in (("rolling_mean", want_mean), ("rolling_max", want_max)):
        fn = getattr(mod, name, None)
        if fn is None:
            bad(f"{name} is missing from the module")
            continue
        try:
            got = list(fn(values, w))
        except Exception as exc:               # noqa: BLE001
            bad(f"{name}(values, {w}) raised "
                f"{type(exc).__name__}: {exc}")
            continue
        if len(got) != len(want):
            bad(f"{name}(values, {w}) returned {len(got)} values, "
                f"expected {len(want)}")
            continue
        if any(abs(g - x) > 1e-12 for g, x in zip(got, want)):
            bad(f"{name}(values, {w}) is wrong: {got[:4]} != {want[:4]}")

# 2. the boundary the shipped test never reaches
try:
    full = list(mod.rolling_mean(values, n))
    if full != [sum(values) / n]:
        bad(f"rolling_mean(values, {n}) == {full}, "
            f"expected one value {sum(values) / n}")
except Exception as exc:                       # noqa: BLE001
    bad(f"rolling_mean(values, {n}) raised {type(exc).__name__}: {exc}")

# 3. a single-element window
try:
    single = list(mod.rolling_mean([3.5], 1))
    if single != exp["single_value"]:
        bad(f"rolling_mean([3.5], 1) == {single}, "
            f"expected {exp['single_value']}")
except Exception as exc:                       # noqa: BLE001
    bad(f"rolling_mean([3.5], 1) raised {type(exc).__name__}: {exc}")

# 4. both functions must reject a bad window
for w in (0, -1, n + 1):
    for name in ("rolling_mean", "rolling_max"):
        fn = getattr(mod, name, None)
        if fn is None:
            continue
        try:
            fn(values, w)
        except ValueError:
            pass
        except Exception as exc:               # noqa: BLE001
            bad(f"{name}(values, {w}) raised {type(exc).__name__}, "
                "expected ValueError")
        else:
            bad(f"{name}(values, {w}) did not raise ValueError")

# 5. the shipped test must not have been deleted or rewritten away
shipped = os.path.join(work, exp["shipped_test"])
if not os.path.isfile(shipped):
    bad(f"{exp['shipped_test']} was deleted; fix the module, not the test")
elif "test_first_window" not in open(shipped).read():
    bad(f"{exp['shipped_test']} was rewritten; fix the module, not the test")

if problems:
    print(f"bugfix-python: {len(problems)} problem(s)")
    sys.exit(1)
print(f"bugfix-python: OK (contract holds for every window 1..{n}, "
      "boundary cases included)")
PY
