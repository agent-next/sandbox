#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Grade one `params.json` against the hidden reference. Prints one JSON verdict.

Five gates, all numeric and seeded (see SPEC.md):

    G1  every parameter is a real ClothMaterialSpec field inside its declared range
    G2  mean per-particle position error over the training track <= 3 * e_truth
    G3  the same on the held-out track <= 3 * e_truth_heldout
    G4  RSS's own fold measure matches the reference outcome
    G5  the rollout is finite, bounded and not over-contacting

Exits 0 only if all five pass. Standard library only: this runs on the host, and
shells out to `rollout.py` inside the sandbox that has robosimstudio.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = json.load(open(os.path.join(HERE, "params_table.json")))
FIELDS = TABLE["fields"]
SHELLS = TABLE["shells"]
COUPLINGS = TABLE["couplings"]


def sha256_dir(path):
    """A checksum over every file in a directory, so the judge can prove it did not move."""
    digest = hashlib.sha256()
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            full = os.path.join(root, name)
            digest.update(os.path.relpath(full, path).encode())
            with open(full, "rb") as fh:
                digest.update(fh.read())
    return digest.hexdigest()


def gate_g1(params, table=FIELDS):
    """Every key is a real field, every value inside that field's declared range."""
    problems = []
    seen = set()
    for group in ("cloth", "contact"):
        for key, value in (params.get(group) or {}).items():
            seen.add(key)
            if key not in table:
                problems.append(f"{key!r} is not a ClothMaterialSpec field")
                continue
            spec = table[key]
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                problems.append(f"{key} = {value!r} is not a number")
                continue
            if not spec["lo"] <= float(value) <= spec["hi"]:
                problems.append(
                    f"{key} = {value:g} {spec['unit']} outside [{spec['lo']:g}, {spec['hi']:g}]"
                )
    shell = params.get("shell")
    if shell is not None and shell not in SHELLS:
        problems.append(f"shell = {shell!r} is not one of {SHELLS}")
    # The scene's explicit constraint entries (the paper's Sec. 3 solver/contact
    # choices): they are choices, so an unknown value is rejected rather than
    # ignored, the same way an unknown parameter is.
    constraint = params.get("constraint")
    if constraint is not None:
        if not isinstance(constraint, dict):
            problems.append(f"constraint = {constraint!r} is not an object")
        else:
            for key, value in constraint.items():
                if key == "coupling" and value not in COUPLINGS:
                    problems.append(f"constraint.coupling = {value!r} is not one of {COUPLINGS}")
                elif key == "full_surface_contact" and not isinstance(value, bool):
                    problems.append(f"constraint.full_surface_contact = {value!r} is not a bool")
                elif key not in ("coupling", "full_surface_contact"):
                    problems.append(f"constraint.{key!r} is not a scene entry")
    if not seen:
        problems.append("no cloth or contact parameters given")
    return {"pass": not problems, "problems": problems, "n_params": len(seen)}


def _rollout(env, params, track, out, device, timeout_s):
    """Run rollout.py inside the sandbox environment; return (report, stderr)."""
    cmd = [
        sys.executable, os.path.join(HERE, "rollout.py"),
        "--params", params, "--track", track, "--out", out, "--device", device,
    ]
    started = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, env=env)
    elapsed = round(time.monotonic() - started, 1)
    report = None
    for line in proc.stdout.splitlines():
        if line.startswith("ROLLOUT "):
            report = json.loads(line[len("ROLLOUT "):])
    if report is None:
        report = {"error": "rollout produced no report", "stderr": proc.stderr[-2000:]}
    report["wall_s"] = elapsed
    report["rc"] = proc.returncode
    return report


def trajectory_error(np, sim_q, ref_q):
    """Mean per-particle position error over frames [m], after a rigid-free align.

    Both rollouts start from the same settled sheet, so no alignment is needed:
    the frames are compared in world coordinates, frame by frame.
    """
    n = min(sim_q.shape[0], ref_q.shape[0])
    if n == 0:
        return float("inf")
    d = sim_q[:n].astype("float64") - ref_q[:n].astype("float64")
    return float(np.sqrt((d ** 2).sum(axis=2)).mean())


