#!/usr/bin/env python3
"""Write media/MANIFEST.json: what each file shows and how it was made."""

import hashlib
import json
import subprocess
from pathlib import Path

MEDIA = Path(__file__).resolve().parent
DEMO = MEDIA.parent
DATA = MEDIA / "data"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def probe(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True,
                          check=True).stdout.strip()


def main():
    good = json.loads((DATA / "grade_good.json").read_text())
    selftest = json.loads((DATA / "selftest.json").read_text())
    size_kib = good["gates"]["hygiene"]["dist_bytes"] / 1024

    def data_sha(name):
        return sha256(DATA / name)

    manifest = {
        "demo": "app-builder-preview",
        "generated_by": "media/make_media.sh",
        "files": {
            "result.png": {
                "sha256": sha256(MEDIA / "result.png"),
                "size_bytes": (MEDIA / "result.png").stat().st_size,
            },
            "loop.png": {
                "sha256": sha256(MEDIA / "loop.png"),
                "size_bytes": (MEDIA / "loop.png").stat().st_size,
            },
            "demo.mp4": {
                "sha256": sha256(MEDIA / "demo.mp4"),
                "size_bytes": (MEDIA / "demo.mp4").stat().st_size,
                "width": 1920, "height": 1080, "fps": 30, "codec": "h264",
            },
            "master/demo_master.mp4": {
                "sha256": sha256(MEDIA / "master" / "demo_master.mp4"),
                "size_bytes":
                    (MEDIA / "master" / "demo_master.mp4").stat().st_size,
                "note": "lossless master, git-ignored",
            },
        },
        "shows": {
            "result.png": (
                "Judge gate numbers for the known-good artifact, seed "
                f"{good['seed']}: per-flow visible-item count and "
                "stats-total against the exact spec expectations (dashed "
                f"pass lines), build size {size_kib:.1f} KiB against the "
                "250 KiB budget, console errors against zero"),
            "loop.png": (
                "Left: the scripted fixing replay - failing gates per "
                "iteration until the good artifact passes (pass line 0). "
                f"Right: self-test kill rate {selftest['kill_rate']} - the "
                "known-good passes, every mutant is killed"),
            "demo.mp4": (
                "42 s step-through: the 6 flow screenshots the judge "
                "captured (--shots), each with its steps, expected DOM "
                "state and measured numbers, then result.png and loop.png"),
        },
        "source_data": {
            "grade_good": f"media/data/grade_good.json (sha256 "
                          f"{data_sha('grade_good.json')})",
            "selftest": f"media/data/selftest.json (sha256 "
                        f"{data_sha('selftest.json')})",
            "replay": f"media/data/replay.json (sha256 "
                      f"{data_sha('replay.json')})",
            "mutants": "media/data/mutants/*.json (one verdict per mutant)",
            "flow_screenshots": "media/data/shots/<flow>.png (captured by "
                                "judge/grade.sh --shots while grading)",
        },
        "commands": {
            "setup": "bash judge/setup.sh",
            "grade_good": "bash judge/grade.sh examples/good/app --seed 0 "
                          "--json media/data/grade_good.json --shots "
                          "media/data/shots",
            "selftest": "bash judge/selftest.sh",
            "media": "bash media/make_media.sh",
        },
        "environment": {
            "python": probe("python3", "-c", "import sys; "
                            "print('.'.join(map(str, sys.version_info[:3])))"),
            "matplotlib": probe(str(MEDIA / ".venv/bin/python"), "-c",
                                "import matplotlib;print(matplotlib.__version__)"),
            "ffmpeg": probe("ffmpeg", "-version").split()[2].rstrip(')'),
        },
    }
    (MEDIA / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print("media: wrote MANIFEST.json")


if __name__ == "__main__":
    main()
