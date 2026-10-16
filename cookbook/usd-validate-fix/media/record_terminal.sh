#!/usr/bin/env bash
# Record a REAL run of judge/selftest.sh on screen, for the video's
# "Nx speed" sandbox-run slot (cookbook/DEMO-STANDARD.md, Media: "a sped-up
# process run of the agent in the sandbox, labelled 'Nx speed'").
#
# This is a screen capture of the actual self-test process, not a replay of
# text: an X server (Xvfb) hosts an xterm running `bash judge/selftest.sh`,
# and ffmpeg's x11grab records that window at 30 fps.  The capture stops
# when the self-test process exits, so the clip is exactly one real run.
#
# Output: media/clips/terminal_raw.mp4 (git-ignored; regenerated here).
# make_video.py crops it to the active terminal region, scales it to 1080p
# and labels it with the speed factor STORYBOARD.md records.
#
# Dependencies (media-time, on the host that cuts the video):
#   ffmpeg, xvfb, xterm            (Debian: sudo apt-get install -y xvfb xterm)
# The judge itself needs no display; only the capture does.  Missing tools
# fail loudly here rather than producing a video with no real run in it.

set -euo pipefail

MEDIA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(dirname "$MEDIA_DIR")"
CLIPS="$MEDIA_DIR/clips"
RAW="$CLIPS/terminal_raw.mp4"
DISP="${TERMINAL_CAPTURE_DISPLAY:-:99}"
W=1920
H=1080
FPS=30

for tool in ffmpeg Xvfb xterm; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "record_terminal: '$tool' not found." >&2
        if [ "$tool" = "ffmpeg" ]; then exit 1; fi
        echo "  install the capture tools: sudo apt-get install -y xvfb xterm" >&2
        exit 1
    }
done

mkdir -p "$CLIPS"

# A stale lock from a killed run makes Xvfb refuse to start, so clear it.
LOCK="/tmp/.X${DISP#:}-lock"
[ -e "$LOCK" ] && rm -f "$LOCK" 2>/dev/null || true

# Start our own X server; remember the pid so we can stop exactly this one.
Xvfb "$DISP" -screen 0 "${W}x${H}x24" -nolisten tcp >"$CLIPS/xvfb.log" 2>&1 &
XVFB_PID=$!
cleanup() {
    [ -n "${GRAB_PID:-}" ] && kill "$GRAB_PID" 2>/dev/null || true
    kill "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT

# Wait for the display to accept connections (up to ~5 s).
for _ in $(seq 1 50); do
    [ -S "/tmp/.X11-unix/X${DISP#:}" ] && break
    sleep 0.1
done

rm -f "$RAW"

# Open the terminal running the real self-test.  It prints a sentinel when
# the process has exited and then closes, so the capture length equals the
# run length.  Its pid is tracked directly: polling `pgrep -f selftest.sh`
# would also match any unrelated process whose command line mentions the
# script (the harness's own prompt does), and the grabber would never stop.
DISPLAY="$DISP" xterm \
    -fa "DejaVu Sans Mono" -fs 22 -geometry 76x32 \
    -bg "#0d1117" -fg "#c9d1d9" -b 0 -bw 0 \
    -e bash -lc "cd '$DEMO_DIR' && bash judge/selftest.sh; rc=\$?; \
                 echo; echo \"selftest exit \$rc\"; sleep 1" &
XTERM_PID=$!

# Give xterm a moment to map its window before grabbing.
sleep 2

# Grab the whole screen at 30 fps until the terminal closes.
ffmpeg -y -nostdin -f x11grab -video_size "${W}x${H}" -framerate "$FPS" \
       -draw_mouse 0 -i "${DISP}.0" \
       -pix_fmt yuv420p -c:v libx264 -crf 18 -preset ultrafast "$RAW" \
       >"$CLIPS/ffmpeg_grab.log" 2>&1 &
GRAB_PID=$!

# Wait for the self-test window to close, then stop the grabber with SIGINT
# so the mp4 is finalised cleanly (SIGKILL would leave no moov atom).
wait "$XTERM_PID" 2>/dev/null || true
sleep 2   # let the sentinel/exit line paint
kill -INT "$GRAB_PID" 2>/dev/null || true
wait "$GRAB_PID" 2>/dev/null || true

[ -s "$RAW" ] || { echo "record_terminal: no capture written" >&2; exit 1; }
DUR="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$RAW")"
echo "record_terminal: wrote $RAW (${DUR}s at ${W}x${H}, ${FPS} fps)"
