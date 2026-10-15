#!/usr/bin/env bash
# Probe 2: open CSV in real Calc on the display, inspect windows/dialog.
set -ux
export DISPLAY=:92
Xvfb :92 -screen 0 1024x768x24 -nolisten tcp > /tmp/xvfb.log 2>&1 &
XVFB_PID=$!
for i in $(seq 1 50); do xdpyinfo -display :92 >/dev/null 2>&1 && break; sleep 0.2; done
DISPLAY=:92 fluxbox > /tmp/fluxbox.log 2>&1 &
FB_PID=$!
sleep 3
mkdir -p /tmp/desktop-cu /tmp/loprofile
printf 'item,qty,price\napple,3,0.50\nbanana,2,0.25\ncherry,5,1.00\n' > /tmp/desktop-cu/input.csv
cd /tmp
HOME=/tmp/loprofile DISPLAY=:92 soffice --norestore --calc /tmp/desktop-cu/input.csv > /tmp/soffice.log 2>&1 &
SOFF_PID=$!
for i in $(seq 1 60); do
  sleep 1
  if DISPLAY=:92 xdotool search --name "." 2>/dev/null | grep -q .; then break; fi
done
echo "=== window tree ==="
DISPLAY=:92 xdotool search --name "." 2>&1 | while read w; do
  echo "win $w name=[$(DISPLAY=:92 xdotool getwindowname $w 2>/dev/null)]"
done
echo "=== xwininfo root ==="
DISPLAY=:92 xwininfo -root -children 2>&1 | head -20
DISPLAY=:92 import -window root /tmp/after_open.png
echo "=== active window ==="
DISPLAY=:92 xdotool getactivewindow getwindowname 2>&1
