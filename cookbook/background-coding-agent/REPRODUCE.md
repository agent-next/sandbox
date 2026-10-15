VERDICT: (not done: this file must be written by a different agent)

# REPRODUCE — `cookbook/background-coding-agent/`

DEMO-STANDARD.md requires an **independent reproduction by a different
agent (different model family from the builder)**, following only
`README.md` in a fresh sandbox, with the numbers recorded here and compared
against `RECEIPT.md` within the tolerances in `SPEC.md`.

That has not been done. This file is the placeholder for it; the builder
cannot satisfy the requirement by reproducing its own work, so it is left
for a second agent before merge. The steps that agent should take:

1. In a fresh sandbox, follow `README.md` only (do not read `RECEIPT.md`
   first — record your own numbers, then compare).
2. Run, in `cookbook/background-coding-agent/`:
   - `bash judge/setup.sh` (expect exit 0)
   - `bash judge/selftest.sh` (expect exit 0, kill rate 11/11 = 100 %)
   - `bash judge/grade.sh examples/good/delivery.patch --json /tmp/v.json`
     (expect exit 0, `"passed": true`)
   - `python3 -m py_compile run.py` (the `sbx` path cannot run without a
     key; the lead runs it end to end)
3. Record here, as pasted real output: the three exit codes and wall
   times, the kill rate, the tool versions from `judge/VERSIONS.txt`, and
   the full verdict JSON.
4. Compare against `RECEIPT.md`: the verdict JSON must match except for
   `patch`/`pr` path strings; the tool versions must match exactly; wall
   times may differ (network-bound setup especially).

Tolerances (from `SPEC.md`): the verdict JSON is expected byte-identical
apart from path strings and any wall-time fields; the oracle tolerance is
1e-9 relative, which a correct implementation meets with ~1e-16 to spare,
so no numeric drift is acceptable in the verdict.
