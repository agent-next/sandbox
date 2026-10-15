#!/usr/bin/env bash
# video-transcode-pipeline: ingest one MP4 and emit an HLS ladder, a poster
# and WebVTT captions. This is the artifact the judge grades; the known-good
# copy lives in examples/good/pipeline.sh (identical file).
#
#   ./pipeline.sh --input <source.mp4> --out <dir> [--seed N]
#
# Defaults read the committed fixtures: fixtures/source.mp4 and
# fixtures/speech.mp3. Everything is written under <out>:
#
#   <out>/360p/index.m3u8   <out>/360p/seg-*.ts
#   <out>/720p/index.m3u8   <out>/720p/seg-*.ts
#   <out>/poster.png
#   <out>/captions.vtt
#
# Deterministic: fixed encoder settings, fixed keyframe grid, fixed whisper
# decode parameters, so the output is byte-stable for any seed. --seed is
# accepted and validated for the interface SPEC.md describes, and a pipeline
# that introduces randomness (a wording variant, say) would branch on it.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INPUT=""
OUT=""
SEED=0

while [ $# -gt 0 ]; do
    case "$1" in
        --input) INPUT="${2:?--input needs a value}"; shift 2 ;;
        --out)   OUT="${2:?--out needs a value}";   shift 2 ;;
        --seed)  SEED="${2:?--seed needs a value}"; shift 2 ;;
        -h|--help) sed -n '2,18p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "pipeline.sh: unknown argument: $1" >&2; exit 2 ;;
    esac
done

[ -n "$OUT" ] || { echo "pipeline.sh: --out is required" >&2; exit 2; }
case "$SEED" in ''|*[!0-9]*) echo "pipeline.sh: --seed must be a non-negative integer" >&2; exit 2 ;; esac

for tool in ffmpeg ffprobe; do
    command -v "$tool" > /dev/null || { echo "pipeline.sh: $tool not found on PATH" >&2; exit 1; }
done

# Inputs: explicit --input, else the committed fixtures next to this script.
FIXTURES="$SELF_DIR/fixtures"
[ -f "$FIXTURES/source.mp4" ] || FIXTURES="$SELF_DIR/../fixtures"
[ -n "$INPUT" ] || INPUT="$FIXTURES/source.mp4"
SPEECH="$FIXTURES/speech.mp3"
[ -f "$INPUT" ] || { echo "pipeline.sh: input $INPUT not found" >&2; exit 1; }
[ -f "$SPEECH" ] || { echo "pipeline.sh: speech fixture $SPEECH not found" >&2; exit 1; }

# whisper.cpp built by judge/setup.sh, or an explicit override.
WHISPER_CLI="${WHISPER_CLI:-$HOME/.vtp-tools/whisper-cli}"
WHISPER_MODEL="${WHISPER_MODEL:-$HOME/.vtp-tools/ggml-tiny.en.bin}"
[ -x "$WHISPER_CLI" ] || { echo "pipeline.sh: whisper-cli not found at $WHISPER_CLI (run judge/setup.sh)" >&2; exit 1; }
[ -f "$WHISPER_MODEL" ] || { echo "pipeline.sh: model not found at $WHISPER_MODEL (run judge/setup.sh)" >&2; exit 1; }

# --- pins (the judge's numbers depend on these) ---------------------------
SRC_FPS=24
KEYINT=96                 # 4 s at 24 fps
GOP_SECONDS=4
CRF=20
AUDIO_360=96k
AUDIO_720=128k
POSTER_T=1.0              # seconds
CAPTION_MAXLINE=18
CAPTION_THREADS=2

DURATION="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$INPUT")"
[ -n "$DURATION" ] || { echo "pipeline.sh: could not read the duration of $INPUT" >&2; exit 1; }

rm -rf "$OUT"
mkdir -p "$OUT/360p" "$OUT/720p" "$OUT/.work"
WORK="$OUT/.work"
trap 'rm -rf "$WORK"' EXIT

# --- HLS ladder -----------------------------------------------------------
# One pass per rendition. -g/-keyint_min/-sc_threshold pin the keyframe grid
# to exactly 4 s; -hls_time 2 with split_by_time cuts 2 s segments on that
# grid (a plain -hls_time would stretch every segment to the next keyframe).
encode() {
    local w="$1" h="$2" abr="$3" name="$4"
    ffmpeg -v error -y -i "$INPUT" \
        -vf "scale=${w}:${h}" \
        -c:v libx264 -preset veryfast -profile:v main -crf "$CRF" \
        -g "$KEYINT" -keyint_min "$KEYINT" -sc_threshold 0 \
        -pix_fmt yuv420p -r "$SRC_FPS" \
        -c:a aac -b:a "$abr" -ac 2 -ar 48000 \
        -f hls -hls_time 2 -hls_flags split_by_time \
        -hls_playlist_type vod -hls_segment_filename "$OUT/$name/seg-%03d.ts" \
        "$OUT/$name/index.m3u8"
}
encode 640 360 "$AUDIO_360" 360p
encode 1280 720 "$AUDIO_720" 720p

# --- poster ---------------------------------------------------------------
ffmpeg -v error -y -ss "$POSTER_T" -i "$INPUT" -frames:v 1 -pix_fmt rgb24 "$OUT/poster.png"

# --- captions -------------------------------------------------------------
# whisper.cpp wants 16 kHz mono PCM; feed it the speech track, not the video.
ffmpeg -v error -y -i "$SPEECH" -ar 16000 -ac 1 -c:a pcm_s16le "$WORK/speech.wav"
"$WHISPER_CLI" \
    -m "$WHISPER_MODEL" \
    -f "$WORK/speech.wav" \
    -t "$CAPTION_THREADS" \
    -ml "$CAPTION_MAXLINE" -sow \
    -ovtt -of "$WORK/captions" -np \
    > "$WORK/whisper.log" 2>&1
[ -s "$WORK/captions.vtt" ] || { echo "pipeline.sh: whisper produced no captions" >&2; exit 1; }
cp "$WORK/captions.vtt" "$OUT/captions.vtt"

# --- report ---------------------------------------------------------------
for name in 360p 720p; do
    n="$(ls "$OUT/$name"/seg-*.ts 2>/dev/null | wc -l)"
    [ "$n" -gt 0 ] || { echo "pipeline.sh: no segments written for $name" >&2; exit 1; }
    echo "pipeline.sh: $name $(ffprobe -v error -select_streams v -show_entries stream=width,height -of csv=p=0 "$OUT/$name/seg-000.ts") in $n segments"
done
echo "pipeline.sh: poster $OUT/poster.png"
echo "pipeline.sh: captions $OUT/captions.vtt ($(grep -c ' --> ' "$OUT/captions.vtt") cues)"
echo "pipeline.sh: done"
