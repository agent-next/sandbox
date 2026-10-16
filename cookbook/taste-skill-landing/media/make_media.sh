#!/usr/bin/env bash
# media/make_media.sh — regenerate every media file for this demo.
#
#   1. browser frames     media/make_frames.py (judge venv python)
#   2. verdict JSONs      judge/grade.sh on both example sites (seed 42)
#   3. judge self-test    judge/selftest.sh -> real mutant kill count
#   4. HUD facts          media/make_facts.py -> media/video/src/facts.json
#   5. motion clips       media/record_clips.py -> media/clips/*.mp4 (gitignored)
#   6. demo.mp4           Remotion composition in media/video (clips -> render
#                         -> encode). ffmpeg only encodes; it never builds the
#                         visuals. The composition lives in media/video/src.
#   7. media/MANIFEST.json  per file: what it shows, the command, sha256
#
# Needs: the judge toolchain (bash judge/setup.sh), Node >= 22 + npm for the
# Remotion render (media/video/package-lock.json pins it), and ffmpeg/ffprobe
# on PATH.
#
# Usage: bash media/make_media.sh [--skip-frames] [--skip-grade]
#                                  [--skip-clips] [--skip-render]

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="$(dirname "$HERE")"
VENV_PY="$HOME/.taste-judge/venv/bin/python"
FPS=30

SKIP_FRAMES=0; SKIP_GRADE=0; SKIP_CLIPS=0; SKIP_RENDER=0
for a in "$@"; do
    case "$a" in
        --skip-frames) SKIP_FRAMES=1 ;;
        --skip-grade)  SKIP_GRADE=1 ;;
        --skip-clips)  SKIP_CLIPS=1 ;;
        --skip-render) SKIP_RENDER=1 ;;
        *) echo "usage: $0 [--skip-frames] [--skip-grade] [--skip-clips] [--skip-render]" >&2; exit 2 ;;
    esac
done

command -v ffmpeg >/dev/null || { echo "[media] ffmpeg not on PATH" >&2; exit 2; }
[[ -x "$VENV_PY" ]] || { echo "[media] $VENV_PY missing — run bash judge/setup.sh first" >&2; exit 2; }

# ---------------------------------------------------------------- frames
if [[ $SKIP_FRAMES -eq 0 ]]; then
    echo "[media] frames: headless Chromium captures of the fixed good site"
    "$VENV_PY" "$HERE/make_frames.py" --out "$HERE"
fi

# ---------------------------------------------------------------- verdicts
WORK="$(mktemp -d "${TMPDIR:-/tmp}/taste-media.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

if [[ $SKIP_GRADE -eq 0 ]]; then
    echo "[media] verdicts: grade.sh examples/{good,baseline}/site --seed 42"
    bash "$BASE/judge/grade.sh" "$BASE/examples/good/site" --seed 42 \
        --json "$WORK/good.json" >"$WORK/good.log" 2>&1
    bash "$BASE/judge/grade.sh" "$BASE/examples/baseline/site" --seed 42 \
        --json "$WORK/base.json" >"$WORK/base.log" 2>&1 || true
    echo "[media] selftest: judge/selftest.sh (real kill count for the HUD)"
    bash "$BASE/judge/selftest.sh" >"$WORK/selftest.log" 2>&1 || {
        echo "[media] selftest.sh failed — last lines:" >&2
        tail -20 "$WORK/selftest.log" >&2; exit 1; }
    KILLS="$(grep 'mutants killed' "$WORK/selftest.log" | tail -1 \
        | sed -E 's/.*mutants killed *: *//')"
    [[ -n "$KILLS" ]] || {
        echo "[media] no kill count in selftest output" >&2; exit 1; }
    # cache for --skip-grade reruns
    cp "$WORK/good.json" "$HERE/verdict-good.json"
    cp "$WORK/base.json" "$HERE/verdict-baseline.json"
    echo "$KILLS" > "$HERE/selftest-kills.txt"
else
    cp "$HERE/verdict-good.json" "$WORK/good.json" 2>/dev/null || true
    cp "$HERE/verdict-baseline.json" "$WORK/base.json" 2>/dev/null || true
    KILLS="$(cat "$HERE/selftest-kills.txt" 2>/dev/null || true)"
fi
[[ -f "$WORK/good.json" && -f "$WORK/base.json" ]] || {
    echo "[media] no verdict JSONs — run without --skip-grade" >&2; exit 2; }
[[ -n "$KILLS" ]] || {
    echo "[media] no selftest kill count — run without --skip-grade" >&2
    exit 2; }

# ---------------------------------------------------------------- HUD facts
echo "[media] facts: make_facts.py -> media/video/src/facts.json"
python3 "$HERE/make_facts.py" \
    --good "$WORK/good.json" --base "$WORK/base.json" \
    --kills "$HERE/selftest-kills.txt" \
    --out "$HERE/video/src/facts.json"

