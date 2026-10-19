#!/usr/bin/env python3
"""Actually train the velocity-reward-sign mutant, never fake its weights."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

DEMO = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", type=Path, default=DEMO / "out/reward-flipped")
    a = ap.parse_args()
    a.outdir.mkdir(parents=True, exist_ok=True)
    config = json.loads((DEMO / "examples/good/train_config.json").read_text())
    config["reward"]["track_lin"] *= -1
    path = a.outdir / "config.json"
    path.write_text(json.dumps(config, indent=2) + "\n")
    command = [sys.executable, str(DEMO / "run.py"), "--config", str(path),
               "--no-selftest", "--outdir", str(a.outdir)]
    process = subprocess.run(command, check=False)
    if process.returncode not in (0, 1) or not (a.outdir / "verdict.json").is_file():
        raise RuntimeError("reward-flipped training did not complete with a real verdict")
    verdict = json.loads((a.outdir / "verdict.json").read_text())
    timing = json.loads((a.outdir / "timing.json").read_text())
    if not timing.get("grade_completed"):
        raise RuntimeError("run did not reach grading; an old verdict cannot stand in")
    if verdict.get("error") or verdict["ok"]:
        raise RuntimeError("expected a simulated, failing reward-sign counterfactual")
    if not any(not g["pass"] for g in verdict["gates"].values()):
        raise RuntimeError("no numeric gate rejected the reward-sign mutant")
    print("reward-flipped: training completed; real judge rejected the checkpoint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
