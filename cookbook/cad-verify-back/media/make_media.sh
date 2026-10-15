#!/usr/bin/env bash
# cookbook/cad-verify-back/media: regenerate every media file from judge outputs.
#
# Stages (default: all):
#   data  - run the judge for real: regenerate the good exports, build the 10
#           scripted mutants, grade every artifact with --json, replay the
#           fixing-agent loop (bad -> partly fixed -> good) and run the
#           self-test.  All verdict JSONs land in media/data/ (git-ignored).
#   figs  - result.png + loop.png from those verdict JSONs (matplotlib only,
#           every plotted number read from a judge output file).
#   video - demo.mp4: part turntable + one card per mutant (1920x1080 30fps,
#           H.264 crf 18 slow yuv420p +faststart, < 8 MB) from a lossless
#           crf-0 master written to media/master/ (git-ignored).
#   manifest - MANIFEST.json (sha256, command, source data per file).
#
# Tools: exactly what judge/setup.sh pins (matplotlib 3.11.2 / numpy 2.5.4 are
# pinned wheels of the judge's own requirements.txt) + the distro ffmpeg.
# Run 'bash judge/setup.sh' first.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
JUDGE="${ROOT}/judge"
GOOD="${ROOT}/examples/good"
DATA="${HERE}/data"
MUTDIR="${DATA}/mutants"

MUTANTS=(wrong_bolt_count wrong_pcd bore_off boss_missing scale_inch_mm
         stl_flipped_facet stl_not_watertight dxf_missing_hole
         edge_violation tangential_hole_drift)

# The fixing-agent loop this demo replays (worst -> nearly right -> pass).
# It is a replay of graded verdicts, not a live agent trace; every iteration
# is a real grade.sh run on a scripted artifact.
REPLAY=(scale_inch_mm boss_missing tangential_hole_drift)

fail() { echo "make_media: $*" >&2; exit 1; }

stage_data() {
    mkdir -p "${DATA}/verdicts" "${DATA}/replay"
    echo "[data] regenerating the good example's delivered files"
    ( cd "${GOOD}" && python3 part.py ) >"${DATA}/part_py.log"

    echo "[data] building the ${#MUTANTS[@]} scripted mutants (judge/mutants.py)"
    rm -rf "${MUTDIR}"
    python3 "${JUDGE}/mutants.py" "${GOOD}" "${MUTDIR}" >"${DATA}/mutants.log"

    echo "[data] grading every artifact (judge/grade.sh --json)"
    grade() {  # grade <artifact_dir> <json_out>
        local dir="$1" out="$2"
        if ! bash "${JUDGE}/grade.sh" "$dir" --json "$out" >"${out%.json}.log" 2>&1; then
            echo "[data]   verdict FAIL (expected for mutants): $(basename "${dir%/}")"
        else
            echo "[data]   verdict PASS: $(basename "${dir%/}")"
        fi
    }
    grade "${GOOD}" "${DATA}/verdicts/good.json"
    for m in "${MUTANTS[@]}"; do
        grade "${MUTDIR}/${m}" "${DATA}/verdicts/${m}.json"
    done

    echo "[data] replaying the fixing-agent loop: ${REPLAY[*]} -> good"
    local i=0
    for m in "${REPLAY[@]}"; do
        i=$((i + 1))
        grade "${MUTDIR}/${m}" "${DATA}/replay/iter${i}_${m}.json"
    done
    i=$((i + 1))
    grade "${GOOD}" "${DATA}/replay/iter${i}_good.json"

    echo "[data] running the self-test (kill rate + determinism)"
    bash "${JUDGE}/selftest.sh" >"${DATA}/selftest.log" 2>&1 \
        || fail "selftest.sh failed - see ${DATA}/selftest.log"
    grep -E "kill rate|determinism" "${DATA}/selftest.log" | sed 's/^/[data]   /'

    # every figure below reads these files; refuse to invent any of them
    local needed=("${DATA}/verdicts/good.json")
    local m
    for m in "${MUTANTS[@]}"; do
        needed+=("${DATA}/verdicts/${m}.json")
    done
    needed+=("${DATA}/replay/"iter*.json "${DATA}/selftest.log")
    for f in "${needed[@]}"; do
        [ -s "$f" ] || fail "data stage: judge output $f missing or empty"
    done
    echo "[data] done."
}

stage_figs() {
    MPLBACKEND=Agg python3 "${HERE}/fig_result.py"
    MPLBACKEND=Agg python3 "${HERE}/fig_loop.py"
}

stage_video() {
    MPLBACKEND=Agg python3 "${HERE}/video.py"
    local frames="${DATA}/frames"
    mkdir -p "${HERE}/master"
    echo "[video] lossless crf-0 master (media/master/, git-ignored)"
    ffmpeg -y -hide_banner -loglevel error -f concat -safe 0 \
        -i "${frames}/concat.txt" -vf fps=30 \
        -c:v libx264 -crf 0 -preset veryfast -pix_fmt yuv420p \
        "${HERE}/master/demo_master.mp4"
    echo "[video] web encode (crf 18, slow, yuv420p, +faststart)"
    ffmpeg -y -hide_banner -loglevel error -i "${HERE}/master/demo_master.mp4" \
        -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p \
        -movflags +faststart -an "${HERE}/demo.mp4"
    local size
    size=$(stat -c%s "${HERE}/demo.mp4")
    [ "$size" -lt $((8 * 1024 * 1024)) ] \
        || fail "demo.mp4 is ${size} bytes (>= 8 MB); raise crf or shorten"
    echo "[video] demo.mp4 ${size} bytes"
}

stage_manifest() {
    python3 "${HERE}/manifest.py"
}

case "${1:-all}" in
    data)     stage_data ;;
    figs)     stage_figs ;;
    video)    stage_video ;;
    manifest) stage_manifest ;;
    all)      stage_data; stage_figs; stage_video; stage_manifest ;;
    *) echo "usage: make_media.sh [data|figs|video|manifest|all]" >&2; exit 2 ;;
esac
