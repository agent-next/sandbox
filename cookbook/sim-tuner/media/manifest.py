"""Trace every deliverable to its inputs and write the shared result card."""

import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent


def main():
    report = json.loads((HERE / "data/run-1.json").read_text())
    verdict = report["verdict"]
    kills = re.findall(r"selftest: mutant (\S+): killed", report["stages"]["selftest"]["stdout_tail"])
    assert len(kills) == len(set(kills)) == 18
    assert "selftest: kill rate: 18/18 = 100%" in report["stages"]["selftest"]["stdout_tail"]
    g3, g4 = verdict["gates"]["G3_heldout"], verdict["gates"]["G4_gpu_cpu_agree"]
    source = "media/data/run-1.json (python3 cookbook/sim-tuner/run.py --seed 7)"
    commit = json.loads((HERE / "data/provenance.json").read_text())["source_commit"]
    result = {
        "schema": "agent-next/result@1", "demo": "sim-tuner",
        "headline": f"Tuning cuts held-out error from {g3['default_err']} to {g3['heldout_err']}.",
        "verdict": verdict["verdict"],
        "gates": [
            {"name": "G1 ranges", "pass": verdict["gates"]["G1_ranges"]["pass"],
             "measured": "five finite in-range parameters", "threshold": "strict JSON, exact keys"},
            {"name": "G3 absolute error", "pass": g3["pass"],
             "measured": g3["heldout_err"], "threshold": f"< {g3['abs_threshold']}"},
            {"name": "G3 fraction of default", "pass": g3["pass"],
             "measured": g3["frac_of_default"], "threshold": f"< {g3['rel_threshold']}"},
            {"name": "G4 agreement", "pass": g4["pass"],
             "measured": f"abs {g4['abs_diff']}, rel {g4['rel_diff']}",
             "threshold": f"abs <= {g4['abs_tol']}, rel <= {g4['rel_tol']}"},
        ],
        "numbers": [
            {"label": "Held-out error", "value": g3["heldout_err"], "unit": "normalized RMS", "source": source},
            {"label": "Default error", "value": g3["default_err"], "unit": "normalized RMS", "source": source},
            {"label": "GPU train error", "value": g4["gpu_train_err"], "unit": "normalized RMS", "source": source},
            {"label": "CPU train error", "value": g4["cpu_train_err"], "unit": "normalized RMS", "source": source},
            {"label": "Mutant kill rate", "value": "18/18 = 100%", "unit": "", "source": source},
        ],
        "hero": {"kind": "image", "path": "media/result.png",
                 "caption": "Default, tuned and hidden truth: real graded MuJoCo states."},
        "gallery": [{"kind": "video", "path": "media/demo.mp4", "poster": "media/result.png"},
                    {"kind": "image", "path": "media/loop.png"}],
        "launch": {"command": "python3 cookbook/sim-tuner/run.py",
                   "ask_agent": "Fit the five rig parameters from six training recordings; grade on four held-out commands and require CPU/GPU agreement. See README.md."},
        "receipt": "RECEIPT.md", "sandbox_commit": commit,
    }
    (HERE / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    entries = {}
    for path in sorted(HERE.rglob("*")):
        if not path.is_file() or any(p.startswith(".") or p in ("master", "work", "__pycache__")
                                    for p in path.relative_to(HERE).parts):
            continue
        if path.name == "MANIFEST.json" or path.suffix in (".npz", ".xml"):
            continue
        entries[str(path.relative_to(HERE))] = {
            "shows": {"result.png": "Default, tuned and truth: graded box and arm states",
                      "loop.png": "Recorded CPU search and eighteen mutant gate failures",
                      "demo.mp4": "Synchronized real-time MuJoCo replay with judge HUD"}.get(path.name, path.stem),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "command": "bash cookbook/sim-tuner/media/make_media.sh" if path.suffix in (".png", ".mp4") else "See file / RECEIPT.md",
            "source": "data/run-1.json + data/replay.json + ../examples/good/loop.json",
        }
    manifest = {"source_commit": commit,
                "trajectory_note": "trajectories.npz is regenerated inside CPU grading; render-checks.json records frame checks",
                "files": entries}
    (HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
