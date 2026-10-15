#!/usr/bin/env python3
"""Judge self-test on ONE GPU lease (stdlib only).

- generates the mutants into a temp dir
- grades the known-good artifact twice with the same seed -> the two
  verdicts must be identical except the `timing` key (determinism)
- grades every mutant -> each must fail at least one gate
- prints the kill rate; exits 0 only if good passes and >= 90% of mutants
  are killed
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grade as G  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
SEEDS = "101,202,303"


def strip_timing(v):
    v = dict(v)
    v.pop("timing", None)
    return v


def main():
    key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
    if not key:
        G.die("no API key: export SBX_API_KEY (or E2B_API_KEY)")
    good = os.path.join(DEMO, "examples", "good")
    tmp = tempfile.mkdtemp(prefix="go1-selftest-")
    mutdir = os.path.join(tmp, "mutants")
    names = subprocess.run(
        [sys.executable, os.path.join(HERE, "mutants.py"), good, mutdir],
        check=True, capture_output=True, text=True).stdout.split()
    print(f"selftest: {len(names)} mutants: {' '.join(names)}", flush=True)

    results = {}
    with G.Lease(key, 4) as lease:
        print(f"selftest: lease {lease.id}", flush=True)

        rep = G.grade_on_lease(lease, good, SEEDS, 64, 500, 1.0,
                               timeout_s=600)
        good_v = rep.get("verdict")
        results["good_run1"] = good_v
        if not good_v or good_v.get("ok") is not True:
            G.die("known-good artifact did not pass: "
                  + json.dumps(good_v or rep, indent=1)[:800])
        m = good_v["measured"]
        print(f"selftest: good PASS fwd={m['mean_forward_mps']} m/s "
              f"fall={m['fall_rate']} sat={m['max_sat_frac']}", flush=True)

        # determinism: same seed twice -> identical verdict minus timing
        rep2 = G.grade_on_lease(lease, good, SEEDS, 64, 500, 1.0,
                                timeout_s=600)
        good_v2 = rep2.get("verdict")
        results["good_run2"] = good_v2
        if strip_timing(good_v2 or {}) != strip_timing(good_v):
            G.die("determinism check failed: two same-seed grades differ")
        print("selftest: determinism ok (two same-seed grades identical)",
              flush=True)

        killed = 0
        for name in names:
            mdir = os.path.join(mutdir, name)
            args = {}
            aj = os.path.join(mdir, "args.json")
            if os.path.exists(aj):
                args = json.load(open(aj))
            ms = 1.0
            ea = args.get("extra_args") or []
            if "--mass-scale" in ea:
                ms = float(ea[ea.index("--mass-scale") + 1])
            rep = G.grade_on_lease(lease, mdir, SEEDS, 64, 500, ms,
                                   timeout_s=600)
            v = rep.get("verdict")
            results[name] = v
            if v is None:
                print(f"selftest: {name}: judge error "
                      f"{json.dumps(rep)[:300]}", flush=True)
                continue
            failed = [n for n, g in (v.get("gates") or {}).items()
                      if g.get("pass") is False]
            if failed:
                killed += 1
            meas = (v.get("measured") or {})
            print(f"selftest: {name}: {'KILLED' if failed else 'SURVIVED'}"
                  f" ({', '.join(failed) or 'no gate failed'}; "
                  f"fwd={meas.get('mean_forward_mps')})", flush=True)

    rate = killed / len(names)
    out = os.path.join(tmp, "selftest.json")
    with open(out, "w") as fh:
        json.dump(results, fh, indent=1, sort_keys=True)
    print(f"selftest: kill rate {killed}/{len(names)} = {rate:.0%} "
          f"(verdicts: {out})", flush=True)
    if rate < 0.9:
        G.die(f"kill rate {rate:.0%} < 90%")
    print("selftest: PASS", flush=True)


if __name__ == "__main__":
    main()
