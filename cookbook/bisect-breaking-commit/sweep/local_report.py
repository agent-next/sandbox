#!/usr/bin/env python3
"""Run the sweep locally (no sandboxes) and write the sweep report — the
same per-commit work and the same derivation run.py uses, so the known-good
example is produced by the sweep itself (SPEC.md, "Artifact").

Serial wall: every commit's sweep run one after another.
Parallel wall: every commit's sweep run concurrently (one worker each —
what the 11 sandboxes do in parallel, minus sandbox-lifecycle latency).

Usage: python3 sweep/local_report.py <out.json>   (from the demo directory)
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
SWEEP_FIRST, SWEEP_LAST = 20, 30


def one(index: int, root: Path) -> dict:
    # one fixture per worker, as one fixture per sandbox: each sandbox
    # rebuilds the fixture at the pinned seed (deterministic SHAs), so no
    # worker shares git state with another.
    env = dict(os.environ, FIXTURE_DIR=str(root / f"fixture-{index}"))
    p = subprocess.run(
        ["bash", str(HERE / "one_commit.sh"), str(index)],
        env=env, cwd=DEMO, capture_output=True, text=True, check=True,
        timeout=300)
    return json.loads(p.stdout.strip().splitlines()[-1])


def main() -> int:
    out = Path(sys.argv[1])
    with tempfile.TemporaryDirectory(prefix="local-sweep-") as td:
        root = Path(td)
        t0 = time.monotonic()
        receipts_s = {}
        for i in range(SWEEP_FIRST, SWEEP_LAST + 1):
            receipts_s[i] = one(i, root)
        serial_s = time.monotonic() - t0

        t0 = time.monotonic()
        receipts_p = {}
        with concurrent.futures.ThreadPoolExecutor(
                SWEEP_LAST - SWEEP_FIRST + 1) as ex:
            futs = [ex.submit(one, i, root) for i in range(SWEEP_FIRST,
                                                          SWEEP_LAST + 1)]
            for f in futs:
                r = f.result()
                receipts_p[r["index"]] = r
        parallel_s = time.monotonic() - t0

    bad = sorted(i for i, r in receipts_p.items() if not r["passed"])
    if not bad:
        sys.exit("local_report: no failing commit in range "
                 "(fixture does not reproduce the regression)")
    first = bad[0]
    report = {
        "identified_commit": receipts_p[first]["sha"],
        "identified_index": first,
        "evidence": {"n_minus_1_passes": receipts_p[first - 1]["passed"],
                     "n_fails": not receipts_p[first]["passed"]},
        "diff": receipts_p[first]["diff"],
        "serial_seconds": round(serial_s, 3),
        "parallel_seconds": round(parallel_s, 3),
        "speedup": round(serial_s / parallel_s, 3),
        "sandboxes_used": SWEEP_LAST - SWEEP_FIRST + 1,
    }
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"culprit index {first} sha {report['identified_commit']}")
    print(f"serial {serial_s:.1f}s / parallel {parallel_s:.1f}s "
          f"= {report['speedup']:.2f}x over {report['sandboxes_used']} workers")
    print(f"report written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
