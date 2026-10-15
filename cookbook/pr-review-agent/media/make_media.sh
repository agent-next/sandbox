#!/usr/bin/env bash
# media/make_media.sh — regenerate every media file from real judge output.
#
# Pipeline (all data written by judge/grade.sh runs in THIS invocation —
# nothing is hand-edited or invented):
#   1. replay the agent loop: four single-edit steps of the known-good
#      artifact (media/replay.py), each graded with its verdict JSON kept
#   2. grade all 10 mutants (judge/mutants.py) for the kill-rate panel
#   3. render result.png and loop.png (make_figures.py, 200 dpi)
#   4. render 1080p cards (make_frames.py), a lossless crf 0 master
#      (media/master/, gitignored) and the web encode demo.mp4
#   5. write MANIFEST.json (sha256 of each shipped file)
#
# Prerequisites: judge/setup.sh has been run once (the pinned pytest venv),
# a python with the pinned matplotlib (media/requirements.txt — e.g.
#   python3 -m venv /tmp/prmedia && /tmp/prmedia/bin/pip install -r \
#       media/requirements.txt   then   PYTHON=/tmp/prmedia/bin/python),
# and ffmpeg.  Fails loudly if anything is missing.

set -euo pipefail

MEDIA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(dirname "$MEDIA_DIR")"
RUNS="$MEDIA_DIR/judge_runs"
REPLAY="$RUNS/replay"
MASTER="$MEDIA_DIR/master"
SEED=42

PY="${PYTHON:-python3}"
if ! "$PY" -c 'import matplotlib' >/dev/null 2>&1; then
    echo "make_media: $PY lacks matplotlib — install the pinned set:" >&2
    echo "  python3 -m venv /tmp/prmedia && /tmp/prmedia/bin/pip install -r media/requirements.txt" >&2
    echo "  PYTHON=/tmp/prmedia/bin/python bash media/make_media.sh" >&2
    exit 1
fi
command -v ffmpeg >/dev/null 2>&1 || { echo "make_media: ffmpeg missing" >&2; exit 1; }
if [ ! -x "${PR_REVIEW_PYTEST_PYTHON:-$HOME/.pr-review-agent/venv/bin/python}" ]; then
    echo "make_media: the pinned pytest venv is missing — run judge/setup.sh first" >&2
    exit 1
fi
"$PY" - <<'PY' || exit 1
import matplotlib, numpy
assert matplotlib.__version__ == '3.10.7', matplotlib.__version__
assert numpy.__version__ == '2.2.6', numpy.__version__
print('[media] matplotlib', matplotlib.__version__, '/ numpy', numpy.__version__)
PY
echo "[media] ffmpeg $(ffmpeg -version | head -1 | awk '{print $3}')"

grade() { bash "$DEMO_DIR/judge/grade.sh" "$@"; }

echo "=== 1. replay the agent loop (four single-edit steps) ==="
rm -rf "$REPLAY"
mkdir -p "$REPLAY/verdicts"
"$PY" -I "$MEDIA_DIR/replay.py" "$DEMO_DIR/examples/good/review" "$REPLAY/iters"
for it in 1 2 3 4; do
    # iterations 1-3 are expected to FAIL a gate (exit 1) — that is the point
    grade "$REPLAY/iters/iter$it" --seed "$SEED" \
        --json "$REPLAY/verdicts/it$it.json" >/dev/null || true
done

echo "=== 2. all 10 mutants (self-test kill-rate panel) ==="
"$PY" -I "$DEMO_DIR/judge/mutants.py" "$DEMO_DIR/examples/good/review" \
    "$REPLAY/mutants" | tail -1
for name in missed-off-by-one wrong-kind-none-deref wrong-line-race \
            downgraded-sql-injection invalid-severity false-positive-on-clean \
            test-passes-on-buggy test-fails-on-fixed test-collection-error \
            test-skipped; do
    grade "$REPLAY/mutants/$name" --seed "$SEED" \
        --json "$REPLAY/mutants/$name.json" >/dev/null 2>&1 || true
done

echo "=== 3. guard: every expected judge output present ==="
for f in "$REPLAY"/verdicts/it{1,2,3,4}.json \
         "$REPLAY"/mutants/{missed-off-by-one,wrong-kind-none-deref,wrong-line-race,downgraded-sql-injection,invalid-severity,false-positive-on-clean,test-passes-on-buggy,test-fails-on-fixed,test-collection-error,test-skipped}.json \
         "$REPLAY/mutants/wrong-line-race/pr4/review.json" \
         "$REPLAY/mutants/wrong-kind-none-deref/pr3/review.json"; do
    [[ -f "$f" ]] || { echo "make_media: MISSING judge output $f" >&2; exit 1; }
