#!/usr/bin/env bash
# Probe 3: CSV import dialog - keys, geometry, after OK.
set -ux
export DISPLAY=:93
pkill Xvfb 2>/dev/null; pkill fluxbox 2>/dev/null; sleep 1
Xvfb :93 -screen 0 1024x768x24 -nolisten tcp > /tmp/xvfb.log 2>&1 &
for i in $(seq 1 50); do xdpyinfo -display :93 >/dev/null 2>&1 && break; sleep 0.2; done
DISPLAY=:93 fluxbox > /tmp/fluxbox.log 2>&1 &
sleep 3
mkdir -p /tmp/desktop-cu /tmp/loprofile
printf 'item,qty,price\napple,3,0.50\nbanana,2,0.25\ncherry,5,1.00\n' > /tmp/desktop-cu/input.csv
rm -rf /tmp/loprofile
mkdir -p /tmp/loprofile
cd /tmp
HOME=/tmp/loprofile DISPLAY=:93 soffice --norestore --calc /tmp/desktop-cu/input.csv > /tmp/soffice.log 2>&1 &
for i in $(seq 1 60); do sleep 1; DISPLAY=:93 xdotool search --name "Text Import" 2>/dev/null | grep -q . && break; done
echo "=== windows now ==="
DISPLAY=:93 xdotool search --name "." | while read w; do echo "win $w [$(xdotool getwindowname $w 2>/dev/null)]"; done
echo "=== dialog geometry ==="
D=$(DISPLAY=:93 xdotool search --name "Text Import" | head -1)
echo "dialog id $D"
xdotool getwindowgeometry --shell "$D"
DISPLAY=:93 import -window root /tmp/dialog.png
echo "=== press Return ==="
xdotool key --window "$D" Return
sleep 3
echo "=== windows after OK ==="
DISPLAY=:93 xdotool search --name "." | while read w; do echo "win $w [$(xdotool getwindowname $w 2>/dev/null)]"; done
DISPLAY=:93 import -window root /tmp/loaded.png
echo "=== focused cell / name box ==="
xdotool getwindowfocus getwindowname
ls -la /tmp/*.png
