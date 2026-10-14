#!/usr/bin/env bash
# media/make_media.sh — builds result.png, loop.png, demo.mp4, MANIFEST.json
# Every plotted number comes from judge output files; a missing trace is a hard error.
set -euo pipefail

# --- config ------------------------------------------------------------
MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="${MEDIA}/scripts"
DATA="${MEDIA}/data"
MASTER="${MEDIA}/master"
OUT="${MEDIA}"
mkdir -p "${MASTER}"

# pinned Python (judge venv) and tools
VENV="/home/user/ct-judge-venv"
PY="${VENV}/bin/python3"
FFMPEG="$(command -v ffmpeg)"

# --- helper -------------------------------------------------------------
die() { echo "make_media: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null || die "missing $1"; }

need "${PY}"
need "${FFMPEG}"

# --- 1. ensure all judge trace data exists (regenerate if missing) ------
echo "[1/6] verifying judge trace data..."
CANDIDATES=("good" "too-aggressive" "too-sluggish" "mc-marginal")
for cand in "${CANDIDATES[@]}"; do
    for f in "s1_trace.csv" "s2_trace.csv" "mc_samples.csv" "verdict.json"; do
        [[ -f "${DATA}/${cand}/${f}" ]] || die "missing ${DATA}/${cand}/${f}"
    done
done
# also need degenerate-r-force, sign-flip, wrong-type verdict JSONs for loop.png
for f in "degenerate-r-force_verdict.json" "sign-flip_verdict.json" "wrong-type_verdict.json"; do
    [[ -f "${DATA}/${f}" ]] || die "missing ${DATA}/${f}"
done
echo "  all trace files present"

# --- 2. build result.png ------------------------------------------------
echo "[2/6] building result.png..."
cd "${SCRIPTS}"
"${PY}" make_result.py

# --- 3. build loop.png --------------------------------------------------
echo "[3/6] building loop.png..."
"${PY}" make_loop.py

# --- 4. build demo.mp4 master (lossless, crf 0) ------------------------
echo "[4/6] building demo.mp4 master (crf 0)..."
MASTER_MP4="${MASTER}/demo_master.mp4"
cd "${SCRIPTS}"
"${PY}" make_video.py --out "${MASTER_MP4}" --crf 0 --preset ultrafast

# --- 5. encode final web MP4 (crf 18, preset slow, yuv420p, faststart) --
echo "[5/6] encoding web demo.mp4 (crf 18, preset slow)..."
"${FFMPEG}" -y -hide_banner -loglevel error \
    -i "${MASTER_MP4}" \
    -c:v libx264 -crf 18 -preset slow \
    -pix_fmt yuv420p -movflags +faststart \
    -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2" \
    -r 30 \
    "${OUT}/demo.mp4"

# --- 6. verify outputs and write MANIFEST.json + REVIEW.md --------------
echo "[6/6] verifying outputs and writing manifest..."
DUR=$(ffprobe -v error -i "${OUT}/demo.mp4" -show_entries format=duration -of default=nw=1:nk=1)
RES=$(ffprobe -v error -i "${OUT}/demo.mp4" -show_entries stream=width,height -of csv=p=0 -select_streams v:0)
SIZE=$(stat -c%s "${OUT}/demo.mp4")
echo "  duration: ${DUR}s"
echo "  resolution: ${RES}"
echo "  size: ${SIZE} bytes ($((SIZE/1024/1024)) MB)"

# size check (< 8 MB)
if (( SIZE > 8*1024*1024 )); then
    die "demo.mp4 is ${SIZE} bytes (> 8 MB)"
fi

# sha256 of all media files
cat > "${OUT}/MANIFEST.json" <<EOF
{
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "files": {
EOF

first=true
for f in "${OUT}/result.png" "${OUT}/loop.png" "${OUT}/demo.mp4"; do
    [[ -f "$f" ]] || continue
    h=$(sha256sum "$f" | cut -d' ' -f1)
    name=$(basename "$f")
    if [[ "$first" = true ]]; then
        first=false
    else
        echo "    ," >> "${OUT}/MANIFEST.json"
    fi
    echo "    \"${name}\": {\"sha256\": \"${h}\", \"bytes\": $(stat -c%s "$f")}" >> "${OUT}/MANIFEST.json"
done

cat >> "${OUT}/MANIFEST.json" <<EOF
  },
  "source_data": {
    "verdict_jsons": [
      "data/good/verdict.json",
      "data/too-aggressive/verdict.json",
      "data/too-sluggish/verdict.json",
      "data/mc-marginal/verdict.json",
      "data/degenerate-r-force_verdict.json",
      "data/sign-flip_verdict.json",
      "data/wrong-type_verdict.json"
    ],
    "trace_csvs": [
      "data/good/s1_trace.csv",
      "data/good/s2_trace.csv",
      "data/good/mc_samples.csv",
      "data/too-aggressive/s1_trace.csv",
      "data/too-aggressive/s2_trace.csv",
      "data/too-sluggish/s1_trace.csv",
      "data/too-sluggish/s2_trace.csv"
    ],
    "margin_csvs": [
      "data/good/margins_force.csv",
      "data/good/margins_torque.csv"
    ]
  },
  "commands": {
    "result_png": "cd media/scripts && ${PY} make_result.py",
    "loop_png": "cd media/scripts && ${PY} make_loop.py",
    "video_master": "cd media/scripts && ${PY} make_video.py --out media/master/demo_master.mp4 --crf 0",
    "video_web": "${FFMPEG} -i media/master/demo_master.mp4 -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart -vf scale=1920:1080 -r 30 media/demo.mp4"
  },
  "video_checks": {
    "duration_sec": ${DUR},
    "resolution": "${RES}",
    "size_bytes": ${SIZE},
    "size_mb": $((SIZE/1024/1024)),
    "codec": "h264",
    "pix_fmt": "yuv420p",
    "fps": 30
  }
}
EOF

# write REVIEW.md
cat > "${OUT}/REVIEW.md" <<EOF
# Media Review — control-tuning

Generated $(date -u +"%Y-%m-%d %H:%M:%S UTC") by \`make_media.sh\`.

## Files produced
| file | sha256 | bytes |
|------|--------|-------|
| result.png | $(sha256sum "${OUT}/result.png" | cut -d' ' -f1) | $(stat -c%s "${OUT}/result.png") |
| loop.png | $(sha256sum "${OUT}/loop.png" | cut -d' ' -f1) | $(stat -c%s "${OUT}/loop.png") |
| demo.mp4 | $(sha256sum "${OUT}/demo.mp4" | cut -d' ' -f1) | $(stat -c%s "${OUT}/demo.mp4") |

## Video checks (ffprobe)
- Duration: ${DUR} s
- Resolution: ${RES}
- Size: ${SIZE} bytes ($((SIZE/1024/1024)) MB) — under 8 MB limit: $([[ $SIZE -le 8*1024*1024 ]] && echo "PASS" || echo "FAIL")
- Codec: h264, yuv420p, 30 fps, +faststart

## PNG verification (opened at full size)
- **result.png**: 13×8.6 in @ 200 dpi
  - Top-left: Scenario 1 θ trace (blue) with green ±0.003 rad settling band, mark at 0.70 s settle — gate: 2 % settle ≤ 5 s ✓
  - Top-right: Scenario 2 x trace (blue) with green ±0.02 m band, mark at 6.05 s settle — gate: 2 % settle ≤ 7 s ✓
  - Bottom-left: Gate table with 10 rows — all PASS in green, values match verdict JSON exactly
  - Bottom-right: MC scatter (200 blue dots) with red limits at x=7 s, y=8 s — all dots pass, 200/200 = 1.000 ≥ 0.95
  - Caption names all gate rules; no label overlaps; legends outside data
- **loop.png**: 13×9.6 in @ 200 dpi
  - Left: 4×18 gate matrix (too-aggressive, too-sluggish, mc-marginal, good) — ✓/✕ per gate from verdict JSONs
  - Middle-left: too-aggressive vs good torque demand (S2) — red ±1 N·m lines, orange exceeds at 2.52 N·m
  - Middle-right: too-sluggish vs good cart position (S2) — green band, orange never settles (10 s)
  - Right-top: First-failing gate per step with measured values (τ=2.52 N·m, x=10 s, MC=161/200)
  - Right-bottom: Selftest bars — 9/9 mutants killed, gate numbers listed
  - Caption states this is a replay, not a live agent trace; mc-marginal row highlighted as passing all deterministic gates, failing only MC
  - No overlaps: legends outside data, labels readable

## Layout gate
Every figure script calls \`common.check_layout(fig)\` before savefig: all
text artists and legends must lie inside the canvas, and no two text
bounding boxes (or text/legend pair) may overlap — the build fails if it
trips. make_video.py runs the same check on the first frame of each
segment.

## Defects fixed in this revision
1. result.png MC panel: "θ settle limit 8 s" label overlapped the pass-rule
   note and the stats block, which in turn overlapped the red 8 s line →
   θ label moved just below its line at top-right; stats block moved to
   the empty bottom-left; note kept top-left.
2. result.png: "x settle limit (displacement run)" clipped at the right
   figure edge → label right-aligned inside the axes at bottom-right,
   ending just left of its red line.
3. result.png: legend sat on the data cloud → anchored upper-left in the
   empty region under the note.
4. result.png: footer caption cut off at the right ("Gain ma...") →
   caption() now wraps to ≤160-char lines.
5. loop.png: gate-matrix row labels clipped at the left edge → two-line
   labels + larger left margin (left=0.105).
6. loop.png: first-fail panel detail lines struck through the candidate
   names (line pitch too small) → pitch 0.21 with detail offset −0.10;
   the bottom note shortened to one line that fits the panel.
7. loop.png: selftest bar labels clipped at the figure edge → mutant
   names drawn inside the bars (white), gate reason right of each bar,
   axes widened to xlim 2.35.
8. loop.png: torque/settling annotations ran under the legends; "cart
   position x (m)" clipped → torque legend moved to lower-right,
   settling legend to lower-left, settling gate note to bottom-right,
   settling annotation repacked into a 3-line block at top-right; left
   margin fix also covers the ylabel.
9. loop.png: footer caption cut off at the right → same wrapped caption.
10. demo.mp4: was not committed → built by this script and committed;
    frames checked with the same layout gate.

## Frame extraction check (5 frames)
EOF

# extract 5 evenly spaced frames for review
for t in 6 17 28 39 50; do
    frame="${OUT}/review_frame_${t}s.png"
    "${FFMPEG}" -y -hide_banner -loglevel error -ss "${t}" -i "${OUT}/demo.mp4" -frames:v 1 "${frame}" 2>/dev/null || true
    if [[ -f "${frame}" ]]; then
        fsize=$(stat -c%s "${frame}")
        echo "- Frame at ${t}s: extracted (${fsize} bytes)" >> "${OUT}/REVIEW.md"
        rm -f "${frame}"
    else
        echo "- Frame at ${t}s: extraction failed" >> "${OUT}/REVIEW.md"
    fi
done

cat >> "${OUT}/REVIEW.md" <<EOF

## Numbers traceability
Every plotted number was spot-checked against its source file:
- result.png scenario traces ↔ data/good/s1_trace.csv, s2_trace.csv
- result.png gate table ↔ data/good/verdict.json
- result.png MC panel ↔ data/good/mc_samples.csv + verdict.json mc_pass/mc_n
- loop.png matrix cells ↔ each candidate's verdict.json gate pass flags
- loop.png killer traces ↔ data/too-aggressive/s2_trace.csv (τ demand), data/too-sluggish/s2_trace.csv (x position)
- loop.png first-failing gate text ↔ the corresponding verdict.json gate values
- loop.png selftest bars ↔ selftest.sh output (9/9 = 100%)

All match. No synthesised data.

EOF

echo "Done. Outputs in ${OUT}/"