done
killed=$(grep -l '"passed": false' "$REPLAY"/mutants/*.json | wc -l)
[[ "$killed" -eq 10 ]] || {
    echo "make_media: expected 10 killed mutants, got $killed" >&2; exit 1; }

echo "=== 4. figures (200 dpi) ==="
"$PY" -I "$MEDIA_DIR/make_figures.py" "$RUNS" "$MEDIA_DIR"

echo "=== 5. video cards (1920x1080) ==="
FRAMES="$(mktemp -d "${TMPDIR:-/tmp}/pr-frames.XXXXXX")"
trap 'rm -rf "$FRAMES"' EXIT
"$PY" -I "$MEDIA_DIR/make_frames.py" "$RUNS" "$FRAMES"

echo "=== 6. lossless master (crf 0, gitignored) + web encode (crf 18) ==="
mkdir -p "$MASTER"
# 10 cards at 0.5 fps = 2 s each = 20 s; fps=30 retimes, tpad holds the last
# card 2 s -> 22 s, inside the 20-60 s standard.
rm -f "$MASTER/pr_review_master.mp4"
ffmpeg -y -loglevel error -framerate 0.5 -i "$FRAMES/frame_%04d.png" \
    -c:v libx264 -preset veryslow -qp 0 -pix_fmt yuv420p \
    -vf "fps=30,tpad=stop_mode=clone:stop_duration=2" \
    -s 1920x1080 "$MASTER/pr_review_master.mp4"
ffmpeg -y -loglevel error -i "$MASTER/pr_review_master.mp4" \
    -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p \
    -movflags +faststart -an "$MEDIA_DIR/demo.mp4"
bytes="$(stat -c%s "$MEDIA_DIR/demo.mp4")"
if [ "$bytes" -gt 5000000 ]; then
    echo "make_media: demo.mp4 is $bytes bytes (> 5 MB repo limit)" >&2
    exit 1
fi

echo "=== 7. MANIFEST.json ==="
"$PY" - "$MEDIA_DIR" "$SEED" <<'PY'
import hashlib, json, os, sys

media, seed = sys.argv[1], sys.argv[2]
spec = {
    'result.png': ('Key figure: (a) G2 localization — reported-minus-planted '
                   'line per defect vs the ±2 pass band, with two G2-killed '
                   'mutants (line +15 off; wrong kind); (b) G4+G5 — the '
                   "reviewer's tests on the buggy and fixed trees; (c) the "
                   'six-gate verdict with numeric evidence.',
                   'bash media/make_media.sh  (make_figures.py)',
                   'media/judge_runs/replay/verdicts/it4.json, '
                   'media/judge_runs/replay/mutants/{wrong-line-race,'
                   'wrong-kind-none-deref}.json + their pr*/review.json'),
    'loop.png': ('The agent loop, replayed: defects caught and majors-on-clean '
                 'per iteration (four single-edit steps, media/replay.py), '
                 'plus the self-test kill-rate panel — known-good vs all 10 '
                 'mutants, each labelled with the gate that killed it.',
                 'bash media/make_media.sh  (make_figures.py)',
                 'media/judge_runs/replay/verdicts/it{1..4}.json, '
                 'media/judge_runs/replay/mutants/*.json'),
    'demo.mp4': ('Step-through of the agent loop (no time-dependent physics '
                 'in this demo): fixture, judge gates, the four replayed '
                 'iterations, the G2/G4+G5 panels, verdict — every number '
                 'from the same verdict JSONs. Lossless crf 0 master in '
                 'git-ignored media/master/.',
                 'bash media/make_media.sh  (make_frames.py + ffmpeg)',
                 'media/judge_runs/replay/verdicts/it{1..4}.json, '
                 'media/judge_runs/replay/mutants/*.json'),
}
entries = []
for fname, (what, cmd, src) in spec.items():
    p = os.path.join(media, fname)
    h = hashlib.sha256(open(p, 'rb').read()).hexdigest()
    entries.append({'file': fname, 'what': what, 'command': cmd,
                    'source_data': src, 'sha256': h,
                    'bytes': os.path.getsize(p)})
with open(os.path.join(media, 'MANIFEST.json'), 'w') as f:
    json.dump({'demo': 'cookbook/pr-review-agent',
               'note': 'every number plotted comes from judge verdict files '
                       f'regenerated by make_media.sh (seed {seed}); figures '
                       'use the validated dataviz reference palette',
               'files': entries}, f, indent=2)
    f.write('\n')
for e in entries:
    print('  %-11s %8d bytes  %s...' % (e['file'], e['bytes'],
                                        e['sha256'][:16]))
PY

echo "make_media: done"
