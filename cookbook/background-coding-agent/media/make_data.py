#!/usr/bin/env python3
"""Media data extraction for the background-coding-agent demo.

Writes media/data/*.json by driving the judge directly (imported, not
duplicated): the known-good verdict, the scripted agent-loop replay
verdicts, the per-mutant kill results and a per-field oracle comparison
of the delivered --json output against judge/reference.py.  Every plotted
number comes from a judge output -- nothing is invented here.

Usage: make_data.py <demodir> <workdir>
  <demodir>  path to cookbook/background-coding-agent (media/ inside)
  <workdir>  scratch dir holding good.json, the replay sequence JSONs
             (<name>.json) and mutants/ -- graded by make_media.sh
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

demodir = Path(sys.argv[1])
work = Path(sys.argv[2])
outdir = demodir / "media" / "data"
outdir.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(demodir / "judge"))
import grade_engine as G  # noqa: E402
import reference  # noqa: E402

GATE_ORDER = ["patch", "integrity", "regression", "acceptance",
              "lint", "oracle", "pr"]

# The scripted replay: one iteration per gate, in the order the judge
# runs them, ending at the known-good delivery.  A fixing agent meets
# the gates in exactly this order -- it is a scripted replay, not a
# recorded live trace.
REPLAY = ["empty-patch", "touches-tests", "breaks-old-test",
          "json-missing-field", "lint-unused-import", "mean-sign-dropped",
          "pr-no-test-plan", "good"]


def distill(name: str, verdict: dict) -> dict:
    """Keep the figure-relevant fields; drop machine-local paths."""
    gates = verdict.get("gates", {})
    return {
        "label": name,
        "passed": verdict.get("passed", False),
        "failed_gate": verdict.get("failed_gate", "-"),
        "reason": verdict.get("reason", "")[:160],
        "gates_passed": sum(1 for g in GATE_ORDER if g in gates),
        "gates": gates,
    }


# --- the known-good verdict --------------------------------------------
good = json.loads((work / "good.json").read_text())
(outdir / "verdict_good.json").write_text(json.dumps(good, indent=1))

# --- replay + selftest: distilled verdicts ------------------------------
replay = [distill(n, json.loads((work / f"{n}.json").read_text()))
          for n in REPLAY]
(outdir / "replay.json").write_text(json.dumps(replay, indent=1))

kills = []
for mdir in sorted((work / "mutants").iterdir()):
    name = mdir.name
    v = json.loads((work / f"{name}.json").read_text())
    kills.append(distill(name, v))
kill_rate = sum(1 for k in kills if not k["passed"]) / len(kills)
(outdir / "selftest.json").write_text(json.dumps(
    {"kills": kills, "kill_rate": kill_rate, "mutants": len(kills)},
    indent=1))

# --- oracle detail: delivered --json vs judge/reference.py --------------
# Build the patched checkout exactly as the engine does (its own helpers),
# run the delivered CLI on the three oracle inputs and record the relative
# error of every numeric field against the independent reference.
patch = demodir / "examples" / "good" / "delivery.patch"
text = patch.read_text()
info = G.parse_patch(text)
oracle = {"tolerance_rel": G.REL_TOL, "seed": G.SEED_DEFAULT, "inputs": []}

tmp = Path(tempfile.mkdtemp(prefix="bca-media-"))
try:
    root = tmp / "fixture"
    shutil.copytree(G.FIXTURE, root,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    patch_file = tmp / "delivery.patch"
    patch_file.write_text(G.reroot_patch(text, info.files))
    applied = subprocess.run(["git", "apply", "-p1", str(patch_file)],
                             cwd=str(root), capture_output=True, text=True)
    assert applied.returncode == 0, applied.stderr

    cases = [("sample.csv", root / "data" / "sample.csv")]
    for name, body in G.synth_inputs(G.SEED_DEFAULT):
        path = tmp / name
        path.write_text(body)
        cases.append((name, path))

    for name, path in cases:
        want = reference.summarise_text(path.read_text())
        proc = subprocess.run(
            [sys.executable, "-m", "measurectl", "--json", str(path)],
            capture_output=True, text=True, cwd=str(root),
            env=G.child_env(root), timeout=G.CLI_TIMEOUT)
        assert proc.returncode == 0, proc.stderr
        got = json.loads(proc.stdout)
        fields = []
        for entry, expect in zip(got["metrics"], want["metrics"]):
            assert entry["name"] == expect["name"]
            per_field = {}
            for field in ("sum", "mean", "min", "max"):
                a, b = float(entry[field]), float(expect[field])
                per_field[field] = abs(a - b) / max(1.0, abs(b))
            fields.append({"metric": entry["name"],
                           "count": entry["count"],
                           "min": entry["min"], "mean": entry["mean"],
                           "max": entry["max"],
                           "rel_error": per_field,
                           "max_rel_error": max(per_field.values())})
        oracle["inputs"].append({
            "input": name,
            "metrics": len(fields),
            "total_count": got["total_count"],
            "fields": fields,
            "max_rel_error": max(f["max_rel_error"] for f in fields),
        })
finally:
    shutil.rmtree(tmp, ignore_errors=True)
(outdir / "oracle_detail.json").write_text(json.dumps(oracle, indent=1))

print(f"make_data: wrote verdict_good.json, replay.json, selftest.json, "
      f"oracle_detail.json to {outdir} (kill rate {kill_rate:.0%})")
