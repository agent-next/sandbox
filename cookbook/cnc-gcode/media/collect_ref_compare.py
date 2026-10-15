#!/usr/bin/env python3
"""Dump the reference cross-check comparison table for the result figure.

Runs the judge's own two interpreters on the good example's part.nc:

  * the judge's parser (judge/gcode_sim.py parse_gcode + reference.sim_stats)
  * LinuxCNC's standalone rs274 interpreter (judge/reference.py run)

and writes media/data/ref_compare.json with both sides' canonical move list
statistics and the per-item differences the judge's `reference` gate checks
(same convention both sides: endpoints + arc centres for the bbox).

Every number in the output is measured by the judge's own code; nothing is
synthesised here.  make_media.sh fails if this file is missing.

Usage (from cookbook/cnc-gcode/, with the judge venv on sys.path):
    bash media/collect_ref_compare.sh
"""
import json
import os
import sys

DEMO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(DEMO, "media")
DATA = os.path.join(MEDIA, "data")
sys.path.insert(0, os.path.join(DEMO, "judge"))   # the judge's own modules

import gcode_sim as gs
import reference as ref


def main():
    # the exact program the good grade run graded: re-run cam.py the same way
    # grade.sh does, then take the emitted part.nc (never the CAM script's
    # own idea of the path).
    import subprocess
    import tempfile

    work = tempfile.mkdtemp(prefix="refcmp")
    with open(os.path.join(work, "cam.py"), "w") as fh:
        fh.write(open(os.path.join(DEMO, "examples/good/cam.py")).read())
    with open(os.path.join(work, "spec.json"), "w") as fh:
        fh.write(open(os.path.join(DEMO, "spec.json")).read())
    subprocess.run(
        [sys.executable, "cam.py", "--spec", "spec.json", "--out", "part.nc"],
        cwd=work, check=True, timeout=120)
    with open(os.path.join(work, "part.nc")) as fh:
        nc_text = fh.read()

    with open(os.path.join(DEMO, "spec.json")) as fh:
        spec = json.load(fh)

    # judge side: the same parser + the same stats the reference gate uses
    moves, _info = gs.parse_gcode(
        nc_text, spec["machine"]["start_xy_mm"], spec["machine"]["safe_z_mm"])
    ours = ref.sim_stats(moves)

    # reference side: LinuxCNC rs274's own canonical output
    theirs = ref.run(nc_text)

    gate = json.load(open(os.path.join(DATA, "replay/01_good.json")))
    g = gate["gates"]["reference"]

    # cross-check the two sides against what the gate reported, so the figure
    # can never drift from the graded verdict
    diffs = {
        "feeds": theirs["feeds"] - ours["feeds"],
        "rapids": theirs["rapids"] - ours["rapids"],
        "arcs": theirs["arcs"] - ours["arcs"],
        "z_max_mm": theirs["z_max"] - ours["z_max"],
        "z_min_mm": theirs["z_min"] - ours["z_min"],
        "bbox_mm": [round(theirs["bbox"][k] - ours["bbox"][k], 6)
                    for k in range(4)],
    }
    for k, v in diffs.items():
        if k.endswith("_mm") or k == "bbox_mm":
            continue
        assert v == g[f"{k}_diff"], (k, v, g)
    assert abs(diffs["z_max_mm"] - g["z_max_diff_mm"]) < 1e-9
    assert abs(diffs["z_min_mm"] - g["z_min_diff_mm"]) < 1e-9
    assert diffs["bbox_mm"] == g["bbox_diff_mm"]

    out = {
        "ours": ours,
        "rs274": theirs,
        "diffs": diffs,
        "tolerance_mm": g["tolerance_mm"],
        "ref_tool": g["ref_tool"],
        "gate_pass": g["pass"],
    }
    with open(os.path.join(DATA, "ref_compare.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"ref_compare: wrote {DATA}/ref_compare.json "
          f"(feeds {ours['feeds']} vs {theirs['feeds']}, "
          f"arcs {ours['arcs']} vs {theirs['arcs']})")


if __name__ == "__main__":
    main()
