#!/usr/bin/env bash
# Regenerate all gpu-kernel demo media from media/data/.
#
#   bash cookbook/gpu-kernel/media/make_media.sh
#
# Requires: python3 (for a local venv), ffmpeg + ffprobe on PATH, and the
# source data committed under media/data/. Writes media/result.png,
# media/loop.png, media/demo.mp4 and media/MANIFEST.json (sha256 of every
# output plus the sha256 of its source data).
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -s data/gpu-run.log ]; then
    echo "make_media.sh: missing data/gpu-run.log" >&2
    exit 1
fi
if [ ! -s data/report.json ]; then
    echo "make_media.sh: missing data/report.json" >&2
    echo "  generate it on a GPU host:" >&2
    echo "    python3 cookbook/gpu-kernel/run.py --gpu \\" >&2
    echo "        --report-json cookbook/gpu-kernel/media/data/report.json" >&2
    echo "  then commit it before re-running this script." >&2
    exit 1
fi

for tool in ffmpeg ffprobe; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "make_media.sh: $tool not found on PATH" >&2
        exit 1
    fi
done

VENV=.venv
if [ ! -x "$VENV/bin/python" ]; then
    echo "make_media.sh: creating venv at media/$VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet "matplotlib==3.10.8" "numpy==2.4.3"
fi

"$VENV/bin/python" make_figures.py
"$VENV/bin/python" make_video.py

"$VENV/bin/python" - <<'PY'
import hashlib, json, os

def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()

outputs = {
    "result.png": ["data/report.json"],
    "loop.png": ["data/report.json"],
    "demo.mp4": ["data/gpu-run.log", "data/report.json",
                 "result.png", "loop.png"],
}
manifest = {"generated_by": "media/make_media.sh",
            "data": {p: {"sha256": sha(p)} for p in
                     ("data/gpu-run.log", "data/report.json")},
            "outputs": {}}
for out, sources in outputs.items():
    manifest["outputs"][out] = {
        "sha256": sha(out),
        "source_data": {s: sha(s) for s in sources}}
with open("MANIFEST.json", "w") as fh:
    json.dump(manifest, fh, indent=2, sort_keys=True)
    fh.write("\n")
print("wrote MANIFEST.json")
PY
