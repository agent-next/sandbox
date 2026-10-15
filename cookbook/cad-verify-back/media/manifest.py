#!/usr/bin/env python3
"""MANIFEST.json: sha256, what-it-shows, source data and command per file."""
import hashlib
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_tip():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=os.path.dirname(HERE),
            text=True).strip()
    except Exception:
        return "unknown"


def main():
    tip = git_tip()
    files = {
        "result.png": {
            "shows": "the delivered part (examples/good STL parsed with "
                     "trimesh 5.1.1) beside the spec-built reference solid "
                     "with the manifold3d XOR difference, the DXF bolt-circle "
                     "overlay with angular deviations vs the G6 tolerance, "
                     "and per-gate measured errors vs pass limits",
            "command": "bash media/make_media.sh figs  (fig_result.py)",
            "source_data": ["data/verdicts/good.json",
                            "examples/good/part.stl",
                            "examples/good/part.dxf",
                            "judge/spec.json"],
        },
        "loop.png": {
            "shows": "the fixing-agent loop replay (gates passing per "
                     "iteration with the 14/14 pass line) and the mutant x "
                     "gate matrix (known-good + 10 mutants x 14 gates) with "
                     "red cells showing measured vs limit",
            "command": "bash media/make_media.sh figs  (fig_loop.py)",
            "source_data": ["data/replay/iter1_scale_inch_mm.json",
                            "data/replay/iter2_boss_missing.json",
                            "data/replay/iter3_tangential_hole_drift.json",
                            "data/replay/iter4_good.json"]
                           + [f"data/verdicts/{n}.json" for n in
                              ["good", "wrong_bolt_count", "wrong_pcd",
                               "bore_off", "boss_missing", "scale_inch_mm",
                               "stl_flipped_facet", "stl_not_watertight",
                               "dxf_missing_hole", "edge_violation",
                               "tangential_hole_drift"]]
                           + ["data/selftest.log"],
        },
        "demo.mp4": {
            "shows": "storyboarded to media/STORYBOARD.md: a full-frame "
                     "turntable of the real delivered STL rendered offscreen "
                     "by VTK, a push-in on the bolt circle, then full-frame "
                     "cards of result.png and loop.png (per-gate verdict vs "
                     "the spec; the agent loop and the mutant x gate kill "
                     "matrix), and the static end card (34.7 s, 1920x1080, "
                     "30 fps, H.264)",
            "command": "bash media/make_media.sh video  (video.py + ffmpeg)",
            "source_data": ["data/verdicts/*.json", "data/replay/iter*.json",
                            "data/selftest.log",
                            "examples/good/part.stl"],
        },
    }
    out = {"git_tip": tip,
           "data_stage": "bash media/make_media.sh data (judge/grade.sh on "
                        "examples/good, the 10 judge/mutants.py mutants and "
                        "the replay artifacts, all with --json; plus "
                        "judge/selftest.sh)"}
    manifest = {}
    for name, meta in files.items():
        p = os.path.join(HERE, name)
        if not os.path.isfile(p):
            raise SystemExit(f"manifest: {name} not built yet")
        manifest[name] = {**meta, "sha256": sha256(p),
                          "bytes": os.path.getsize(p)}
    out["files"] = manifest
    with open(os.path.join(HERE, "MANIFEST.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("MANIFEST.json written:",
          ", ".join(f"{k}={v['sha256'][:12]}" for k, v in manifest.items()))


if __name__ == "__main__":
    main()
