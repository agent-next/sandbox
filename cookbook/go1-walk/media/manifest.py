"""Bind public media to real verdicts, source states, tools and hashes."""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
COMMAND = "bash cookbook/go1-walk/media/make_media.sh"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
                  "web_encode": "-crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart"},
        "files": {}}
    sources = {
        "result.png": ("Six real 3D states, trained versus untrained, with per-seed judge limits",
                       ["data/trained.json", "data/untrained.json", "data/*.npz"]),
        "loop.png": ("PPO reward curve, independently graded checkpoints, real mutation kills",
                     ["../examples/good/curve.json", "../examples/good/loop.json", "data/selftest.json"]),
        "demo.mp4": ("Three held-out episodes, trained versus untrained, exact-state 3D replay",
                     ["data/trained.json", "data/untrained.json", "data/*.npz"])}
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
