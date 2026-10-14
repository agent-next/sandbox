#!/usr/bin/env bash
# media/make_media.sh — regenerate every media file from real judge output.
#
# Pipeline (all data written by judge/grade.sh / judge/mutants.py runs in
# THIS invocation — nothing is hand-edited or invented):
#   1. replay the agent loop: bad -> partly fixed -> good, each graded with
#      its verdict JSON kept; the good cavity case also gets --trace output
#      (residuals.csv, cellcentres.csv, saved time dirs) for the video
#   2. grade the good poiseuille case with --trace (profile + convergence)
#   3. grade all 10 mutants (self-test kill-rate bars)
#   4. render result.png, loop.png, the video frames, a lossless crf 0
#      master (media/master/, gitignored) and the web encode demo.mp4
#   5. write MANIFEST.json (sha256 of each shipped file)
#
# Fails loudly if any expected judge output is missing.

set -euo pipefail

MEDIA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(dirname "$MEDIA_DIR")"
RUNS="$MEDIA_DIR/judge_runs"
REPLAY="$RUNS/replay"
MASTER="$MEDIA_DIR/master"

PY="${PYTHON:-python3}"
if ! "$PY" -c 'import matplotlib' >/dev/null 2>&1; then
    echo "make_media: python3 lacks matplotlib — install the pinned set:" >&2
    echo "  python3 -m venv /tmp/ofmedia && /tmp/ofmedia/bin/pip install \\" >&2
    echo "      --require-hashes -r judge/requirements.txt" >&2
    echo "  PYTHON=/tmp/ofmedia/bin/python bash media/make_media.sh" >&2
    exit 1
fi
command -v ffmpeg >/dev/null 2>&1 || { echo "make_media: ffmpeg missing" >&2; exit 1; }

# Pinned tool versions (must match judge/requirements.txt and VERSIONS.txt;
# versions.sh records what is actually installed).
"$PY" - <<'PY' || exit 1
import matplotlib
assert matplotlib.__version__ == '3.8.4', matplotlib.__version__
print('[media] matplotlib', matplotlib.__version__)
PY
echo "[media] ffmpeg $(ffmpeg -version | head -1 | awk '{print $3}')"

grade() { bash "$DEMO_DIR/judge/grade.sh" "$@"; }

echo "=== 1. replay: known-bad -> partly fixed -> good (cavity) ==="
mkdir -p "$REPLAY/verdicts" "$REPLAY/mutants"
"$PY" "$DEMO_DIR/judge/mutants.py"
grade "$DEMO_DIR/examples/bad/cavity_wrong_lid" \
    --json "$REPLAY/verdicts/01_cavity_wrong_lid.json" --seed 42 \
    >/dev/null 2>&1 || true
grade "$DEMO_DIR/examples/bad/cavity_unconverged" \
    --json "$REPLAY/verdicts/02_cavity_unconverged.json" --seed 42 \
    >/dev/null 2>&1 || true
grade "$DEMO_DIR/examples/bad/cavity_coarse_mesh" \
    --json "$REPLAY/verdicts/03_cavity_coarse_mesh.json" --seed 42 \
    >/dev/null 2>&1 || true
rm -rf "$REPLAY/cavity_traces"
grade "$DEMO_DIR/examples/good/cavity" \
    --json "$REPLAY/verdicts/04_cavity_good.json" --seed 42 \
    --trace "$REPLAY/cavity_traces" >/dev/null

echo "=== 2. good poiseuille with trace ==="
rm -rf "$REPLAY/poiseuille_traces"
grade "$DEMO_DIR/examples/good/poiseuille" \
    --json "$REPLAY/verdicts/05_poiseuille_good.json" --seed 42 \
    --trace "$REPLAY/poiseuille_traces" >/dev/null

echo "=== 3. all mutants (kill-rate bars) ==="
for m in poiseuille_wrong_bc poiseuille_wrong_viscosity poiseuille_coarse_mesh \
         poiseuille_unconverged poiseuille_wrong_outlet cavity_wrong_lid \
         cavity_wrong_viscosity cavity_coarse_mesh cavity_unconverged \
         cavity_slip_wall; do
    grade "$DEMO_DIR/examples/bad/$m" \
        --json "$REPLAY/mutants/$m.json" --seed 42 >/dev/null 2>&1 || true
done

echo "=== 4. guard: every expected judge output present ==="
for f in \
    "$REPLAY/verdicts/01_cavity_wrong_lid.json" \
    "$REPLAY/verdicts/02_cavity_unconverged.json" \
    "$REPLAY/verdicts/03_cavity_coarse_mesh.json" \
    "$REPLAY/verdicts/04_cavity_good.json" \
    "$REPLAY/verdicts/05_poiseuille_good.json" \
    "$REPLAY/cavity_traces/residuals.csv" \
    "$REPLAY/cavity_traces/cellcentres.csv" \
    "$REPLAY/cavity_traces/samples/centerline_u_U.xy" \
    "$REPLAY/cavity_traces/samples/centerline_v_U.xy" \
    "$REPLAY/cavity_traces/30/U" \
    "$REPLAY/poiseuille_traces/samples/centerline_U.xy" \
    "$REPLAY/poiseuille_traces/residuals.csv"; do
    [[ -f "$f" ]] || { echo "make_media: MISSING trace output $f" >&2; exit 1; }
