#!/usr/bin/env python3
"""result.json — agent-next result manifest (schema agent-next/result@1)."""

import json
import os
import sys
import subprocess

MEDIA = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(MEDIA)

sys.path.insert(0, MEDIA)
from common import load_verdict

# Load the good verdict
good_v = load_verdict("good")

# Get the commit hash
try:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=DEMO, text=True
    ).strip()[:7]
except subprocess.CalledProcessError:
    commit = "unknown"

# Extract gate measurements
gates_data = []
for gate_name in ["validator", "oracle", "geometry", "recount"]:
    g = good_v["gates"][gate_name]
    if gate_name == "validator":
        measured = f"{g['validator_status']} (0 FAILURE)"
        threshold = "PASS, 0 FAILURE/ERROR"
    elif gate_name == "oracle":
        measured = f"{len(g['errors'])} errors"
        threshold = "0 errors"
    elif gate_name == "geometry":
        measured = f"bbox dev 0.0 cm"
        threshold = f"<= 1e-6 cm"
    else:  # recount
        measured = f"{len(g['errors'])} errors"
        threshold = "0 errors"
    gates_data.append({
        "name": f"gate {['validator','oracle','geometry','recount'].index(gate_name)+1} {gate_name}",
        "pass": g["passed"],
        "measured": measured,
        "threshold": threshold
    })

# Key numbers
numbers = [
    {"label": "NVIDIA validator status", "value": good_v["gates"]["validator"]["validator_status"], "unit": "", "source": "judge/grade.sh examples/good --json v.json"},
    {"label": "Oracle errors", "value": 0, "unit": "", "source": "judge/grade.sh examples/good --json v.json"},
    {"label": "Mesh normals/corners (Base/Body/Band)", "value": "24/24, 60/60, 40/40", "unit": "", "source": "judge/grade.sh examples/good --json v.json (facts.oracle.meshes)"},
    {"label": "Max |norm|-1 deviation", "value": "1.7e-08", "unit": "", "source": "judge/grade.sh examples/good --json v.json (facts.oracle.meshes.*.max_normal_dev)"},
    {"label": "Zero-area faces", "value": 0, "unit": "", "source": "judge/grade.sh examples/good --json v.json (facts.oracle.meshes.*.zero_area_faces)"},
    {"label": "Bound materials", "value": "3/3", "unit": "", "source": "judge/grade.sh examples/good --json v.json (facts.oracle.meshes.*.bound_material)"},
    {"label": "Colliders", "value": 1, "unit": "", "source": "judge/grade.sh examples/good --json v.json (facts.oracle.colliders)"},
    {"label": "metersPerUnit", "value": 0.01, "unit": "", "source": "judge/grade.sh examples/good --json v.json (facts.oracle.metersPerUnit)"},
    {"label": "upAxis", "value": "Y", "unit": "", "source": "judge/grade.sh examples/good --json v.json (facts.oracle.upAxis)"},
    {"label": "defaultPrim", "value": "TrafficCone", "unit": "", "source": "judge/grade.sh examples/good --json v.json (facts.oracle.defaultPrim)"},
    {"label": "Point counts (Base/Body/Band)", "value": "8/20/20", "unit": "", "source": "judge/grade.sh examples/good --json v.json (facts.geometry.*.points)"},
    {"label": "Bbox deviation", "value": "0.0", "unit": "cm", "source": "judge/grade.sh examples/good --json v.json (facts.geometry.*.bbox_dev_cm)"},
    {"label": "Self-test kill rate", "value": "100", "unit": "%", "source": "judge/selftest.sh (media/data/selftest_output.txt)"},
    {"label": "Determinism check", "value": "PASS", "unit": "", "source": "judge/selftest.sh --seed 1 twice"},
]

manifest = {
    "schema": "agent-next/result@1",
    "demo": "usd-validate-fix",
    "headline": "OpenUSD traffic-cone prop repaired: NVIDIA validator PASS, usd-core oracle 0 errors, geometry invariant — 12/12 mutants killed (100%)",
    "verdict": "PASS",
    "gates": gates_data,
    "numbers": numbers,
    "hero": {
        "kind": "image",
        "path": "media/result.png",
        "caption": "Before/after repair: broken asset (left) vs judge-passed fixed asset (right) with authored normals and all gates PASS"
    },
    "gallery": [
        {"kind": "image", "path": "media/loop.png", "caption": "Self-test: 12/12 mutants killed by gate, 100% kill rate vs 90% minimum"},
        {"kind": "video", "path": "media/demo.mp4", "poster": "media/result.png", "caption": "Repaired cone, gate HUD, mutant kill matrix, end card with launch command"}
    ],
    "launch": {
        "command": "python3 cookbook/usd-validate-fix/run.py",
        "ask_agent": "Set up a sandbox and solve the demo in cookbook/usd-validate-fix/ of https://github.com/agent-next/sandbox (clone it first). Run bash cookbook/usd-validate-fix/judge/setup.sh, read cookbook/usd-validate-fix/SPEC.md, then repair the asset yourself: start from cookbook/usd-validate-fix/task/traffic_cone_broken.usda and write a fixed .usda that keeps the three meshes at /TrafficCone/Base, /TrafficCone/Body and /TrafficCone/Band with their point arrays unchanged, and gives the stage metersPerUnit = 0.01, upAxis = \"Y\", defaultPrim = \"TrafficCone\", face-varying unit normals (one per face-corner), a correct extent per mesh, a material binding on every mesh (Band → the white plastic, others → the orange) and the physics collider kept. Iterate with bash cookbook/usd-validate-fix/judge/grade.sh <your-fixed.usda> --json v.json until it exits 0, then paste the final verdict JSON. Do not edit anything under judge/; if you believe the judge is wrong, say so instead of working around it. Kill the sandbox when you are done."
    },
    "receipt": "RECEIPT.md",
    "sandbox_commit": commit
}

with open(os.path.join(MEDIA, "result.json"), "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")

print("make_result_json: wrote media/result.json")
