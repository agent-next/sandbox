#!/usr/bin/env bash
# media/make_media.sh — regenerate every media file from real judge output.
#
# Pipeline (all data written by judge/grade.sh / judge/mutants.py runs in
# THIS invocation — nothing is hand-edited or invented):
#   1. replay the agent loop: bad -> partly fixed -> good, each graded with
#      its verdict JSON kept; the good cavity case also gets --trace output
#      (residuals.csv, cellcentres.csv, saved time dirs) for the video.
#      All stdout is tee'd to judge_runs/agent_run.log — that real log is
#      the terminal footage in the "agent sandbox run" segment.
#   2. grade the good poiseuille case with --trace (profile + convergence)
#   3. grade all 10 mutants (self-test kill-rate bars)
#   4. render result.png and loop.png (matplotlib)
#   5. render the motion clips: |U| interpolated between the saved solver
#      snapshots + RK2 tracer particles (numpy/PIL), encoded by ffmpeg into
#      media/clips/ at 30 fps — and write clips/data.json, the Remotion
#      props, from this run's verdict JSONs
#   6. Remotion render (headless Chrome, PNG sequence) composing the clips
#      with the animated HUD, then ffmpeg encodes the lossless crf 0
#      master (media/master/, gitignored) and the web encode demo.mp4
#   7. write MANIFEST.json (sha256 of each shipped file)
#
# Fails loudly if any expected judge output is missing.

set -euo pipefail

MEDIA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(dirname "$MEDIA_DIR")"
RUNS="$MEDIA_DIR/judge_runs"
REPLAY="$RUNS/replay"
MASTER="$MEDIA_DIR/master"
CLIPS="$MEDIA_DIR/clips"
VIDEO="$MEDIA_DIR/video"

PY="${PYTHON:-python3}"
if ! "$PY" -c 'import matplotlib' >/dev/null 2>&1; then
    echo "make_media: python3 lacks matplotlib — install the pinned set:" >&2
    echo "  python3 -m venv /tmp/ofmedia && /tmp/ofmedia/bin/pip install \\" >&2
    echo "      --require-hashes -r judge/requirements.txt" >&2
    echo "  PYTHON=/tmp/ofmedia/bin/python bash media/make_media.sh" >&2
    exit 1
fi
command -v ffmpeg >/dev/null 2>&1 || { echo "make_media: ffmpeg missing" >&2; exit 1; }
command -v node >/dev/null 2>&1 || { echo "make_media: node >= 22 required (Remotion)" >&2; exit 1; }
command -v npx >/dev/null 2>&1 || { echo "make_media: npx required (Remotion)" >&2; exit 1; }

# Pinned tool versions (must match judge/requirements.txt and VERSIONS.txt;
# versions.sh records what is actually installed).
"$PY" - <<'PY' || exit 1
import matplotlib
assert matplotlib.__version__ == '3.8.4', matplotlib.__version__
print('[media] matplotlib', matplotlib.__version__)
PY
echo "[media] ffmpeg $(ffmpeg -version | head -1 | awk '{print $3}')"
echo "[media] node $(node --version)"

grade() { bash "$DEMO_DIR/judge/grade.sh" "$@"; }

# The real stdout/stderr of this run becomes the terminal footage.
mkdir -p "$RUNS"
exec > >(tee "$RUNS/agent_run.log") 2>&1

echo "=== 1. replay: known-bad -> partly fixed -> good (cavity) ==="
mkdir -p "$REPLAY/verdicts" "$REPLAY/mutants"
"$PY" "$DEMO_DIR/judge/mutants.py"
# NOTE: verdict JSONs are left on stdout on purpose — they are the real
# terminal footage that the "agent run" clip scrolls.
grade "$DEMO_DIR/examples/bad/cavity_wrong_lid" \
    --json "$REPLAY/verdicts/01_cavity_wrong_lid.json" --seed 42 || true
grade "$DEMO_DIR/examples/bad/cavity_unconverged" \
    --json "$REPLAY/verdicts/02_cavity_unconverged.json" --seed 42 || true
grade "$DEMO_DIR/examples/bad/cavity_coarse_mesh" \
    --json "$REPLAY/verdicts/03_cavity_coarse_mesh.json" --seed 42 || true
rm -rf "$REPLAY/cavity_traces"
grade "$DEMO_DIR/examples/good/cavity" \
    --json "$REPLAY/verdicts/04_cavity_good.json" --seed 42 \
    --trace "$REPLAY/cavity_traces"

echo "=== 2. good poiseuille with trace ==="
rm -rf "$REPLAY/poiseuille_traces"
grade "$DEMO_DIR/examples/good/poiseuille" \
    --json "$REPLAY/verdicts/05_poiseuille_good.json" --seed 42 \
    --trace "$REPLAY/poiseuille_traces"

echo "=== 3. all mutants (kill-rate bars) ==="
for m in poiseuille_wrong_bc poiseuille_wrong_viscosity poiseuille_coarse_mesh \
         poiseuille_unconverged poiseuille_wrong_outlet cavity_wrong_lid \
         cavity_wrong_viscosity cavity_coarse_mesh cavity_unconverged \
         cavity_slip_wall; do
    grade "$DEMO_DIR/examples/bad/$m" \
        --json "$REPLAY/mutants/$m.json" --seed 42 || true
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
    "$REPLAY/poiseuille_traces/residuals.csv" \
    "$RUNS/agent_run.log"; do
    [[ -f "$f" ]] || { echo "make_media: MISSING trace output $f" >&2; exit 1; }