# ---------------------------------------------------------------- motion clips
if [[ $SKIP_CLIPS -eq 0 ]]; then
    echo "[media] clips: record_clips.py — real headless Chromium recordings"
    mkdir -p "$HERE/clips"
    "$VENV_PY" "$HERE/record_clips.py" --out "$HERE/clips" \
        --good-verdict "$WORK/good.json" \
        --baseline-verdict "$WORK/base.json"
fi
# the composition reads the clips through this symlink (Remotion serves
# media/video/public/); keep it pointing at the recording dir
ln -sfn ../../clips "$HERE/video/public/clips"
missing=0
for c in scroll-hero site-scroll-full site-scroll-slow brief-scroll \
         widget-scrub resp-375 resp-768 resp-1440 baseline-scroll \
         grade-run; do
    [[ -f "$HERE/clips/$c.mp4" ]] || { echo "[media] missing clip $c.mp4" >&2; missing=1; }
done
[[ $missing -eq 0 ]] || { echo "[media] record clips first (--skip-clips not used?)" >&2; exit 2; }

# ---------------------------------------------------------------- video
if [[ $SKIP_RENDER -eq 0 ]]; then
    echo "[media] demo.mp4: Remotion render (media/video), then encode"
    command -v node >/dev/null || { echo "[media] node not on PATH (need >= 22)" >&2; exit 2; }
    cd "$HERE/video"
    if [[ ! -d node_modules ]]; then npm ci --no-audit --no-fund; fi
    # Remotion bundles and renders; ffmpeg does not build any visual.
    npx remotion render Kestrel out/demo-master.mp4 \
        --codec=h264 --crf=18 --pixel-format=yuv420p --concurrency=2
    cd "$HERE"
    # final encode: H.264 yuv420p CRF 18 + faststart (the gate's contract)
    ffmpeg -hide_banner -loglevel error -y -i "$HERE/video/out/demo-master.mp4" \
        -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p \
        -movflags +faststart "$HERE/demo.mp4"
else
    echo "[media] demo.mp4: skipped (--skip-render); using existing file"
fi

SZ=$(stat -c %s "$HERE/demo.mp4")
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$HERE/demo.mp4")
echo "[media] demo.mp4: $((SZ / 1024)) KiB, ${DUR}s"
[[ $SZ -lt $((8 * 1024 * 1024)) ]] || {
    echo "[media] ERROR: demo.mp4 over the 8 MB budget" >&2; exit 1; }

# ---------------------------------------------------------------- manifest
python3 - "$HERE" <<'PY'
import hashlib, json, os, sys
here = sys.argv[1]
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
entries = []
for name in sorted(os.listdir(here)):
    if not (name.endswith(".png") or name == "demo.mp4"):
        continue
    path = os.path.join(here, name)
    if name.startswith("site-"):
        w = name[5:-4]
        what, cmd, src = (
            f"full-page screenshot of examples/good/site at {w} px",
            "~/.taste-judge/venv/bin/python media/make_frames.py",
            "examples/good/site (fixed wind math), Chromium 153 headless")
    elif name.startswith("scroll-"):
        what, cmd, src = (
            f"scroll-capture frame {name[7:-4]}/09 at 1440x900",
            "~/.taste-judge/venv/bin/python media/make_frames.py",
            "examples/good/site (fixed wind math), Chromium 153 headless")
    else:
        what, cmd, src = (
            "44 s animated demo: real moving browser recordings (scroll, "
            "hover, responsive, widget drag) composited by Remotion with an "
            "animated HUD; a static end card is the only still window",
            "bash media/make_media.sh",
            "media/clips/*.mp4 (gitignored Playwright recordings) + "
            "media/video/src (Remotion) + this run's grade.sh/selftest.sh facts")
    entries.append({"file": name, "shows": what, "command": cmd,
                    "source": src, "sha256": sha(path)})
# the committed sample frames, if present
frames_dir = os.path.join(here, "frames")
if os.path.isdir(frames_dir):
    for name in sorted(os.listdir(frames_dir)):
        if not name.endswith(".jpg"):
            continue
        path = os.path.join(frames_dir, name)
        entries.append({
            "file": "frames/" + name,
            "shows": f"sample frame from demo.mp4 ({name})",
            "command": "ffmpeg -i media/demo.mp4 -ss ... media/frames/*.jpg",
            "source": "media/demo.mp4",
            "sha256": sha(path)})
doc = {"generated_by": "bash media/make_media.sh", "files": entries}
with open(os.path.join(here, "MANIFEST.json"), "w") as f:
    json.dump(doc, f, indent=2)
    f.write("\n")
print("[media] MANIFEST.json:", len(entries), "entries")
PY
echo "[media] done"
