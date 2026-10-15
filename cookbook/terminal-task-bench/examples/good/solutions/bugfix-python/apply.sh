#!/usr/bin/env bash
# bugfix-python: fix the off-by-one in rolling_mean and re-derive the whole
# contract from scratch.
#
# Rather than patching the loop bound, the module is rewritten so both
# functions share one window iterator; then the contract is checked over
# every valid window, including the boundary window == len(values) the
# shipped test never reaches.
set -euo pipefail

WORK="${WORK:?WORK must point at the task work directory}"

cat > "$WORK/pkg/rolling.py" <<'PY'
"""Rolling statistics used by the bench ingest pipeline.

Contract (see task.md):
    rolling_mean(values, window) -> list[float]
        len(result) == len(values) - window + 1
        result[i] == mean(values[i:i + window])
    ValueError when window < 1 or window > len(values).
"""


def _windows(values, window):
    """Yield every window of `window` consecutive values.

    There are exactly len(values) - window + 1 of them, which is the whole
    point of the contract: the last window must be reported too.
    """
    if window < 1:
        raise ValueError("window must be positive")
    if window > len(values):
        raise ValueError("window larger than the input")
    for i in range(len(values) - window + 1):
        yield values[i:i + window]


def rolling_mean(values, window):
    return [sum(chunk) / window for chunk in _windows(values, window)]


def rolling_max(values, window):
    return [max(chunk) for chunk in _windows(values, window)]
PY

python3 -I - "$WORK" <<'PY'
import importlib.util
import os
import sys

work = sys.argv[1]
path = os.path.join(work, "pkg", "rolling.py")
spec = importlib.util.spec_from_file_location("rolling", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

values = [3, 1, 4, 1, 5, 9, 2, 6, 5]
n = len(values)
for w in range(1, n + 1):
    want = [sum(values[i:i + w]) / w for i in range(n - w + 1)]
    got = list(mod.rolling_mean(values, w))
    if len(got) != len(want) or any(abs(a - b) > 1e-12
                                    for a, b in zip(got, want)):
        raise SystemExit(f"rolling_mean(window={w}) = {got}, want {want}")
    want_max = [max(values[i:i + w]) for i in range(n - w + 1)]
    got_max = list(mod.rolling_max(values, w))
    if got_max != want_max:
        raise SystemExit(f"rolling_max(window={w}) = {got_max}, "
                         f"want {want_max}")
for bad in (0, -1, n + 1):
    for fn in (mod.rolling_mean, mod.rolling_max):
        try:
            fn(values, bad)
        except ValueError:
            continue
        raise SystemExit(f"{fn.__name__}(window={bad}) did not raise")
print(f"bugfix-python: contract holds for every window 1..{n} "
      "(including window == len(values))")
PY
