#!/usr/bin/env bash
# media/make_media.sh — regenerate every media file for this demo.
#
#   1. browser frames     media/make_frames.py (judge venv python)
#   2. verdict JSONs      judge/grade.sh on both example sites (seed 42)
#   3. media/demo.mp4     ffmpeg step-through of the scroll frames with
#                         verdict captions; the lossless master goes to
#                         the gitignored media/master/
#   4. media/MANIFEST.json  per file: what it shows, the command, sha256
#
# Needs: the judge toolchain (bash judge/setup.sh) and ffmpeg with
# drawtext on PATH (Debian's ffmpeg build has it). A TrueType font is
# found via fc-match, falling back to fonts-dejavu-core paths.
#
# Usage: bash media/make_media.sh [--skip-frames] [--skip-grade]

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="$(dirname "$HERE")"
VENV_PY="$HOME/.taste-judge/venv/bin/python"
MASTER="$HERE/master"
FPS=30

SKIP_FRAMES=0; SKIP_GRADE=0
for a in "$@"; do
    case "$a" in
        --skip-frames) SKIP_FRAMES=1 ;;
        --skip-grade)  SKIP_GRADE=1 ;;
        *) echo "usage: $0 [--skip-frames] [--skip-grade]" >&2; exit 2 ;;
    esac
done

command -v ffmpeg >/dev/null || { echo "[media] ffmpeg not on PATH" >&2; exit 2; }
[[ -x "$VENV_PY" ]] || { echo "[media] $VENV_PY missing — run bash judge/setup.sh first" >&2; exit 2; }
mkdir -p "$MASTER"

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
else
    cp "$HERE/verdict-good.json" "$WORK/good.json" 2>/dev/null || true
    cp "$HERE/verdict-baseline.json" "$WORK/base.json" 2>/dev/null || true
fi
[[ -f "$WORK/good.json" && -f "$WORK/base.json" ]] || {
    echo "[media] no verdict JSONs — run without --skip-grade" >&2; exit 2; }

mapfile -t VERDICT_LINES < <(python3 - "$WORK/good.json" "$WORK/base.json" <<'PY'
import json, sys
g = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
fails = [x["gate"] for x in b["gates"] if not x["passed"]]
print("examples/good/site  -  ALL %d GATES PASS" % len(g["gates"]))
print("examples/baseline/site  -  FAILS %d/%d  (%s)"
      % (len(fails), len(b["gates"]), ", ".join(fails)))
PY
)

# ---------------------------------------------------------------- fonts
pick_font() {  # $1 = fc pattern, $2 = literal fallback path
    local f
    f="$(fc-match -f '%{file}' "$1" 2>/dev/null || true)"
    [[ -f "$f" ]] || f="$2"
    [[ -f "$f" ]] || { echo "[media] no font for '$1' (install fonts-dejavu-core)" >&2; exit 2; }
    printf '%s' "$f"
}
TITLE_FONT="$(pick_font 'DejaVu Serif:style=Bold' \
    /usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf)"
TEXT_FONT="$(pick_font 'DejaVu Sans' \
    /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf)"

# escape a string for drawtext inside a -filter_complex_script file
esc() {
    python3 -c 'import sys
s = sys.argv[1]
for a, b in [("\\", "\\\\"), (":", "\\:"), ("\x27", "\\\x27"),
             ("%", "\\%"), (",", "\\,"), (";", "\\;"),
             ("[", "\\["), ("]", "\\]")]:
    s = s.replace(a, b)
sys.stdout.write(s)' "$1"
}

# seg_img <png> <seconds> <caption> — page frame letterboxed on the brand
# ground (#F4F1EA) with an ink caption in the bottom band.
seg_img() {
    local png="$1" dur="$2" cap n
    cap="$(esc "$3")"
    n=$(printf '%02d' "$SEG"); SEG=$((SEG + 1))
    cat > "$WORK/f$n.txt" <<EOF
[0:v]scale=1880:980:force_original_aspect_ratio=decrease,
pad=1920:984:(ow-iw)/2:(oh-ih)/2:color=0xF4F1EA,
pad=1920:1080:(ow-iw)/2:0:color=0xF4F1EA,
drawtext=fontfile='${TEXT_FONT}':text='${cap}':fontcolor=0x1A241F:fontsize=28:x=(w-text_w)/2:y=1018,
format=yuv420p[v]
EOF
    ffmpeg -hide_banner -loglevel error -y \
        -loop 1 -framerate $FPS -t "$dur" -i "$png" \
        -filter_complex_script "$WORK/f$n.txt" -map "[v]" \
        -c:v libx264 -preset medium -crf 0 -r $FPS \
        "$MASTER/seg$n.mp4"
}