done
N_MUT=$(ls "$REPLAY/mutants"/*.json 2>/dev/null | wc -l)
[[ "$N_MUT" -eq 10 ]] || { echo "make_media: expected 10 mutant verdicts, got $N_MUT" >&2; exit 1; }

echo "=== 5. figures ==="
"$PY" -I "$MEDIA_DIR/make_figures.py" "$REPLAY" "$MEDIA_DIR"

echo "=== 6. motion clips + Remotion props (real solver output) ==="
"$PY" -I "$VIDEO/render_clips.py" \
    "$REPLAY/cavity_traces" "$RUNS/agent_run.log" "$CLIPS"
"$PY" -I "$VIDEO/write_data.py" "$REPLAY" "$CLIPS"

echo "=== 7. Remotion render (PNG sequence -> lossless master -> web) ==="
cd "$VIDEO"
if [[ ! -d node_modules/remotion ]]; then
    npm ci --no-audit --no-fund
fi
npx remotion browser ensure >/dev/null 2>&1 || true
rm -rf out/seq
npx remotion render Compositions out/seq --sequence \
    --public-dir="$CLIPS" --props="$CLIPS/data.json"
mkdir -p "$MASTER"
rm -f "$MASTER/cavity_master.mp4"
# element-NNN.png: Remotion zero-pads to the frame count's width — glob, do
# not hardcode %04d.
ffmpeg -y -loglevel error -framerate 30 \
    -pattern_type glob -i 'out/seq/element-*.png' \
    -c:v libx264 -preset veryslow -crf 0 -pix_fmt yuv420p \
    -s 1920x1080 "$MASTER/cavity_master.mp4"
cd "$MEDIA_DIR"

echo "=== 8. web encode (crf 18, faststart, <= 8 MiB) ==="
# The gate caps demo.mp4 at 8 MiB.  crf 18 at preset veryslow usually lands
# under it for this footage; if the master is busier than expected, fall
# back to a two-pass encode sized to 7.6 MiB rather than ship a gate fail.
ffmpeg -y -loglevel error -i "$MASTER/cavity_master.mp4" \
    -c:v libx264 -preset veryslow -crf 18 -pix_fmt yuv420p \
    -movflags +faststart -an "$MEDIA_DIR/demo.mp4"
MAX_BYTES=$((8 * 1024 * 1024))
if [[ $(stat -c %s "$MEDIA_DIR/demo.mp4") -gt $MAX_BYTES ]]; then
    DUR=$(ffprobe -v error -show_entries format=duration \
        -of csv=p=0 "$MASTER/cavity_master.mp4")
    # 7.6 MiB target, minus a 5 % container headroom, in kbit/s.
    BR=$(awk -v d="$DUR" 'BEGIN{printf "%dk", (7.6*8*1024*1024/d)*0.95/1000}')
    echo "[media] crf 18 encode exceeded 8 MiB; two-pass at $BR"
    ffmpeg -y -loglevel error -i "$MASTER/cavity_master.mp4" \
        -c:v libx264 -preset slow -b:v "$BR" -pix_fmt yuv420p \
        -pass 1 -passlogfile "$MASTER/2pass" -an -f null /dev/null
    ffmpeg -y -loglevel error -i "$MASTER/cavity_master.mp4" \
        -c:v libx264 -preset slow -b:v "$BR" -pix_fmt yuv420p \
        -pass 2 -passlogfile "$MASTER/2pass" \
        -movflags +faststart -an "$MEDIA_DIR/demo.mp4"
fi

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
    'demo.mp4': ('Cavity |U| developing over pseudo-time with tracer '
                 'particles advected through the real icoFoam field '
                 '(judge --trace), camera close-ups, the scrolling log of '
                 'the judge run itself and a PASS HUD — composed by '
                 'Remotion 4.0.531; lossless crf 0 master in git-ignored '
                 'media/master/.',
                 'bash media/make_media.sh  (render_clips.py + Remotion '
                 '+ ffmpeg)',
                 'media/judge_runs/replay/cavity_traces/, '
                 'media/judge_runs/agent_run.log, media/clips/data.json'),
}
for fname, (what, cmd, src) in spec.items():
    p = os.path.join(media, fname)
    h = hashlib.sha256(open(p, 'rb').read()).hexdigest()
    entries.append({'file': fname, 'what': what, 'command': cmd,
                    'source_data': src, 'sha256': h,
                    'bytes': os.path.getsize(p)})
with open(os.path.join(media, 'MANIFEST.json'), 'w') as f:
    json.dump({'demo': 'cookbook/cfd-openfoam',
               'note': 'every number plotted or on screen comes from judge '
                       'output files regenerated by make_media.sh (seed 42)',
               'files': entries}, f, indent=2)
    f.write('\n')
for e in entries:
    print('  %-10s %9d bytes  %s...' % (e['file'], e['bytes'], e['sha256'][:16]))
PY

echo "make_media: done"
