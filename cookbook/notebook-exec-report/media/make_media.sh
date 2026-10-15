#!/usr/bin/env bash
# media/make_media.sh — regenerate every media file from real judge output.
#
# Pipeline (all data written by judge/grade.sh runs in THIS invocation —
# nothing is hand-edited or invented):
#   1. grade the known-good artifact; its verdict JSON is result.png's data
#   2. generate the 7 known-bad mutants (judge/mutants.py) and grade each
#   3. replay the agent loop: four graded iterations, each one defect away
#      from passing, then the good artifact that passes everything
#   4. render result.png + loop.png (make_figures.py — every plotted
#      number is cross-checked against the verdict JSON or the judge's own
#      oracle refit; any disagreement exits non-zero)
#   5. render the 1080p frame step-through (make_frames.py), a lossless
#      crf-0 master into git-ignored media/master/, and the web encode
#      demo.mp4 (crf 18, yuv420p, faststart)
#   6. write MANIFEST.json (sha256 of each shipped file)
#
# Prerequisite: bash judge/setup.sh (the pinned ~/.judge-venv is the only
# toolchain used here too).  Fails loudly if any expected output is missing.

set -euo pipefail

MEDIA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(dirname "$MEDIA_DIR")"
RUNS="$MEDIA_DIR/judge_runs"
MASTER="$MEDIA_DIR/master"

PY="$HOME/.judge-venv/bin/python"
[ -x "$PY" ] || { echo "make_media: $PY missing — run bash judge/setup.sh first" >&2; exit 1; }
command -v ffmpeg >/dev/null 2>&1 || { echo "make_media: ffmpeg missing" >&2; exit 1; }

echo "[media] toolchain: $("$PY" --version 2>&1), matplotlib" \
     "$("$PY" -c 'import matplotlib;print(matplotlib.__version__)')," \
     "ffmpeg $(ffmpeg -version | head -1 | awk '{print $3}')"

grade() { bash "$DEMO_DIR/judge/grade.sh" "$@"; }

echo "=== 1. grade the known-good artifact ==="
mkdir -p "$RUNS/loop" "$RUNS/mutants"
grade "$DEMO_DIR/examples/good/analysis.ipynb" --json "$RUNS/good.json" \
    >/dev/null
cp "$RUNS/good.json" "$RUNS/loop/05_good.json"

echo "=== 2. the 7 known-bad mutants, each graded ==="
MUTDIR="$(mktemp -d "${TMPDIR:-/tmp}/nb-mutants.XXXXXX")"
trap 'rm -rf "$MUTDIR"' EXIT
"$PY" -I "$DEMO_DIR/judge/mutants.py" \
    "$DEMO_DIR/examples/good/analysis.ipynb" "$MUTDIR" >/dev/null
