#!/usr/bin/env python3
"""Generate MANIFEST.json for the spice-filter demo media."""
import hashlib
import json
import subprocess
from pathlib import Path

MEDIA = Path(__file__).resolve().parent

def sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def get_ffmpeg_version():
    try:
        out = subprocess.check_output(["ffmpeg", "-version"], text=True, stderr=subprocess.STDOUT)
        return out.splitlines()[0].split()[2]
    except Exception:
        return "unknown"

def get_remotion_version():
    try:
        pkg = json.loads((MEDIA / "video" / "package.json").read_text())
        return pkg["dependencies"]["remotion"]
    except Exception:
        return "unknown"

def get_ffprobe_info(filepath):
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration,codec_name",
            "-of", "json", str(filepath)
        ], text=True)
        info = json.loads(out)
        stream = info["streams"][0]
        return {
            "width": stream.get("width"),
            "height": stream.get("height"),
            "duration_sec": float(stream.get("duration", 0)),
            "codec": stream.get("codec_name"),
        }
    except Exception as e:
        return {"error": str(e)}

def main():
    manifest = {
        "demo": "spice-filter",
        "generated_by": "media/make_media.sh",
        "files": {},
        "source_data": {
            "sweep_good": "media/data/sweep_good.json (judge ngspice sweeps)",
            "replay": "media/data/replay.json (scripted replay: r-decade-up -> off-series -> unrecognised-topology -> good)",
            "selftest": "media/data/selftest.json (judge selftest: 9 mutants, 100% kill rate)",
            "transient": "media/data/transient.json (ngspice .tran of the good netlist at 300 Hz / 1.4 kHz / 16 kHz)",
            "mc_curves": "media/data/mc_curves.json (all 100 seeded Monte-Carlo sweeps)",
            "runlog": "media/data/runlog.txt (captured selftest+grade terminal output)",
            "video_props": "media/data/video_props.json (HUD numbers, from the verdict JSONs)",
        },
        "commands": {
            "setup": "bash judge/setup.sh",
            "selftest": "bash judge/selftest.sh",
            "grade_good": "bash judge/grade.sh examples/good/lpf4sk.cir --json good.json",
            "media": "bash media/make_media.sh",
        },
        "environment": {
            "python": "3.12.15",
            "matplotlib": "3.9.4",
            "pillow": "12.3.0",
            "ffmpeg": get_ffmpeg_version(),
            "ngspice": "39.3+ds-1 (Debian bookworm)",
            "remotion": get_remotion_version(),
        },
    }

    for fname in ["result.png", "loop.png", "demo.mp4"]:
        fpath = MEDIA / fname
        if fpath.exists():
            manifest["files"][fname] = {
                "sha256": sha256(fpath),
                "size_bytes": fpath.stat().st_size,
            }
            if fname == "demo.mp4":
                manifest["files"][fname].update(get_ffprobe_info(fpath))

    frames_dir = MEDIA / "frames"
    if frames_dir.exists():
        for fpath in sorted(frames_dir.glob("*.jpg")):
            manifest["files"][f"frames/{fpath.name}"] = {
                "sha256": sha256(fpath),
                "size_bytes": fpath.stat().st_size,
            }

    master_path = MEDIA / "master" / "demo_master.mp4"
    if master_path.exists():
        manifest["files"]["master/demo_master.mp4"] = {
            "sha256": sha256(master_path),
            "size_bytes": master_path.stat().st_size,
        }

    (MEDIA / "MANIFEST.json").write_text(json.dumps(manifest, indent=1))
    print("MANIFEST.json written")

if __name__ == "__main__":
    main()
