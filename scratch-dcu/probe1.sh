#!/usr/bin/env bash
# Probe: start Xvfb + fluxbox, open the CSV in soffice Calc, screenshot.
set -ux
export DISPLAY=:91
Xvfb :91 -screen 0 1024x768x24 -nolisten tcp > /tmp/xvfb.log 2>&1 &
XVFB_PID=$!
for i in $(seq 1 50); do xdpyinfo -display :91 >/dev/null 2>&1 && break; sleep 0.2; done
DISPLAY=:91 fluxbox > /tmp/fluxbox.log 2>&1 &
FB_PID=$!
sleep 3
mkdir -p /tmp/desktop-cu
printf 'item,qty,price\napple,3,0.50\nbanana,2,0.25\ncherry,5,1.00\n' > /tmp/desktop-cu/input.csv
rm -rf /tmp/loprofile
mkdir -p /tmp/loprofile
( cd /tmp && HOME=/tmp/loprofile soffice --headless --norestore --convert-to fods --outdir /tmp/conv /tmp/desktop-cu/input.csv ) || true
echo "=== window list after convert ==="
DISPLAY=:91 xdotool search --name . 2>&1 | head
DISPLAY=:91 import -window root /tmp/before.png
ls -la /tmp/before.png /tmp/conv 2>&1
kill $FB_PID $XVFB_PID 2>/dev/null || true
