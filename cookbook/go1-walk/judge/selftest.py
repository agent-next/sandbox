#!/usr/bin/env python3
"""Real self-test on one lease. No local dependency beyond the stdlib."""

from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grade as G

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
SEEDS = "101,202,303"


def same_verdict(a, b):
    a, b = copy.deepcopy(a), copy.deepcopy(b)
    a.pop("timing", None)
    b.pop("timing", None)
    a.pop("traces", None)
    b.pop("traces", None)
    return a == b


def checked_verdict(rep):
    v = rep.get("verdict")
    if rep.get("rc") not in (0, 1) or not v or v.get("error"):
        raise RuntimeError("judge execution failed: " + json.dumps(rep)[:1200])
    if (rep["rc"] == 0) != v["ok"]:
        raise RuntimeError("judge exit and verdict disagree")
    return v


def selftest_on_lease(lease, good, out_json, seeds=SEEDS):
    t0 = time.monotonic()
    # Generate mutants with the pinned NumPy already on the lease.
    files = {n: os.path.join(good, n) for n in
             ("policy.npz", "step0.npz", "short.npz", "reward-flipped.npz")}
    files["mutants.py"] = os.path.join(HERE, "mutants.py")
    payload = {n: base64.b64encode(open(p, "rb").read()).decode()
               for n, p in files.items()}
    code = f"""
import base64, os, subprocess, sys
root = os.path.expanduser('~/go1mutants')
os.makedirs(root, exist_ok=True)
for name, value in {payload!r}.items():
    open(os.path.join(root, name), 'wb').write(base64.b64decode(value))
p = subprocess.run([sys.executable, os.path.join(root, 'mutants.py'),
                    root, os.path.join(root, 'mutants')],
                   capture_output=True, text=True, timeout=60)
report['rc'] = p.returncode
report['names'] = p.stdout.split()
report['stderr'] = p.stderr
"""
    result = lease.exec(code, 120)
    rep = result.get("report") or {}
    if result.get("ok") is not True or rep.get("rc") != 0:
        raise RuntimeError("mutant generation failed: " + str(rep))
    names = rep["names"]
    if len(names) < 6 or any(not all(c.isalnum() or c == "-" for c in n)
                             for n in names):
        raise RuntimeError("invalid mutant inventory")
    results = {"mutants": {}, "timing": {}, "seeds": seeds}
    for i in range(2):
        v = checked_verdict(G.grade_on_lease(lease, good, seeds, 64, 500, 1.0))
        results[f"good_run{i+1}"] = v
        m = v.get("measured", {})
        print(f"selftest: good {i+1} {'PASS' if v['ok'] else 'FAIL'} "
              f"fwd={m.get('mean_forward_mps')} m/s "
              f"fall={m.get('fall_rate')} sat={m.get('max_sat_frac')}", flush=True)
        if not v["ok"]:
            raise RuntimeError("known-good artifact did not pass")
    deterministic = same_verdict(results["good_run1"], results["good_run2"])
    results["deterministic"] = deterministic
    if not deterministic:
        raise RuntimeError("same-seed verdict JSON differs outside timing")
    print("selftest: byte-identical verdicts outside timing", flush=True)
    killed = 0
    # Remote files are fetched as data, then shipped to the unchanged judge.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="go1-selftest-") as tmp:
        for name in names:
            path = os.path.join(tmp, "policy.npz")
            data = lease.fetch_file(f"~/go1mutants/mutants/{name}/policy.npz")
            with open(path, "wb") as fh:
                fh.write(data)
            mass = 2.0 if name == "mass2x" else 1.0
            v = checked_verdict(G.grade_on_lease(lease, tmp, seeds, 64, 500, mass))
            failed = [n for n, g in v["gates"].items() if not g["pass"]]
            killed += bool(failed)
            results["mutants"][name] = {"verdict": v, "failed_gates": failed}
            print(f"selftest: {name}: {'KILLED' if failed else 'SURVIVED'} "
                  f"({', '.join(failed)}; "
                  f"fwd={v['measured']['mean_forward_mps']})", flush=True)
    rate = killed / len(names)
    results.update(killed=killed, total=len(names), kill_rate=rate,
                   ok=rate >= 0.9 and killed == len(names))
    results["timing"]["wall_s"] = round(time.monotonic() - t0, 3)
    with open(out_json, "w") as fh:
        json.dump(results, fh, indent=2, sort_keys=True)
    print(f"selftest: kill rate {killed}/{len(names)} = {rate:.0%}; "
          f"{'PASS' if results['ok'] else 'FAIL'}", flush=True)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", default=os.path.join(DEMO, "examples", "good"))
    ap.add_argument("--json", default=os.path.join(DEMO, "out", "selftest.json"))
    a = ap.parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
    key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
    if not key:
        G.die("export SBX_API_KEY (or E2B_API_KEY)")
    with G.Lease(key, 4) as lease:
        print(f"selftest: created {lease.id}", flush=True)
        results = selftest_on_lease(lease, a.artifact, a.json)
    return 0 if results["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
