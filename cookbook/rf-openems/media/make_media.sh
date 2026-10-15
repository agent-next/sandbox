#!/bin/bash
# Rebuild every media artifact from the committed judge outputs in
# media/data/ (collected by make_data.sh -- real grade.sh runs plus one
# selftest; nothing here re-runs the solver).
#
#   data/verdicts/*.json   committed verdict JSONs (grade.sh --json)
#   data/traces/*.csv      grade.py --trace S11 sweeps (grader's own
#                          output, the judge's re-derivation, fine mesh)
#   data/selftest.txt      one full judge/selftest.sh run
#   result.png loop.png    matplotlib figures
#   demo.mp4               cards -> lossless master (crf 0, git-ignored
#                          media/master/) -> H.264 web encode
#   MANIFEST.json          sha256 + provenance for each file
#
# Requires judge/setup.sh already run (openEMS env provides python3.11
# with the pinned matplotlib + the pinned static ffmpeg via env.sh);
# falls back to the distro ffmpeg. No venv: the toolchain is the judge's
# own pinned one, so the figures and the judge share exact versions.
set -euo pipefail
MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$MEDIA")"
cd "$DEMO"

die() { echo "make_media: $*" >&2; exit 1; }

# --- toolchain (the judge's pinned environment) ----------------------------
if [ ! -f "${RF_OPENEMS_HOME:-$HOME/.rf-openems}/sysroot/.debs_done" ]; then
    die "judge env missing; run judge/setup.sh first"
fi
source judge/env.sh
FFMPEG_BIN="${RF_FFMPEG:-$(command -v ffmpeg || true)}"
[ -n "$FFMPEG_BIN" ] || die "ffmpeg missing (judge/setup.sh or distro)"
export RF_FFMPEG="$FFMPEG_BIN"
"$RF_PY" -c 'import matplotlib, numpy' 2>/dev/null \
    || die "matplotlib/numpy missing in the judge env"

# --- judge outputs (must exist; never re-run the solver here) ---------------
for f in good bad_nan_er bad_substrate_er bad_thick_substrate \
         bad_coarse_mesh bad_patch_length bad_no_ground bad_feed_center \
         bad_no_result bad_lie_scalars bad_replay_cached bad_fake_curve \
         bad_oracle_tamper bad_fine_geometry bad_fine_fabricated \
         bad_plant_pyc; do
    [ -s "media/data/verdicts/$f.json" ] || die "missing verdict $f.json"
done
for t in good__s11_artifact good__s11_judge good__s11_fine \
         bad_patch_length__s11_artifact bad_no_ground__s11_artifact \
         bad_feed_center__s11_artifact; do
    [ -s "media/data/traces/$t.csv" ] || die "missing trace $t.csv"
done
[ -s media/data/selftest.txt ] || die "missing media/data/selftest.txt"

# --- figures ----------------------------------------------------------------
echo "== result.png =="
"$RF_PY" media/fig_result.py
echo "== loop.png =="
"$RF_PY" media/fig_loop.py

# --- video ------------------------------------------------------------------
echo "== demo.mp4 (lossless master + web encode) =="
"$RF_PY" media/make_video.py

# --- manifest ----------------------------------------------------------------
echo "== MANIFEST.json =="
"$RF_PY" media/manifest.py
echo "make_media: done -> $MEDIA/{result.png,loop.png,demo.mp4,MANIFEST.json}"
