#!/usr/bin/env python3
"""Reproduce the agent-style loop that produced examples/good/sim.py.

Each iteration is a realistic draft port with one mistake, graded for real
by judge/grade.sh; the previous iteration's failures are the feedback the
agent works from. Drafts are regenerated from the final good port by
single edits (the inverse of the mutation idea: drafts are the mistakes a
real agent makes on the way to passing). Writes examples/good/loop.json.

  draft 1  pendulum pivot at the mass (no gravity torque, flat theta)
  draft 2  pivot fixed; incline box left axis-aligned (not lying flat on
           the plane, so friction acts on an edge)
  draft 3  box oriented with the plane -> the committed good port, PASS

Usage: python3 examples/loop.py    (from cookbook/sim-engine-arena/)
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GOOD = os.path.join(HERE, "good", "sim.py")
GRADE = os.path.join(os.path.dirname(HERE), "judge", "grade.sh")
LOOP_OUT = os.path.join(HERE, "good", "loop.json")

# (change description, must-exist literal, replacement) applied to the good
# port to recover each draft. None = the good port itself (final iteration).
DRAFTS = [
    ("draft 1: hinge body origin at the bob, not the anchor — the "
     "inertial sits at the pivot so gravity applies no torque and the "
     "pendulum stays flat",
     '<inertial pos="0 0 -{L}" mass="{m}" diaginertia="1e-8 1e-8 1e-8"/>',
     '<inertial pos="0 0 0" mass="{m}" diaginertia="1e-8 1e-8 1e-8"/>'),
    ("draft 2: pivot fixed, but the incline box is left axis-aligned "
     "instead of lying flat on the tilted plane",
     '<body name="mover" pos="{pos}" quat="{quat}">',
     '<body name="mover" pos="{pos}">'),
    (None, None, None),
]


def grade(sim_path, workdir):
    out = os.path.join(workdir, "verdict.json")
    proc = subprocess.run(["bash", GRADE, sim_path, "--json", out],
                          capture_output=True, text=True)
    with open(out) as fh:
        verdict = json.load(fh)
    return proc.returncode, verdict


def summarize(verdict):
    """Compact per-iteration record for loop.json (media/loop.png source)."""
    gates = {k: bool(g.get("pass")) for k, g in verdict.get("gates", {}).items()}
    scen = {}
    for name, s in verdict.get("scenarios", {}).items():
        rec = {"pass": all(g.get("pass") for g in s.values())}
        o = s.get("oracle", {})
        for key in ("t_contact", "t_contact_err", "accel", "accel_err",
                    "period", "period_err", "state", "travel_m"):
            if key in o:
                rec[key] = o[key]
        probs = []
        for g in s.values():
            probs += [str(p) for p in (g.get("problems") or [])]
        if probs:
            rec["problems"] = probs
        scen[name] = rec
    return {"gates": gates, "scenarios": scen,
            "judge_intact": verdict.get("judge_intact")}


def main():
    with open(GOOD) as fh:
        good = fh.read()
    iterations = []
    with tempfile.TemporaryDirectory(prefix="arena-loop-") as work:
        for i, (change, old, new) in enumerate(DRAFTS, 1):
            if old is None:
                draft = good
                tag = "final"
            else:
                if old not in good:
                    raise SystemExit(f"draft {i}: anchor not found in good port")
                draft = good.replace(old, new, 1)
                tag = f"draft{i}"
            sim = os.path.join(work, tag + ".py")
            with open(sim, "w") as fh:
                fh.write(draft)
            rc, verdict = grade(sim, work)
            rec = {"iteration": i, "change": change or
                   "final: box oriented with the plane (the committed good port)",
                   "passed": rc == 0, **summarize(verdict)}
            if not rec["passed"]:
                failed = [k for k, ok in rec["gates"].items() if not ok]
                failed += [f"{n}.{k}" for n, s in rec["scenarios"].items()
                           if not s["pass"] for k in ("oracle", "csv_shape")
                           if k in n]
                rec["failed_gates"] = sorted(
                    set(k for k, ok in rec["gates"].items() if not ok) |
                    {f"{n}" for n, s in rec["scenarios"].items()
                     if not s["pass"]})
            iterations.append(rec)
            print(f"loop: iteration {i} ({tag}): "
                  f"{'PASS' if rc == 0 else 'FAIL'}")
            for n, s in rec["scenarios"].items():
                print(f"    {n}: {'ok' if s['pass'] else 'FAIL'} "
                      + ", ".join(f"{k}={s[k]}" for k in
                                  ("t_contact", "accel", "period", "state",
                                   "travel_m") if k in s)
                      + (f"  problems: {s['problems']}" if s.get("problems") else ""))
    result = {"demo": "sim-engine-arena",
              "note": "every iteration graded for real by judge/grade.sh; "
                      "drafts regenerated from the good port by examples/loop.py",
              "iterations": iterations}
    with open(LOOP_OUT, "w") as fh:
        json.dump(result, fh, indent=2)
    print(f"loop: wrote {os.path.relpath(LOOP_OUT, HERE)}")
    sys.exit(0 if iterations[-1]["passed"] else 1)


if __name__ == "__main__":
    main()