cp "$DEMO_DIR/examples/good/dataset.csv" "$MUTDIR/dataset.csv"
killed=0
for m in "$MUTDIR"/*.ipynb; do
    name="$(basename "$m" .ipynb)"
    if grade "$m" --json "$RUNS/mutants/$name.json" >/dev/null 2>&1; then
        echo "make_media: SURVIVED $name — kill rate broken, refusing" >&2
        exit 1
    fi
    echo "[media] killed $name"
    killed=$((killed + 1))
done
[ "$killed" -eq 7 ] || { echo "make_media: expected 7 mutants, graded $killed" >&2; exit 1; }

echo "=== 3. replay the agent loop (4 failing iterations, then the pass) ==="
cp "$RUNS/mutants/order-dependence.json"     "$RUNS/loop/01_order-dependence.json"
cp "$RUNS/mutants/nondeterministic-seed.json" "$RUNS/loop/02_nondeterministic-seed.json"
cp "$RUNS/mutants/round-metric.json"          "$RUNS/loop/03_round-metric.json"
cp "$RUNS/mutants/missing-figure.json"        "$RUNS/loop/04_missing-figure.json"
for f in "$RUNS"/loop/*.json; do
    [ -s "$f" ] || { echo "make_media: MISSING loop verdict $f" >&2; exit 1; }
done

echo "=== 4. figures ==="
"$PY" -I "$MEDIA_DIR/make_figures.py" "$DEMO_DIR" "$RUNS" "$MEDIA_DIR"

echo "=== 5. video: frames, lossless master, web encode ==="
FRAMES="$(mktemp -d "${TMPDIR:-/tmp}/nb-frames.XXXXXX")"
# frames dir is cleaned by the same EXIT trap as MUTDIR
trap 'rm -rf "$MUTDIR" "$FRAMES"' EXIT
"$PY" -I "$MEDIA_DIR/make_frames.py" "$DEMO_DIR" "$RUNS" "$FRAMES"
mkdir -p "$MASTER"
rm -f "$MASTER/demo_master.mp4"
# 9 chapters x 5 s at fps 2 = 45 s of video (standard: 20-60 s); the
# master is lossless (qp 0), the web encode re-encodes it untouched.
ffmpeg -y -loglevel error -framerate 2 -i "$FRAMES/frame_%04d.png" \
    -c:v libx264 -preset veryslow -qp 0 -pix_fmt yuv444p \
    -vf "fps=30" -s 1920x1080 "$MASTER/demo_master.mp4"
ffmpeg -y -loglevel error -i "$MASTER/demo_master.mp4" \
    -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p \
    -movflags +faststart -an "$MEDIA_DIR/demo.mp4"

echo "=== 6. MANIFEST.json ==="
"$PY" - "$MEDIA_DIR" <<'PY'
import hashlib, json, os, sys

media = sys.argv[1]
spec = {
    'result.png': ('Key figure: (a) held-out predictions on the test split '
                   'with the G5 rmse_test limit 0.3040, (b) graded split vs '
                   'the five blind refits with the 1.25x-median band, '
                   '(c) coefficient recovery vs the generator-exact W_TRUE '
                   'with the 0.05 limit, (d) reported-vs-refit agreement '
                   'against the G4 tolerances (1e-6 / 1e-9).',
                   'bash media/make_media.sh  (make_figures.py)',
                   'media/judge_runs/good.json'),
    'loop.png': ('The agent loop, replayed: which judge gate failed at each '
                 'of four graded iterations (one defect fixed per iteration) '
                 'until the artifact passes everything; plus the self-test '
                 'kill-rate bar (known-good vs all 7 known-bad mutants).',
                 'bash media/make_media.sh  (make_figures.py)',
                 'media/judge_runs/loop/*.json, media/judge_runs/mutants/*.json'),
    'demo.mp4': ('Step-through of the demo: the graded artifact, the '
                 'independent refit, the four key figures with their pass '
                 'lines, the self-test kill rate, the final verdict. '
                 'Lossless crf-0 master in git-ignored media/master/.',
                 'bash media/make_media.sh  (make_frames.py + ffmpeg)',
                 'media/judge_runs/good.json, media/judge_runs/mutants/*.json'),
}
entries = []
for fname, (what, cmd, src) in spec.items():
    p = os.path.join(media, fname)
    h = hashlib.sha256(open(p, 'rb').read()).hexdigest()
    entries.append({'file': fname, 'what': what, 'command': cmd,
                    'source_data': src, 'sha256': h,
                    'bytes': os.path.getsize(p)})
with open(os.path.join(media, 'MANIFEST.json'), 'w') as f:
    json.dump({'demo': 'cookbook/notebook-exec-report',
               'note': 'every plotted number comes from judge verdict JSONs '
                       'written by grade.sh runs in this make_media.sh '
                       'invocation (seed 20261015, alpha 10)',
               'files': entries}, f, indent=2)
    f.write('\n')
for e in entries:
    print('  %-12s %9d bytes  %s...' % (e['file'], e['bytes'],
                                        e['sha256'][:16]))
PY

echo "make_media: done"