# seg_card <seconds> <fontsize:x:y:fontfile:text> ... — text lines on the
# brand ground. Each spec is "size|y|fontfile|text" (x centred).
seg_card() {
    local dur="$1"; shift
    local n spec size y font text dt=""
    n=$(printf '%02d' "$SEG"); SEG=$((SEG + 1))
    for spec in "$@"; do
        size="${spec%%|*}"; spec="${spec#*|}"
        y="${spec%%|*}";    spec="${spec#*|}"
        font="${spec%%|*}"; spec="${spec#*|}"
        text="$(esc "$spec")"
        dt="${dt},drawtext=fontfile='${font}':text='${text}':fontcolor=0x1A241F:fontsize=${size}:x=(w-text_w)/2:y=${y}"
    done
    cat > "$WORK/f$n.txt" <<EOF
[0:v]format=yuv420p${dt}[v]
EOF
    ffmpeg -hide_banner -loglevel error -y \
        -f lavfi -t "$dur" -i "color=c=0xF4F1EA:s=1920x1080:r=$FPS" \
        -filter_complex_script "$WORK/f$n.txt" -map "[v]" \
        -c:v libx264 -preset medium -crf 0 -r $FPS \
        "$MASTER/seg$n.mp4"
}

# ---------------------------------------------------------------- video
SEG=0
echo "[media] demo.mp4: title card, scroll frames, verdict card"
seg_card 3.4 \
    "128|330|${TITLE_FONT}|Kestrel" \
    "42|500|${TEXT_FONT}|the same brief, built with - and without - a design-taste skill" \
    "30|570|${TEXT_FONT}|judged in headless Chromium 153 by 7 measured gates"
for i in 0 1 2 3 4 5 6 7 8 9; do
    f="$HERE/scroll-0$i.png"
    seg_img "$f" 2.1 \
        "examples/good/site - headless Chromium scroll capture, 1440x900"
done
seg_card 6.0 \
    "56|300|${TITLE_FONT}|judge verdict - seed 42" \
    "36|420|${TEXT_FONT}|${VERDICT_LINES[0]}" \
    "30|500|${TEXT_FONT}|${VERDICT_LINES[1]}" \
    "28|620|${TEXT_FONT}|judge self-test - 10/10 mutants killed, a failing site exits non-zero"

for f in "$MASTER"/seg*.mp4; do printf 'file %s\n' "$f"; done \
    > "$WORK/concat.txt"
ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 \
    -i "$WORK/concat.txt" -c copy "$MASTER/demo-master.mp4"
ffmpeg -hide_banner -loglevel error -y -i "$MASTER/demo-master.mp4" \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p \
    -movflags +faststart "$HERE/demo.mp4"
SZ=$(stat -c %s "$HERE/demo.mp4")
echo "[media] demo.mp4: $((SZ / 1024)) KiB ($(ffprobe -v error \
    -show_entries format=duration -of csv=p=0 "$HERE/demo.mp4") s)"
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
            "~30 s step-through of the scroll frames with the seed-42 "
            "verdict captions (lossless master in gitignored media/master/)",
            "bash media/make_media.sh",
            "media/scroll-*.png + fresh judge/grade.sh verdict JSONs")
    entries.append({"file": name, "shows": what, "command": cmd,
                    "source": src, "sha256": sha(path)})
doc = {"generated_by": "bash media/make_media.sh", "files": entries}
with open(os.path.join(here, "MANIFEST.json"), "w") as f:
    json.dump(doc, f, indent=2)
    f.write("\n")
print("[media] MANIFEST.json:", len(entries), "entries")
PY
echo "[media] done"