done
N_MUT=$(ls "$REPLAY/mutants"/*.json 2>/dev/null | wc -l)
[[ "$N_MUT" -eq 10 ]] || { echo "make_media: expected 10 mutant verdicts, got $N_MUT" >&2; exit 1; }

echo "=== 5. figures ==="
"$PY" -I "$MEDIA_DIR/make_figures.py" "$REPLAY" "$MEDIA_DIR"

echo "=== 6. video frames (lossless PNG) ==="
FRAMES="$(mktemp -d "${TMPDIR:-/tmp}/of-frames.XXXXXX")"
trap 'rm -rf "$FRAMES"' EXIT
"$PY" -I "$MEDIA_DIR/make_frames.py" "$REPLAY/cavity_traces" "$FRAMES"

echo "=== 7. lossless master (crf 0, gitignored) ==="
mkdir -p "$MASTER"
# 0.5 s of wall clock per pseudo-time snapshot -> 60 snapshots = 30 s of
# video, inside the 20-60 s standard.  Master is lossless (qp 0); the web
# encode reuses the timeline untouched.
rm -f "$MASTER/cavity_master.mp4"
# input holds exactly the 60 traced snapshots (0.5 s wall each = 30 s);
# fps=30 duplicates each to the output rate, tpad holds the last frame 3 s
# -> 33 s total, inside the 20-60 s standard.
ffmpeg -y -loglevel error -framerate 2 -i "$FRAMES/frame_%04d.png" \
    -c:v libx264 -preset veryslow -qp 0 -pix_fmt yuv420p \
    -vf "fps=30,tpad=stop_mode=clone:stop_duration=3" \
    -s 1920x1080 "$MASTER/cavity_master.mp4"

echo "=== 8. web encode (crf 18 preset slow, faststart) ==="
ffmpeg -y -loglevel error -i "$MASTER/cavity_master.mp4" \
    -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p \
    -movflags +faststart -an "$MEDIA_DIR/demo.mp4"

echo "=== 9. MANIFEST.json ==="
"$PY" - "$MEDIA_DIR" <<'PY'
import hashlib, json, os, sys

media = sys.argv[1]
entries = []
spec = {
    'result.png': ('Key figure: (a) Poiseuille centreline u(y) vs the '
                   'analytic parabola with the 2 % L2 pass band (gate 3), '
                   '(b) cavity centreline u/v vs Ghia et al. 1982 (gate 5), '
                   '(c) mesh-convergence log-log with fitted order vs the '
                   'order >= 1.5 gate (gate 4), (d) cavity |U| at t = 30 s.',
                   'bash media/make_media.sh  (make_figures.py)',
                   'media/judge_runs/replay/verdicts/*.json, '
                   'media/judge_runs/replay/{cavity,poiseuille}_traces/'),
    'loop.png': ('The agent loop, replayed: the gate-5 metric per replayed '
                 'iteration (each iteration fixes the gate the previous one '
                 'failed) plus the self-test kill-rate bar for all 10 '
                 'mutants.', 'bash media/make_media.sh  (make_figures.py)',
                 'media/judge_runs/replay/verdicts/*.json, '
                 'media/judge_runs/replay/mutants/*.json'),
    'demo.mp4': ('Cavity flow developing over pseudo-time: |U| field from '
                 'the saved time directories of a real icoFoam run, with '
                 'the gate-2 residual convergence; lossless crf 0 master in '
                 'git-ignored media/master/.',
                 'bash media/make_media.sh  (make_frames.py + ffmpeg)',
                 'media/judge_runs/replay/cavity_traces/'),
}
for fname, (what, cmd, src) in spec.items():
    p = os.path.join(media, fname)
    h = hashlib.sha256(open(p, 'rb').read()).hexdigest()
    entries.append({'file': fname, 'what': what, 'command': cmd,
                    'source_data': src, 'sha256': h,
                    'bytes': os.path.getsize(p)})
with open(os.path.join(media, 'MANIFEST.json'), 'w') as f:
    json.dump({'demo': 'cookbook/cfd-openfoam',
               'note': 'every number plotted comes from judge output files '
                       'regenerated by make_media.sh (seed 42)',
               'files': entries}, f, indent=2)
    f.write('\n')
for e in entries:
    print('  %-10s %9d bytes  %s...' % (e['file'], e['bytes'], e['sha256'][:16]))
PY

echo "make_media: done"
