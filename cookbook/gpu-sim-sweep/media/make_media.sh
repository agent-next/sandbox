#!/usr/bin/env bash
# Regenerate all gpu-sim-sweep demo media from media/data/.
#
#   bash cookbook/gpu-sim-sweep/media/make_media.sh
#
# Requires: python3 (for a local venv), ffmpeg + ffprobe on PATH, and the
# source data committed under media/data/. Writes media/result.png,
# media/loop.png, media/demo.mp4 and media/MANIFEST.json (sha256 of every
# output plus the sha256 of its source data). The lossless intermediate
# media/master/demo-master.mp4 is regenerated too but stays git-ignored.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -s data/report.json ]; then
    echo "make_media.sh: missing data/report.json" >&2
    echo "  generate it on a GPU key:" >&2
    echo "    python3 cookbook/gpu-sim-sweep/run.py --gpu \\" >&2
    echo "        --report-json cookbook/gpu-sim-sweep/media/data/report.json" >&2
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
    "result.png": {
        "what": "Measured GPU steps/s vs nworld on the 4 GiB slice (log-log) "
                "with the measured CPU baseline and the throughput pass "
                "floor drawn on it; plus the physics oracle per nworld "
                "(landed box z band, arm error vs tolerance).",
        "command": "media/make_figures.py",
    },
    "loop.png": {
        "what": "Gate x artifact verdict matrix (good config + every "
                "mutant) from the real grade runs, plus the self-test "
                "kill-rate bar.",
        "command": "media/make_figures.py",
    },
    "demo.mp4": {
        "what": "The 8 boxes falling onto the table in world 0, rendered "
                "from the judge-measured settle trajectory, then the "
                "nworld ladder filling in with measured steps/s.",
        "command": "media/make_video.py + ffmpeg "
                   "(lossless crf-0 master in git-ignored media/master/)",
    },
}
manifest = {"generated_by": "media/make_media.sh",
            "note": "every number plotted comes from the judge's own "
                    "measurements in data/report.json (a real "
                    "run.py --gpu exec report)",
            "data": {p: {"sha256": sha(p)} for p in ("data/report.json",)},
            "outputs": {}}
for out, meta in outputs.items():
    manifest["outputs"][out] = {
        **meta,
        "sha256": sha(out),
        "bytes": os.path.getsize(out),
        "source_data": {"data/report.json": sha("data/report.json")}}
with open("MANIFEST.json", "w") as fh:
    json.dump(manifest, fh, indent=2, sort_keys=True)
    fh.write("\n")
print("wrote MANIFEST.json")
PY
