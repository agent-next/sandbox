#!/usr/bin/env bash
# media/make_media.sh — regenerate every media file from real judge output.
#
# Pipeline (all data written by judge/selftest.sh and the good artifact in
# THIS invocation — nothing is hand-edited or invented):
#   1. judge/selftest.sh --verdicts media/judge_runs  (good.json + one
#      verdict per mutant; the kill rate; the determinism check)
#   2. the known-good artifact itself, once, under the pinned interpreter
#      (charts.json + the three PNGs the judge graded)
#   3. result.png and loop.png from those judge outputs (make_figures.py)
#   4. video frames from the artifact's PNGs + the verdict numbers
#      (make_frames.py), lossless crf 0 master into media/master/ (git
#      ignored), then the web H.264 encode
#   5. MANIFEST.json (sha256 of each shipped file)
#
# Fails loudly if any expected judge output is missing or a step fails.
# Needs the pinned stack from judge/setup.sh and ffmpeg:
#   CHART_VENV=~/.cache/code-interpreter-charts/venv bash media/make_media.sh

set -euo pipefail

MEDIA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(dirname "$MEDIA_DIR")"
RUNS="$MEDIA_DIR/judge_runs"
MASTER="$MEDIA_DIR/master"
VENV="${CHART_VENV:-$HOME/.cache/code-interpreter-charts/venv}"
PY="$VENV/bin/python"

# The judge stack (exact versions, judge/VERSIONS.txt) so media and judge
# render identically; ffmpeg for the encode.
[ -x "$PY" ] || { echo "make_media: no pinned interpreter at $PY -- run judge/setup.sh first" >&2; exit 1; }
"$PY" -c 'import matplotlib, PIL' >/dev/null 2>&1 || {
    echo "make_media: $PY lacks matplotlib/Pillow -- re-run judge/setup.sh" >&2; exit 1; }
"$PY" - <<'PY' || exit 1
import matplotlib
assert matplotlib.__version__ == '3.11.2', matplotlib.__version__
print('[media] matplotlib', matplotlib.__version__)
PY
command -v ffmpeg >/dev/null 2>&1 || { echo "make_media: ffmpeg missing" >&2; exit 1; }
echo "[media] ffmpeg $(ffmpeg -version | head -1 | awk '{print $3}')"

mkdir -p "$RUNS"

echo "=== 1. self-test (verdicts -> $RUNS) ==="
rm -rf "$RUNS/good.json" "$RUNS/mutants"
bash "$DEMO_DIR/judge/selftest.sh" --verdicts "$RUNS" 2>&1 | tee "$RUNS/selftest_output.txt"

echo "=== 2. good artifact run (charts + PNGs the judge graded) ==="
rm -rf "$RUNS/good_out"
mkdir -p "$RUNS/good_out"
MPLBACKEND=Agg "$PY" -I "$DEMO_DIR/examples/good/analysis.py" \
    --data-dir "$DEMO_DIR/examples/good/data" --out-dir "$RUNS/good_out"

echo "=== 3. guard: judge outputs present ==="
for f in "$RUNS/good.json" "$RUNS/selftest_output.txt" \
         "$RUNS/good_out/charts.json" \
         "$RUNS/good_out/c1_mauna_loa_trend.png" \
         "$RUNS/good_out/c2_seasonal_cycle.png" \
         "$RUNS/good_out/c3_top_emitters_2024.png"; do
    [ -f "$f" ] || { echo "make_media: MISSING $f" >&2; exit 1; }
done
n_mutants="$(ls -1 "$RUNS/mutants"/*.json 2>/dev/null | wc -l)"
[ "$n_mutants" -ge 5 ] || { echo "make_media: only $n_mutants mutant verdicts (< 5)" >&2; exit 1; }

echo "=== 4. figures ==="
"$PY" -I "$MEDIA_DIR/make_figures.py" "$RUNS" "$MEDIA_DIR"

echo "=== 5. video frames (lossless PNG) ==="
FRAMES="$(mktemp -d "${TMPDIR:-/tmp}/charts-frames.XXXXXX")"
trap 'rm -rf "$FRAMES"' EXIT
"$PY" -I "$MEDIA_DIR/make_frames.py" "$RUNS" "$FRAMES"

echo "=== 6. lossless master (crf 0, git-ignored media/master/) ==="
mkdir -p "$MASTER"
rm -f "$MASTER/charts_master.mp4"
# 8 frames at 4 s each = 32 s of content; tpad holds the last frame 3 s
# more: 35 s total, inside the 20-60 s standard.
ffmpeg -y -loglevel error -framerate 1/4 -i "$FRAMES/frame_%04d.png" \
    -c:v libx264 -preset veryslow -crf 0 -pix_fmt yuv444p \
    -vf "fps=30,tpad=stop_mode=clone:stop_duration=3" \
    -s 1920x1080 "$MASTER/charts_master.mp4"

echo "=== 7. web encode (crf 18 preset slow, faststart) ==="
ffmpeg -y -loglevel error -i "$MASTER/charts_master.mp4" \
    -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p \
    -movflags +faststart -an "$MEDIA_DIR/demo.mp4"

echo "=== 8. MANIFEST.json ==="
"$PY" - "$MEDIA_DIR" <<'PY'
import hashlib, json, os, sys

media = sys.argv[1]
entries = []
spec = {
    'result.png': ('Key figure: the three charts the judge graded for the '
                   'known-good artifact (C1 Mauna Loa trend + OLS line, C2 '
                   'seasonal cycle, C3 top-10 emitters) with the verdict '
                   'numbers.',
                   'bash media/make_media.sh  (make_figures.py)',
                   'media/judge_runs/good_out/charts.json, '
                   'media/judge_runs/good.json'),
    'loop.png': ('The agent loop: gates passed per draft iteration '
                 '(single-edit mutant verdicts until the good artifact '
                 'passes) and the self-test kill rate.',
                 'bash media/make_media.sh  (make_figures.py)',
                 'media/judge_runs/mutants/*.json, '
                 'media/judge_runs/good.json, '
                 'media/judge_runs/selftest_output.txt'),
    'demo.mp4': ('Step-through of the agent loop: each judged chart with '
                 'its gate numbers, then the verdict summary; lossless '
                 'crf 0 master in git-ignored media/master/.',
                 'bash media/make_media.sh  (make_frames.py + ffmpeg)',
                 'media/judge_runs/good_out/*.png, '
                 'media/judge_runs/good.json, '
                 'media/judge_runs/selftest_output.txt'),
}
for fname, (what, cmd, src) in spec.items():
    p = os.path.join(media, fname)
    h = hashlib.sha256(open(p, 'rb').read()).hexdigest()
    entries.append({'file': fname, 'what': what, 'command': cmd,
                    'source_data': src, 'sha256': h,
                    'bytes': os.path.getsize(p)})
with open(os.path.join(media, 'MANIFEST.json'), 'w') as f:
    json.dump({'demo': 'cookbook/code-interpreter-charts',
               'note': 'every number plotted comes from judge output files '
                       'regenerated by make_media.sh',
               'files': entries}, f, indent=2)
    f.write('\n')
for e in entries:
    print('  %-10s %9d bytes  %s...' % (e['file'], e['bytes'], e['sha256'][:16]))
PY

echo "make_media: done"
