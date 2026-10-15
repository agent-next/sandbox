#!/usr/bin/env python3
"""Write media/MANIFEST.json: sha256 and provenance for every media file."""

import hashlib
import json
import subprocess
from pathlib import Path

MEDIA = Path(__file__).resolve().parent

PRODUCED_BY = {
    "result.png": {
        "what": "Recalculated NPV at 8/10/12% against the closed-form oracle "
                "with the judge's ±0.5% pass band, plus each oracle error "
                "against its SPEC limit.",
        "command": "media/make_media.sh -> media/render.py "
                   "(data: grade.json, selftest.json, model.json)",
        "source": "media/data/grade.json",
    },
    "loop.png": {
        "what": "The judge loop: self-test kill-rate bars (known-good vs "
                "every known-bad mutant) and the error-vs-limit panel.",
        "command": "media/make_media.sh -> media/render.py",
        "source": "media/data/selftest.json, media/data/grade.json",
    },
    "demo.mp4": {
        "what": "30 s step-through: artifact structure, judge recalc vs "
                "oracle, self-test kills, verdict.",
        "command": "media/make_media.sh -> media/render.py frames + ffmpeg "
                   "-crf 18 (web encode of the crf 0 master)",
        "source": "media/data/*.json",
    },
    "master/demo_master.mp4": {
        "what": "Lossless H.264 master (crf 0) the web encode is made from.",
        "command": "media/make_media.sh -> ffmpeg -crf 0",
        "source": "media/data/*.json",
    },
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_name,width,height,pix_fmt",
         "-show_entries", "format=duration,size",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    stream = info["streams"][0]
    return {
        "codec": stream.get("codec_name"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "pix_fmt": stream.get("pix_fmt"),
        "duration_sec": round(float(info["format"]["duration"]), 2),
    }


def main():
    files = {}
    for name, meta in PRODUCED_BY.items():
        path = MEDIA / name
        assert path.exists(), f"missing {name}; run make_media.sh first"
        entry = {
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
            **meta,
        }
        if name.endswith(".mp4"):
            entry.update(probe(path))
            assert entry["size_bytes"] < 8 * 1024 * 1024, \
                f"{name} is {entry['size_bytes']} bytes, over the 8 MB limit"
            assert (entry["width"], entry["height"]) == (1920, 1080), \
                f"{name} is not 1920x1080"
        files[name] = entry
    manifest = {
        "demo": "spreadsheet-recalc",
        "generated_by": "media/make_media.sh",
        "files": files,
    }
    (MEDIA / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print("manifest: wrote MANIFEST.json")


if __name__ == "__main__":
    main()
