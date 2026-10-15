#!/usr/bin/env python3
"""Collect the judge outputs the figures and the video are drawn from.

    make_data.py <demo_dir> <workdir>

Writes media/data/*.json. Every number here comes from running the judge
(main) on the committed artifact and on the single-edit mutants; nothing is
hand-entered. Needs ffmpeg/whisper-cli on PATH as judge/setup.sh installs
them, plus the media venv for nothing at all -- this script is stdlib-only
so it can reuse the judge's own decoder.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_judge(demo: Path):
    spec = importlib.util.spec_from_file_location(
        "vtp_judge", demo / "judge" / "vtp_judge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def grade(demo: Path, artifact: Path, workdir: Path, seed: int = 0) -> dict:
    out = workdir / f"verdict-{artifact.parent.name}.json"
    proc = subprocess.run(
        ["bash", str(demo / "judge" / "grade.sh"), str(artifact),
         "--seed", str(seed), "--json", str(out)],
        capture_output=True, text=True)
    if not out.is_file():
        raise SystemExit(f"grade.sh produced no verdict for {artifact}:\n"
                         f"{proc.stdout[-800:]}{proc.stderr[-800:]}")
    return json.loads(out.read_text())


def counter_series(judge, demo: Path, workdir: Path) -> dict:
    """Decode the burned counter from the good renditions, frame by frame."""
    verdict = grade(demo, demo / "examples" / "good", workdir)
    if not verdict["passed"]:
        raise SystemExit("the known-good artifact did not pass; fix that first")

    run_dir = workdir / "series"
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(demo / "examples" / "good" / "pipeline.sh", run_dir / "pipeline.sh")
    shutil.copytree(demo / "fixtures", run_dir / "fixtures", dirs_exist_ok=True)
    out = run_dir / "out"
    subprocess.run(["bash", str(run_dir / "pipeline.sh"),
                    "--input", str(demo / "fixtures" / "source.mp4"),
                    "--out", str(out), "--seed", "0"], check=True,
                   capture_output=True, cwd=run_dir)

    tpl = judge.templates(demo / "fixtures", workdir)
    series: dict = {"tolerance": judge.COUNTER_TOL, "renditions": {}}
    for name, (w, h) in judge.RENDITIONS.items():
        frames = judge.counter_frames(judge.concat_arg(out, name), w, h)
        idx, decoded = [], []
        for i in range(1, len(frames), 12):
            try:
                value = int(judge.read_counter(
                    judge.binarize(frames[i], w, h), tpl)[0])
            except ValueError:
                value = None
            idx.append(i)
            decoded.append(value)
        series["renditions"][name] = {
            "frames": len(frames), "index": idx, "decoded": decoded,
            "expected": idx, "matched": sum(1 for a, b in zip(idx, decoded) if a == b),
            "samples": len(idx)}
    return series


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    demo, workdir = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    data = HERE / "data"
    data.mkdir(parents=True, exist_ok=True)
    judge = load_judge(demo)

    good = grade(demo, demo / "examples" / "good", workdir)
    (data / "good.json").write_text(json.dumps(good, indent=2) + "\n")
    print(f"data: good verdict passed={good['passed']}")

    mutants_dir = workdir / "mutants"
    proc = subprocess.run(["python3", "-I", str(demo / "judge" / "mutants.py"),
                           str(mutants_dir)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr or proc.stdout)

    mutants = []
    for path in sorted(mutants_dir.iterdir()):
        verdict = grade(demo, path, workdir)
        mutants.append({
            "name": path.name,
            "description": verdict.get("reason", "")[:200],
            "failed_gate": verdict.get("failed_gate"),
            "passed": verdict["passed"],
            "gates": {k: v.get("passed") for k, v in verdict["gates"].items()},
        })
        print(f"data: mutant {path.name:20s} passed={verdict['passed']} "
              f"gate={verdict.get('failed_gate')}")
    killed = sum(1 for m in mutants if not m["passed"])
    (data / "mutants.json").write_text(json.dumps({
        "mutants": mutants, "total": len(mutants), "killed": killed,
        "kill_rate": killed / len(mutants) if mutants else 0.0}, indent=2) + "\n")

    # A scripted replay in the order a fixing agent would meet the failures:
    # a wrong rendition size, then a truncated stream, then a playlist that
    # drops a segment, then the wrong keyframe grid, then the finished
    # pipeline. Real verdicts, not a recorded trace.
    order = ["wrong-resolution", "truncated", "dropped-segment",
             "wrong-keyframe", None]
    replay = []
    for i, name in enumerate(order):
        if name is None:
            verdict, label = good, "examples/good (fixed)"
        else:
            verdict = grade(demo, mutants_dir / name, workdir)
            label = name
        replay.append({
            "iteration": i + 1, "artifact": label, "passed": verdict["passed"],
            "failed_gate": verdict.get("failed_gate"),
            "gates": {k: bool(v.get("passed")) for k, v in verdict["gates"].items()},
        })
        print(f"data: replay {i + 1} {label:28s} passed={verdict['passed']}")
    (data / "replay.json").write_text(json.dumps({"replay": replay}, indent=2) + "\n")

    series = counter_series(judge, demo, workdir)
    (data / "counter.json").write_text(json.dumps(series, indent=2) + "\n")
    print("data: counter series "
          + ", ".join(f"{k} {v['matched']}/{v['samples']}"
                      for k, v in series["renditions"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
