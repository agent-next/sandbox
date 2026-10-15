#!/usr/bin/env bash
# Generate the committed fixtures this demo grades against.
#
#   fixtures/source.mp4   20.000 s, 640x360, 24 fps, H.264 + AAC. A testsrc
#                         pattern with a black band across the bottom and the
#                         frame number burned into it as five zero-padded
#                         digits (drawtext, monospace bold). The judge decodes
#                         those digits back out of the renditions (G5).
#   fixtures/speech.mp3   6.07 s, 16 kHz mono MP3, espeak-ng reading
#                         fixtures/TRANSCRIPT.txt. The judge scores the
#                         captions against that text (G8, word error rate).
#
# Deterministic: no timestamps, no metadata, fixed encoder settings, and the
# drawtext `%{n}` counter is a pure function of the frame index. Re-running
# this script reproduces byte-identical fixtures (verify with
# fixtures/SHA256SUMS).
#
# Requires ffmpeg 5.1.9 and espeak-ng 1.51 (judge/setup.sh), plus a
# DejaVu Sans Mono Bold font. The fixtures are committed, so this script is
# only needed to regenerate them.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- pins -----------------------------------------------------------------
FFMPEG_MIN="5.1.9"
ESPEAK_VOICE="en-us"
ESPEAK_SPEED="140"
FONT="${FIXTURE_FONT:-/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf}"

# 20 s at 24 fps, keyframe every 4 s exactly (96 frames).
SRC_DUR="20"
SRC_FPS="24"
SRC_W="640"
SRC_H="360"
KEYINT="96"
# The counter lives inside this band; judge/vtp_judge.py crops the same
# fraction of whatever frame size it is handed.
BAND_X="0"
BAND_Y="278"
BAND_W="640"
BAND_H="82"
TEXT_X="24"
TEXT_Y="290"
FONT_SIZE="48"

# --- preconditions --------------------------------------------------------
for tool in ffmpeg ffprobe espeak-ng; do
    command -v "$tool" > /dev/null || {
        echo "gen_fixtures: $tool not found; run judge/setup.sh first" >&2
        exit 1
    }
done
have="$(ffmpeg -version | sed -n '1s/^ffmpeg version \([0-9][^ -]*\).*/\1/p')"
if [ "$have" != "$FFMPEG_MIN" ]; then
    echo "gen_fixtures: ffmpeg $have != pinned $FFMPEG_MIN" >&2
    exit 1
fi
[ -f "$FONT" ] || {
    echo "gen_fixtures: font $FONT not found (set FIXTURE_FONT)" >&2
    exit 1
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# --- speech clip ----------------------------------------------------------
# The transcript is a single line of public-domain pangrams; espeak-ng
# renders it deterministically at a fixed voice and speed.
text="$(cat "$HERE/TRANSCRIPT.txt")"
espeak-ng -v "$ESPEAK_VOICE" -s "$ESPEAK_SPEED" -w "$tmp/speech.wav" "$text"
ffmpeg -v error -y -i "$tmp/speech.wav" -ac 1 -ar 16000 -b:a 64k \
    -map_metadata -1 "$tmp/speech.mp3"

# --- source video ---------------------------------------------------------
# testsrc gives moving, high-contrast content (so the poster gate has real
# luminance spread); the black band keeps the test pattern out of the
# counter's glyph segmentation; drawtext burns `%{n}`, the frame index.
vf="drawbox=x=${BAND_X}:y=${BAND_Y}:w=${BAND_W}:h=${BAND_H}:color=black@1:t=fill,"
# ffmpeg 5.1's filtergraph parser eats one level of backslash, so the
# drawtext expression needs a doubled escape to survive into the filter.
vf+="drawtext=fontfile=${FONT}:text=%{eif\\\\:n\\\\:d\\\\:5}:"
vf+="x=${TEXT_X}:y=${TEXT_Y}:fontsize=${FONT_SIZE}:fontcolor=white"
ffmpeg -v error -y \
    -f lavfi -i "testsrc=size=${SRC_W}x${SRC_H}:rate=${SRC_FPS}:duration=${SRC_DUR}" \
    -f lavfi -i "sine=frequency=440:sample_rate=48000:duration=${SRC_DUR}" \
    -vf "$vf" \
    -c:v libx264 -preset veryfast -profile:v main -crf 18 \
    -g "$KEYINT" -keyint_min "$KEYINT" -sc_threshold 0 \
    -pix_fmt yuv420p -r "$SRC_FPS" \
    -c:a aac -b:a 128k -shortest -map_metadata -1 \
    "$tmp/source.mp4"

# --- install + verify -----------------------------------------------------
for f in source.mp4 speech.mp3; do
    if [ -f "$HERE/$f" ]; then
        echo "gen_fixtures: $f exists (not overwritten; delete it to regenerate)"
        continue
    fi
    cp "$tmp/$f" "$HERE/$f"
    echo "gen_fixtures: wrote $f"
done

dur="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$HERE/source.mp4")"
printf 'gen_fixtures: source.mp4 duration %s s\n' "$dur"
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate \
    -of csv=p=0 "$HERE/source.mp4"
