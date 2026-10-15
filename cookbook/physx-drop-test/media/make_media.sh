#!/usr/bin/env bash
# make_media.sh — regenerate every media file from real judge outputs.
#
#   media/result.png     measured trajectory vs the analytic oracle (3 panels)
#   media/loop.png       agent-loop replay + mutant x gate kill matrix
#   media/demo.mp4       43 s storyboard video (media/STORYBOARD.md), cut
#                        from a lossless crf-0 master in media/master/
#                        (git-ignored, per DEMO-STANDARD.md)
#   media/result.json    the demo result manifest (agent-next/result@1)
#   media/MANIFEST.json  what each file shows, its command, sources, sha256
#
# Raw judge outputs land in media/judge_runs/ (git-ignored) via
# make_judge_runs.sh: nothing is drawn that the judge did not produce, and
# every number on screen traces to a verdict JSON or traj.npz sample.
# media/REVIEW.json (the blind review panel of DEMO-STANDARD.md) records
# verdicts from vision models and is not machine-regenerated; it is listed
# in MANIFEST.json only once it exists.
#
# Usage: bash media/make_media.sh [--seed N]     (default seed 42)
# Requires: judge/setup.sh already run (the judge venv) and ffmpeg on PATH
# (distro build; version recorded in MANIFEST.json).
# Exit codes: 0 ok, 1 a judge/media step failed, 2 environment missing.

set -euo pipefail

MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$MEDIA/.." && pwd)"
REPO="$(cd "$DEMO/../.." && pwd)"
VENV="${PHYSX_DROP_TEST_VENV:-$HOME/.venvs/physx-drop-test}"
MPY="$MEDIA/.venv/bin/python"          # pinned matplotlib venv

log() { echo "[media] $*"; }
die() { echo "[media] ERROR: $*" >&2; exit "${2:-1}"; }

SEED=42
while [[ $# -gt 0 ]]; do
    case "$1" in
        --seed) SEED="$2"; shift 2 ;;
        *) die "usage: $0 [--seed N]" 2 ;;
    esac
done

# --- environment ------------------------------------------------------------
command -v ffmpeg >/dev/null || die "ffmpeg missing (distro package)" 2
[[ -x "$VENV/bin/python" ]] || die "judge venv missing at $VENV — run judge/setup.sh first" 2
if [[ ! -x "$MPY" ]]; then
    log "creating pinned media venv at $MEDIA/.venv (media/requirements.txt)"
    python3 -m venv "$MEDIA/.venv"
    "$MEDIA/.venv/bin/pip" install -q -r "$MEDIA/requirements.txt"
fi
log "python3 $($MPY -c 'import platform;print(platform.python_version())'), \
matplotlib $($MPY -c 'import matplotlib;print(matplotlib.__version__)'), \
ffmpeg $(ffmpeg -version | awk 'NR==1{print $3}' | tr -d ')')"

# --- 1. raw judge outputs (verdicts, traces, a timed self-test) --------------
log "regenerating judge outputs (media/judge_runs/, seed $SEED)"
bash "$MEDIA/make_judge_runs.sh" --seed "$SEED"

# --- 2. figures ---------------------------------------------------------------
log "rendering result.png and loop.png"
"$MPY" "$MEDIA/make_figures.py"

# --- 3. video: frames -> lossless master -> crf 18 web encode -----------------
log "rendering demo.mp4 (media/STORYBOARD.md)"
"$MPY" "$MEDIA/make_video.py"

# --- 4. manifests (result.json + MANIFEST.json) -------------------------------
log "writing result.json and MANIFEST.json"
"$MPY" "$MEDIA/make_manifests.py" --seed "$SEED"

# --- 5. machine gates ---------------------------------------------------------
log "video gate (cookbook/tools/video_gate.py)"
python3 "$REPO/cookbook/tools/video_gate.py" "$MEDIA/demo.mp4" \
    --json "$MEDIA/judge_runs/video_gate.json"
log "result manifest check (cookbook/tools/result.py)"
python3 "$REPO/cookbook/tools/result.py" check "$MEDIA/result.json" --root "$DEMO"

log "done: result.png, loop.png, demo.mp4, result.json, MANIFEST.json"
