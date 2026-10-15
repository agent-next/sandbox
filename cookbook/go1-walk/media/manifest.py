"""Bind public media to real verdicts, source states, tools and hashes."""

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
COMMAND = os.environ.get("GO1_MEDIA_COMMAND", "bash cookbook/go1-walk/media/make_media.sh")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def result_card():
    verdict = json.loads((HERE / "data/trained.json").read_text())
    curve = json.loads((HERE.parent / "examples/good/curve.json").read_text())
    test = json.loads((HERE / "data/selftest.json").read_text())
    measured = verdict["measured"]
    source = COMMAND + " (seeds 101,202,303; data/trained.json)"
    numbers = [
        {"label": "Forward speed", "value": measured["mean_forward_mps"], "unit": "m/s", "source": source},
        {"label": "Falls", "value": measured["fall_rate"] * 100, "unit": "%", "source": source},
        {"label": "Torque saturation", "value": measured["max_sat_frac"] * 100, "unit": "%", "source": source},
        {"label": "PPO wall time", "value": curve["train_wall_s"], "unit": "s", "source": "RECEIPT.md: fresh training; examples/good/curve.json"},
        {"label": "PPO throughput", "value": curve["steps_per_s"], "unit": "env-steps/s", "source": "RECEIPT.md: fresh training; examples/good/curve.json"},
        {"label": "Mutant kill rate", "value": test["kill_rate"] * 100, "unit": "%", "source": COMMAND + " (data/selftest.json)"}]
    card = {
        "schema": "agent-next/result@1", "demo": "go1-walk",
        "headline": f"Go1 walks at {measured['mean_forward_mps']:.3f} m/s with {measured['fall_rate']:.1%} falls.",
        "verdict": "PASS" if verdict["ok"] else "FAIL",
        "gates": [{"name": name, "pass": row["pass"],
                   "measured": str(row["value"]).lower() if isinstance(row["value"], bool) else row["value"],
                   "threshold": row["rule"]} for name, row in verdict["gates"].items()],
        "numbers": numbers,
        "hero": {"kind": "video", "path": "media/demo.mp4", "poster": "media/result.png",
                 "caption": "Exact judge-scored MuJoCo trajectories, not a new simulation."},
        "gallery": [{"kind": "image", "path": "media/result.png"},
                    {"kind": "image", "path": "media/loop.png"}],
        "launch": {"command": "python3 cookbook/go1-walk/run.py",
                   "ask_agent": "Read cookbook/go1-walk/SPEC.md. Train the Go1 on a 4 GiB GPU lease, pass every independent judge gate and the mutation self-test, then delete the lease and confirm GET 404."},
        "receipt": "RECEIPT.md",
        "sandbox_commit": subprocess.check_output(
            ["git", "-C", str(HERE.parent), "rev-parse", "HEAD"], text=True).strip()}
    (HERE / "result.json").write_text(json.dumps(card, indent=2) + "\n")


def main():
    video = HERE / "demo.mp4"
    assert video.stat().st_size < 8_000_000, "web video must stay below 8 MB"
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(video)], text=True))
    stream = probe["streams"][0]
    assert (stream["codec_name"], stream["width"], stream["height"],
            stream["r_frame_rate"], stream["pix_fmt"]) == (
                "h264", 1920, 1080, "30/1", "yuv420p")
    assert 20 <= float(probe["format"]["duration"]) <= 60
    result_card()
    manifest = {
        "command": COMMAND,
        "tools": {n: importlib.metadata.version(n) for n in
                  ("mujoco", "numpy", "Pillow", "PyOpenGL")},
        "python": sys.version.split()[0],
        "ffmpeg": subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0],
        "render": json.loads((HERE / "data/render.json").read_text()),
        "video": {"codec": "h264", "fps": 30, "width": 1920, "height": 1080,
                  "duration_s": float(probe["format"]["duration"]),
                  "bytes": video.stat().st_size,
                  "master": "media/master/demo.mp4 (ignored, CRF 0)",
                  "web_encode": "-crf 18 -preset slow -tune animation -pix_fmt yuv420p -movflags +faststart"},
        "files": {}}
    inputs = ["env.py", "judge/_eval.py", "judge/grade.py", "judge/selftest.py",
              "judge/mutants.py", "model/go1_meshless.xml",
              "examples/good/policy.npz", "examples/good/step0.npz",
              "examples/good/short.npz", "examples/good/reward-flipped.npz",
              "examples/good/train_config.json", "examples/good/curve.json",
              "examples/good/loop.json", "media/collect.py", "media/render.py",
              "media/manifest.py", "media/make_media.sh", "media/requirements.lock",
              "media/STORYBOARD.md"]
    inputs.extend(f"media/data/{name}-{seed}.npz"
                  for name in ("trained", "untrained") for seed in (101, 202, 303))
    inputs.append("media/data/untrained-policy.npz")
    manifest["source_sha256"] = {name: sha(HERE.parent / name) for name in inputs}
    sources = {
        "result.png": ("Six real 3D states, trained versus untrained, with per-seed judge limits",
                       ["data/trained.json", "data/untrained.json", "data/*.npz"]),
        "loop.png": ("PPO reward curve, independently graded checkpoints, real mutation kills",
                     ["../examples/good/curve.json", "../examples/good/loop.json", "data/selftest.json"]),
        "demo.mp4": ("Three held-out episodes, trained versus untrained, exact-state 3D replay",
                     ["data/trained.json", "data/untrained.json", "data/*.npz"]),
        "result.json": ("Shared gallery/result-card numbers written from the real grade",
                        ["data/trained.json", "data/selftest.json", "../examples/good/curve.json"])}
    for name, (description, source) in sources.items():
        manifest["files"][name] = {"what": description, "command": COMMAND,
                                   "source_data": source, "sha256": sha(HERE / name)}
    for name in ("trained.json", "untrained.json", "selftest.json", "render.json"):
        manifest["files"][f"data/{name}"] = {"what": "Machine-produced evidence",
                                           "command": COMMAND,
                                           "sha256": sha(HERE / "data" / name)}
    (HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"media verified: {manifest['video']['duration_s']} s, {video.stat().st_size} bytes")


if __name__ == "__main__":
    main()
