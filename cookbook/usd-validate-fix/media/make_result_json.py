#!/usr/bin/env python3
"""result.json -- agent-next result manifest (schema agent-next/result@1).

Every gate, number and headline string below is read from
media/data/grade_good.json and media/data/selftest_output.txt, written by
judge/grade.sh and judge/selftest.sh in the same make_media.sh run. Nothing is
hardcoded: if the judge changes its mind, this file changes with it.
"""
import json
import os
import re
import subprocess
import sys

MEDIA = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(MEDIA)

sys.path.insert(0, MEDIA)
from common import GATE_ORDER, GATE_LABEL, load_verdict

SRC = "judge/grade.sh examples/good/traffic_cone_fixed.usda --seed 20261015"

# per-gate threshold text, from SPEC.md; measured side is computed below.
THRESHOLD = {"validator": "PASS, 0 FAILURE/ERROR issues",
             "oracle": "0 errors",
             "geometry": "world bbox dev <= 1e-6 cm",
             "up_axis": "measured height axis == upAxis, margin >= 5 cm",
             "recount": "0 errors (text recount agrees with pxr)"}


def measured(good):
    """The measured string for each gate, from the verdict itself."""
    g = good["gates"]
    out = {}
    v = g["validator"]
    out["validator"] = "%s, %d FAILURE / %d ERROR" % (
        v["validator_status"],
        v["issues_by_severity"].get("FAILURE", 0),
        v["issues_by_severity"].get("ERROR", 0))
    out["oracle"] = "%d errors" % len(g["oracle"]["errors"])
    dev = max(f["bbox_dev_cm"] for f in good["facts"]["geometry"].values())
    out["geometry"] = "world bbox dev %.1e cm" % dev
    up = good["facts"]["up_axis"]
    out["up_axis"] = ("upAxis %s == measured height axis %s, margin %.0f cm"
                      % (up["upAxis"], up["height_axis"],
                         up["height_margin_cm"]))
    out["recount"] = "%d errors" % len(g["recount"]["errors"])
    return out


def selftest():
    """(killed, total, pct, det_ok, exit_ok) from the selftest log."""
    with open(os.path.join(MEDIA, "data", "selftest_output.txt"),
              encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"kill rate (\d+)/(\d+) = (\d+)%", text)
    if not m:
        raise SystemExit("selftest_output.txt has no kill-rate line")
    det = "determinism OK" in text and "DETERMINISM FAILED" not in text
    ok = re.search(r"^selftest: OK$", text, re.M) is not None
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), det, ok