def fold_measure(np, frames, settled, axis=1):
    """RSS's `cloth_fold`: the sheet's span across the fold axis over its settled span.

    1.0 is untouched, about 0.5 is folded once (see
    `robosimstudio/assetlib/vocabulary/measures.py`). Reimplemented here from the
    positions so it needs no WorldState; the formula is RSS's.
    """
    lo = frames.min(axis=1)
    hi = frames.max(axis=1)
    extent = hi[:, axis] - lo[:, axis]
    base = float(settled[:, axis].max() - settled[:, axis].min())
    if base < 1e-9:
        return 1.0, 0.0
    return float(extent[-1] / base), float(extent[-1])


def load_rollout(np, path):
    with np.load(path) as data:
        return data["q"], data["settled"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", default="")
    ap.add_argument("--reference", default=os.path.join(HERE, "reference"))
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    import numpy as np

    verdict = {
        "artifact": os.path.abspath(args.artifact),
        "seed": args.seed,
        "gates": {},
        "timing": {},
        "judge_sha256": sha256_dir(HERE),
    }
    with open(args.artifact) as fh:
        params = json.load(fh)
    with open(os.path.join(args.reference, "thresholds.json")) as fh:
        thresholds = json.load(fh)

    verdict["gates"]["G1"] = gate_g1(params)
    if not verdict["gates"]["G1"]["pass"]:
        return finish(verdict, args)

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [os.path.expanduser("~/rsssite"), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)

    work = tempfile.mkdtemp(prefix="rss-grade-")
    results = {}
    for name in ("train", "heldout"):
        track = os.path.join(args.reference, f"track_{name}.json")
        out = os.path.join(work, f"{name}.npz")
        report = _rollout(env, args.artifact, track, out, args.device, args.timeout)
        results[name] = report
        verdict["timing"][name] = {"wall_s": report.get("wall_s"), "steps_per_s": report.get("steps_per_s")}
        if report.get("rc") != 0 or not os.path.exists(out):
            verdict["gates"]["G2" if name == "train" else "G3"] = {
                "pass": False,
                "error": "rollout failed",
                "detail": report.get("error") or report.get("stderr", "")[-800:],
            }
            continue

        sim_q, settled = load_rollout(np, out)
        ref_q, _ = load_rollout(np, os.path.join(args.reference, f"ref_{name}.npz"))
        err = trajectory_error(np, sim_q, ref_q)
        tol = thresholds[name]["tolerance_m"]
        ratio = fold_measure(np, sim_q, settled)[0]
        results[name].update({"error_m": err, "tolerance_m": tol, "fold_ratio": ratio})
        verdict["gates"]["G2" if name == "train" else "G3"] = {
            "pass": err <= tol,
            "error_m": round(err, 6),
            "tolerance_m": tol,
            "truth_error_m": thresholds[name]["truth_error_m"],
        }

    # G4: the fold measure must land in the reference's outcome class.
    g4 = {"pass": False, "detail": "no rollout"}
    if "train" in results and "error_m" in results["train"]:
        ratio = results["train"]["fold_ratio"]
        band = thresholds["train"]["fold_ratio_band"]
        g4 = {
            "pass": band[0] <= ratio <= band[1],
            "fold_ratio": round(ratio, 4),
            "band": band,
            "reference_fold_ratio": thresholds["train"]["reference_fold_ratio"],
        }
    verdict["gates"]["G4"] = g4

    # G5: health, on both rollouts.
    health = {}
    for name, report in results.items():
        h = report.get("health")
        health[name] = h
    worst = max((h or {}).get("max_radius", float("inf")) for h in health.values())
    finite = all((h or {}).get("finite", False) for h in health.values()) and bool(health)
    verdict["gates"]["G5"] = {
        "pass": bool(finite and worst <= thresholds["explosion_radius_m"]),
        "finite": finite,
        "max_radius_m": None if worst == float("inf") else round(worst, 4),
        "explosion_radius_m": thresholds["explosion_radius_m"],
    }

    return finish(verdict, args)


def finish(verdict, args):
    gates = verdict["gates"]
    verdict["pass"] = all(g.get("pass") for g in gates.values()) and len(gates) == 5
    verdict["failed"] = sorted(k for k, g in gates.items() if not g.get("pass"))
    text = json.dumps(verdict, indent=2, sort_keys=True)
    if args.json:
        with open(args.json, "w") as fh:
            fh.write(text + "\n")
    print(text)
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
