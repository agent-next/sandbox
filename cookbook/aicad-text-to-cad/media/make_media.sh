#!/bin/bash
# Regenerate every media file from the judge's own outputs.
#
#   bash media/make_media.sh          (run media/collect_verdicts.sh first)
#
# Builds, from media/data/ (real verdict JSONs, the selftest log, the
# replay order -- nothing synthesised):
#   result.png   the 3 delivered parts vs the spec-built reference
#   loop.png     agent-loop replay + mutant x gate matrix + kill rate
#   demo.mp4     1920x1080 30 fps H.264 web encode (crf 18, preset slow,
#                yuv420p, +faststart, < 8 MB) from a lossless crf-0 master
#                written to media/master/ (git-ignored)
#   MANIFEST.json  sha256 + provenance of each output
#
# Python side runs under the pinned judge venv (matplotlib 3.11.2,
# trimesh 4.12.2, manifold3d 3.5.2, OCP 7.9.3.1.1 -- sha256-checked in
# judge/requirements.txt); ffmpeg is the distro build (version recorded
# in MANIFEST.json).  Fails loudly if any input data file is missing.
set -euo pipefail

MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${AICAD_JUDGE_VENV:-$HOME/.venvs/aicad-judge}/bin/python"
[ -x "$PY" ] || { echo "judge venv missing -- run judge/setup.sh" >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo "ffmpeg not found" >&2; exit 1; }

FFMPEG_VER="$(ffmpeg -version | head -1)"
echo "== inputs (all produced by collect_verdicts.sh) =="
for f in data/verdicts/good_bushing.json data/verdicts/good_adapter_plate.json \
         data/verdicts/good_bracket.json data/selftest.txt data/replay.txt; do
    [ -f "$MEDIA/$f" ] || { echo "missing $MEDIA/$f -- run media/collect_verdicts.sh first" >&2; exit 1; }
done
for m in plate-hole-count plate-hole-diameter plate-hole-drift \
         plate-flipped-facet bracket-missing-fillet bracket-fillet-radius \
         bushing-scale-25_4 bushing-non-watertight; do
    [ -f "$MEDIA/data/verdicts/$m.json" ] || { echo "missing verdict $m" >&2; exit 1; }
done
echo "   11 verdict JSONs + selftest.txt + replay.txt present"

cd "$MEDIA"

echo "== result.png =="
"$PY" fig_result.py

echo "== loop.png =="
"$PY" fig_loop.py

echo "== demo.mp4 master frames (lossless inputs) =="
"$PY" make_video.py

echo "== demo.mp4: lossless master (crf 0) =="
mkdir -p master
ffmpeg -hide_banner -loglevel error -y -framerate 30 -i work/frames/f%05d.png \
    -c:v libx264 -crf 0 -preset veryfast -pix_fmt yuv444p master/demo_master.mp4

echo "== demo.mp4: web encode (crf 18, preset slow, yuv420p, +faststart) =="
ffmpeg -hide_banner -loglevel error -y -i master/demo_master.mp4 \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart \
    -an demo.mp4

SIZE=$(stat -c%s demo.mp4)
if [ "$SIZE" -ge $((8 * 1024 * 1024)) ]; then
    echo "demo.mp4 is $SIZE bytes (>= 8 MB) -- shorten scenes and rebuild" >&2
    exit 1
fi
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 demo.mp4)
echo "   demo.mp4: ${DUR}s, $SIZE bytes"

echo "== MANIFEST.json =="
"$PY" - "$FFMPEG_VER" <<'PYEOF'
import hashlib, json, os, sys
MEDIA = os.getcwd()          # make_media.sh has cd'ed into media/
ffmpeg = sys.argv[1]

def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

v = sorted(os.listdir("data/verdicts"))
collect = ("bash media/collect_verdicts.sh  (judge/setup.sh first): "
           "mutants.py rebuilds the 8 mutants, judge/grade.sh --seed 42 "
           "--json grades the 3 good parts + 8 mutants, judge/selftest.sh "
           "writes data/selftest.txt")
files = {
    "result.png": {
        "what": "the three known-good parts as delivered (model.stl) beside "
                "the reference solid rebuilt from judge/spec.json, with the "
                "boolean-XOR difference highlighted (zero for the good "
                "parts) and each gate's measured number vs its pass line",
        "command": "bash media/make_media.sh -> $PY media/fig_result.py",
        "source_data": ["data/verdicts/good_bushing.json",
                        "data/verdicts/good_adapter_plate.json",
                        "data/verdicts/good_bracket.json",
                        "examples/good/*/model.stl",
                        "examples/good/*/model.step",
                        "judge/spec.json"],
        "sha256": sha("result.png"),
    },
    "loop.png": {
        "what": "the agent loop replayed (gates failed per iteration until "
                "pass), the mutant x gate matrix (3 good parts + 8 "
                "single-edit mutants vs the judge's 10 gates, failing "
                "cells showing measured value vs limit) and the selftest "
                "kill rate against the 90% floor",
        "command": "bash media/make_media.sh -> $PY media/fig_loop.py",
        "source_data": ["data/verdicts/*.json", "data/selftest.txt",
                        "data/replay.txt", "judge/mutants.py"],
        "sha256": sha("loop.png"),
    },
    "demo.mp4": {
        "what": "the text spec, the generated bushing turning beside the "
                "spec-built reference with its 10-gate verdict, then one "
                "card per mutant with the defect highlighted on the real "
                "delivered mesh and the gate that killed it, then the "
                "selftest summary",
        "command": ("bash media/make_media.sh -> $PY media/make_video.py "
                    "(frames) | ffmpeg -framerate 30 -i f%05d.png -crf 0 "
                    "master | ffmpeg -crf 18 -preset slow -pix_fmt yuv420p "
                    "-movflags +faststart demo.mp4"),
        "source_data": ["data/verdicts/*.json", "data/selftest.txt",
                        "examples/good/bushing/spec.txt",
                        "examples/good/bushing/model.stl",
                        "data/mutants/*/model.stl", "judge/spec.json"],
        "sha256": sha("demo.mp4"),
    },
    "master/demo_master.mp4": {
        "what": "lossless (crf 0) master demo.mp4 is encoded from; "
                "git-ignored, regenerated by make_media.sh",
        "command": "ffmpeg -framerate 30 -i work/frames/f%05d.png -crf 0 "
                   "-preset veryfast -pix_fmt yuv444p master/demo_master.mp4",
        "source_data": ["work/frames/*.png (make_video.py)"],
        "sha256": sha("master/demo_master.mp4"),
    },
}
out = {
    "seed": 42,
    "python": "judge venv (judge/requirements.txt, sha256-pinned): "
              "matplotlib 3.11.2, trimesh 4.12.2, manifold3d 3.5.2, "
              "OCP 7.9.3.1.1",
    "ffmpeg": ffmpeg,
    "data_collected_by": collect,
    "verdicts": v,
    "files": files,
}
open("MANIFEST.json", "w").write(json.dumps(out, indent=2) + "\n")
print(f"   MANIFEST.json: {len(files)} files recorded")
PYEOF

echo "== done =="
ls -la result.png loop.png demo.mp4 MANIFEST.json master/demo_master.mp4
