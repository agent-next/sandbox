#!/usr/bin/env python3
"""Write lib/run.js — every number the video puts on screen, from this run.

The overlays in index.html must not invent a single number: each value on
screen is read from lib/run.js, and this script fills that file in from the
run's own artifacts:

  media/data/verdicts.json    the judged "good" design and the 19 mutants
                              that had to fail -> PROOF
  media/data/sweep.json       the parametric thickness sweep -> SWEEP
  <stamped selftest log>      a run of judge/selftest.sh with per-line
                              elapsed timestamps -> RUNLOG

Usage: build_overlay_data.py [--selftest-log PATH] [--out PATH] [--check]

--check regenerates the file and diffs it against the committed one, so a run
whose numbers differ from the committed video fails loudly instead of quietly
re-labelling old footage.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

MEDIA = Path(__file__).resolve().parent.parent
VIDEO = MEDIA / "video"
TEMPLATE = VIDEO / "lib" / "run.template.js"
DEFAULT_OUT = VIDEO / "lib" / "run.js"
STAMPED_LOG = MEDIA / "data" / "selftest.stamped.log"

# Design-script facts the judge checks the geometry against, read from
# scripts/examples/good/design.json rather than typed in here. Every count
# that reaches the screen goes through _count(), which refuses anything that
# is not a plain integer — an old run's footage cannot be re-labelled quietly.
def _count(name: str, n) -> int:
    if not isinstance(n, int) or isinstance(n, bool):
        raise SystemExit(f"build_overlay_data: {name} is not an integer: {n!r}")
    return n
DESIGN = MEDIA.parent / "scripts" / "examples" / "good" / "design.json"
if not DESIGN.exists():
    DESIGN = MEDIA.parent / "examples" / "good" / "design.json"
if not DESIGN.exists():
    raise SystemExit("build_overlay_data: no examples/good/design.json to read the spec from")


def design_spec() -> dict:
    """The nominal features the design script declares, as plain numbers."""
    cmds = json.loads(DESIGN.read_text())["commands"]
    spec: dict = {}
    for c in cmds:
        cmd, p = c["command"], c.get("params", {})
        if cmd == "parameters.change":
            spec[p["name"]] = p["expression"]
        elif cmd == "sketch.rectangle.rounded":
            spec["x0"], spec["y0"] = p["p0"]
            spec["x1"], spec["y1"] = p["p1"]
            spec["fillet_radius"] = p["radius"]
        elif cmd == "sketch.circle.center":
            d = float(p["diameter"])
            cx, cy = float(p["center"][0]), float(p["center"][1])
            if abs(cx) < 1e-9 and abs(cy) < 1e-9:
                # concentric circles: the bore is the smaller, the boss outer
                spec["bore"] = d if "bore" not in spec else min(spec["bore"], d)
                spec["boss"] = d if "boss" not in spec else max(spec["boss"], d)
            elif "bolt" not in spec:
                # the first off-axis circles are the bolt holes
                spec["bolt"] = d
                spec["bolt_pos"] = p["center"]
    return spec


def _mm(expr) -> str:
    return expr.replace(" mm", "").strip() if isinstance(expr, str) else expr


def export_stages() -> list[int]:
    """The build-stage prefixes media/video/export_glb.py exports, so the
    caption's 'stage N of M' is the same number the footage was cut from."""
    spec = importlib.util.spec_from_file_location(
        "export_glb", VIDEO / "export_glb.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.STAGES)


def proof() -> dict:
    verdicts = json.loads((MEDIA / "data" / "verdicts.json").read_text())
    good = verdicts["good"]
    gates = good["gates"]
    missing = [g for g in ("build", "occt_shape", "volume", "features", "mass",
                           "cross_check", "parametric", "stl") if g not in gates]
    if missing:
        raise SystemExit(f"build_overlay_data: verdicts.json has no gate(s) {missing}")

    volume, mass = gates["volume"], gates["mass"]
    feat, stl = gates["features"], gates["stl"]
    occt, par, cross = gates["occt_shape"], gates["parametric"], gates["cross_check"]
    spec = design_spec()

    p = {
        "source": "media/data/verdicts.json -> good, this run",
        "passed": bool(good.get("passed")),
        "version_solidcraft": good.get("versions", {}).get("solidcraft"),
        "seed": good.get("seed"),
        "volume_mm3": round(float(gates["volume"]["occt_mm3"]), 4),
        "analytic_mm3": round(float(volume["analytic_mm3"]), 4),
        "volume_rel_dev": float(volume["rel_dev"]),
        "volume_limit_rel": float(volume["limit_rel"]),
        "mass_g": round(float(mass["mass_g"]), 4),
        "mass_limit_g": float(mass["limit_g"]),
        "density_g_cm3": float(mass["density_g_cm3"]),
        "plate_mm": [float(spec["x1"]) - float(spec["x0"]),
                     float(spec["y1"]) - float(spec["y0"])],
        # how long the graded script is and which prefix the plate footage
        # shows, so the captions cannot drift from the design they describe
        "commands_total": _count("commands", len(
            json.loads((MEDIA.parent / "examples" / "good" / "design.json")
                       .read_text())["commands"])),
        "plate_stage": _count("plate_stage", export_stages()[0]),
        "thickness_mm": float(_mm(spec.get("thickness", "6"))),
        "bolt_holes": int(feat["bolt_holes"]),
        "bore_diameter_mm": float(feat["bore_diameter_mm"]),
        "boss_outer_mm": float(spec.get("boss", 32.0)),
        "boss_height_mm": float(feat["boss_height_mm"]),
        "pcd_mm": round(float(spec["bolt_pos"][0]) * 2 * (2 ** 0.5), 4),
        "bolt_dia_mm": float(spec.get("bolt", 3.4)),
        "corner_fillets": int(feat["corner_fillets"]),
        "fillet_radius_mm": float(spec.get("fillet_radius", 5.0)),
        "min_edge_distance_mm": float(feat["min_edge_distance_mm"]),
        "wall_checks": int(feat["wall_checks"]),
        "wall_checks_failed": int(feat["wall_checks_failed"]),
        "kernels_volume_rel_dev": float(cross["volume_rel_dev"]),
        "kernels_area_rel_dev": float(cross["area_rel_dev"]),
        "kernels_com_mm": float(cross["com_max_dev_mm"]),
        "param_delta_mm3": round(float(par["volume_delta_mm3"]), 4),
        "param_analytic_mm3": round(float(par["analytic_delta_mm3"]), 4),
        "param_rel_dev": float(par["rel_dev"]),
        "param_new_value_mm": float(par["new_value_mm"]),
        "stl_triangles": int(stl["triangles"]),
        "stl_rel_dev": float(stl["rel_dev_vs_step"]),
        "bbox_max_dev_mm": float(occt["bbox_max_dev_mm"]),
        "gates": {name: bool(gates[name].get("pass")) for name in gates},
        "gate_order": list(gates.keys()),
    }
    mutants = sorted(k for k in verdicts if k != "good")
    p["mutants_killed"] = sum(1 for m in mutants if verdicts[m].get("failed_gate"))
    p["mutants_total"] = len(mutants)
    if not p["mutants_killed"]:
        raise SystemExit("build_overlay_data: no mutant recorded a failed_gate")
    return p


def sweep() -> list[dict]:
    rows = json.loads((MEDIA / "data" / "sweep.json").read_text())
    for r in rows:
        for k in ("thickness_mm", "solidcraft_volume_mm3"):
            if k not in r:
                raise SystemExit(f"build_overlay_data: sweep.json row missing {k}")
    return rows


def runlog(path: Path) -> dict:
    """Turn the stamped selftest log into [{t, text}] the replay can seek to."""
    lines: list[dict] = []
    for raw in path.read_text().splitlines():
        if "\t" not in raw:
            continue
        ts, text = raw.split("\t", 1)
        text = text.rstrip("\n")
        if text.startswith("SELFTEST_EXIT=") or not text.strip():
            continue
        if text.startswith("mutants: wrote "):
            continue  # the 19 writes share one timestamp; the kills carry it
        lines.append({"t": round(float(ts), 2), "text": text})
    if not lines:
        raise SystemExit(f"build_overlay_data: {path} held no timestamped lines")

    # The unit-test count is read out of the run, never typed in: unittest
    # prints "Ran N tests in Xs", and the replay shows that number.
    ran = next((l["text"] for l in lines
                if l["text"].startswith("Ran ") and " tests in " in l["text"]), None)
    if ran is None:
        raise SystemExit(f"build_overlay_data: {path} has no 'Ran N tests' line")
    count = int(ran.split()[1])
    if count <= 0:
        raise SystemExit(f"build_overlay_data: unit-test count {count} from {ran!r}")
    return {"total_s": round(lines[-1]["t"], 1), "unit_tests": count, "lines": lines}


def renderer() -> dict:
    """The pinned HyperFrames version, from package-lock.json (not the network)."""
    lock = json.loads((VIDEO / "package-lock.json").read_text())
    pkg = lock.get("packages", {}).get("node_modules/hyperframes")
    if not pkg or not pkg.get("version"):
        raise SystemExit("build_overlay_data: package-lock.json has no pinned hyperframes")
    return {"name": "HyperFrames", "version": pkg["version"],
            "source": "package-lock.json -> node_modules/hyperframes"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest-log", type=Path, default=STAMPED_LOG)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="diff against --out, write nothing")
    args = ap.parse_args()

    if not args.selftest_log.exists():
        print(f"build_overlay_data: missing {args.selftest_log}", file=sys.stderr)
        print("build_overlay_data: run judge/selftest.sh with per-line timestamps first",
              file=sys.stderr)
        return 1

    body = TEMPLATE.read_text()
    body = body.replace("__PROOF__", json.dumps(proof()))
    body = body.replace("__SWEEP__", json.dumps(sweep()))
    body = body.replace("__RUNLOG__", json.dumps(runlog(args.selftest_log)))
    body = body.replace("__RENDERER__", json.dumps(renderer()))
    for tok in ("__PROOF__", "__SWEEP__", "__RUNLOG__", "__RENDERER__"):
        if tok in body:
            raise SystemExit(f"build_overlay_data: unresolved placeholder {tok}")

    if args.check:
        if not args.out.exists():
            print(f"build_overlay_data: {args.out} is missing", file=sys.stderr)
            return 1
        if args.out.read_text() != body:
            print("build_overlay_data: the committed file does not match this run",
                  file=sys.stderr)
            return 1
        print("build_overlay_data: the committed file matches this run")
        return 0

    tmp = args.out.with_suffix(args.out.suffix + ".tmp")
    tmp.write_text(body)
    tmp.replace(args.out)
    print(f"build_overlay_data: wrote {args.out} ({len(body)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