def main():
    good = load_verdict("good")
    killed, total, rate_pct, det_ok, exit_ok = selftest()
    meas = measured(good)
    up = good["facts"]["up_axis"]

    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=DEMO, text=True).strip()
    except (subprocess.CalledProcessError, OSError):
        raise SystemExit("result.json: cannot resolve the demo's git commit")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise SystemExit("result.json: %r is not a commit sha" % commit)

    gates = [{"name": "gate %d %s" % (i + 1, key),
              "pass": good["gates"][key]["passed"],
              "measured": meas[key],
              "threshold": THRESHOLD[key]}
             for i, key in enumerate(GATE_ORDER)]

    meshes = good["facts"]["oracle"]["meshes"]
    order = ["/TrafficCone/Base", "/TrafficCone/Body", "/TrafficCone/Band"]
    order = [p for p in order if p in meshes] + \
            [p for p in sorted(meshes) if p not in order]
    norm = "/".join("%d/%d" % (m["normals"], m["face_corners"])
                    for m in (meshes[p] for p in order))
    pts = "/".join(str(good["facts"]["geometry"][p]["points"])
                   for p in order if p in good["facts"]["geometry"])

    numbers = [
        {"label": "NVIDIA validator status", "value": meas["validator"],
         "unit": "", "source": SRC},
        {"label": "Oracle errors", "value": len(good["gates"]["oracle"]
                                                ["errors"]),
         "unit": "", "source": SRC},
        {"label": "Mesh normals/corners (%s)"
                  % "/".join(p.rsplit("/", 1)[-1] for p in order),
         "value": norm, "unit": "", "source": SRC + " (facts.oracle.meshes)"},
        {"label": "Max |norm|-1 deviation",
         "value": "%.1e" % max(m["max_normal_dev"]
                               for m in meshes.values()),
         "unit": "", "source": SRC + " (facts.oracle.meshes)"},
        {"label": "Zero-area faces",
         "value": sum(m["zero_area_faces"] for m in meshes.values()),
         "unit": "", "source": SRC + " (facts.oracle.meshes)"},
        {"label": "Bound materials",
         "value": "%d/%d" % (sum(1 for m in meshes.values()
                                 if m.get("bound_material")), len(meshes)),
         "unit": "", "source": SRC + " (facts.oracle.meshes)"},
        {"label": "Colliders", "value": good["facts"]["oracle"]["colliders"],
         "unit": "", "source": SRC + " (facts.oracle.colliders)"},
        {"label": "metersPerUnit", "value": good["facts"]["oracle"]
         ["metersPerUnit"], "unit": "", "source": SRC + " (facts.oracle)"},
        {"label": "upAxis", "value": good["facts"]["oracle"]["upAxis"],
         "unit": "", "source": SRC + " (facts.oracle)"},
        {"label": "Measured height axis",
         "value": "%s (margin %.0f cm)"
                  % (up["height_axis"], up["height_margin_cm"]),
         "unit": "", "source": SRC + " (facts.up_axis)"},
        {"label": "defaultPrim", "value": good["facts"]["oracle"]
         ["defaultPrim"], "unit": "", "source": SRC + " (facts.oracle)"},
        {"label": "Point counts (%s)"
                  % "/".join(p.rsplit("/", 1)[-1] for p in order),
         "value": pts, "unit": "",
         "source": SRC + " (facts.geometry)"},
        {"label": "World bbox deviation",
         "value": "%.1e" % max(f["bbox_dev_cm"] for f
                               in good["facts"]["geometry"].values()),
         "unit": "cm", "source": SRC + " (facts.geometry)"},
        {"label": "Self-test kill rate", "value": rate_pct, "unit": "%",
         "source": "judge/selftest.sh (media/data/selftest_output.txt)"},
        {"label": "Mutants killed", "value": "%d/%d" % (killed, total),
         "unit": "", "source": "judge/selftest.sh"},
        {"label": "Determinism (--seed 1 twice)",
         "value": "PASS" if det_ok else "FAIL", "unit": "",
         "source": "judge/selftest.sh (media/data/selftest_output.txt)"},
    ]

    headline = ("OpenUSD traffic-cone prop repaired: NVIDIA validator %s, "
                "usd-core oracle %d errors, geometry invariant, upAxis %s "
                "matches the measured %s height axis -- %d/%d mutants "
                "killed (%d%%)"
                % (good["gates"]["validator"]["validator_status"],
                  len(good["gates"]["oracle"]["errors"]),
                  up["upAxis"], up["height_axis"], killed, total, rate_pct))

    manifest = {
        "schema": "agent-next/result@1",
        "demo": "usd-validate-fix",
        "headline": headline,
        "verdict": "PASS" if good["passed"] else "FAIL",
        "gates": gates,
        "numbers": numbers,
        "hero": {
            "kind": "compare",
            "before": "media/result.png",
            "after": "media/result.png",
            "caption": "Before/after repair: the broken asset (left, gray "
                       "Band, no normals) beside the judge-passed fixed "
                       "asset (right) with authored face-varying normals; "
                       "all %d gates PASS" % len(GATE_ORDER),
        },
        "gallery": [
            {"kind": "image", "path": "media/loop.png",
             "caption": "Self-test: %d/%d mutants killed by a named judge "
                        "gate (%d%% kill rate vs 90%% minimum)"
                        % (killed, total, rate_pct)},
            {"kind": "video", "path": "media/demo.mp4",
             "poster": "media/result.png",
             "caption": "Repaired cone, the five gate verdicts, the mutant "
                        "kill matrix, end card with the launch command"},
        ],
        "launch": {
            "command": "python3 cookbook/usd-validate-fix/run.py",
            "ask_agent": (
                "Set up a sandbox and solve the demo in "
                "cookbook/usd-validate-fix/ of "
                "https://github.com/agent-next/sandbox (clone it first). Run "
                "bash cookbook/usd-validate-fix/judge/setup.sh, read "
                "cookbook/usd-validate-fix/SPEC.md, then repair the asset "
                "yourself: start from "
                "cookbook/usd-validate-fix/task/traffic_cone_broken.usda and "
                "write a fixed .usda that keeps the three meshes at "
                "/TrafficCone/Base, /TrafficCone/Body and /TrafficCone/Band "
                "with their point arrays unchanged, and gives the stage "
                "metersPerUnit = 0.01, upAxis = \"Y\", defaultPrim = "
                "\"TrafficCone\", face-varying unit normals (one per "
                "face-corner), a correct extent per mesh, a material binding "
                "on every mesh (Band -> the white plastic, others -> the "
                "orange) and the physics collider kept. Iterate with bash "
                "cookbook/usd-validate-fix/judge/grade.sh <your-fixed.usda> "
                "--json v.json until it exits 0, then paste the final verdict "
                "JSON. Do not edit anything under judge/; if you believe the "
                "judge is wrong, say so instead of working around it. Kill "
                "the sandbox when you are done."),
        },
        "receipt": "RECEIPT.md",
        "sandbox_commit": commit,
    }

    if manifest["verdict"] == "FAIL":
        raise SystemExit("result.json: the good artifact fails the judge -- "
                         "verdict FAIL, refusing to write a PASS manifest")

    with open(os.path.join(MEDIA, "result.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    print("make_result_json: wrote media/result.json (verdict %s, %s)"
          % (manifest["verdict"], headline[:40] + "..."))


if __name__ == "__main__":
    main()
