#!/usr/bin/env bash
set -eux
export DISPLAY=:96
pkill Xvfb 2>/dev/null; pkill fluxbox 2>/dev/null; sleep 1
Xvfb :96 -screen 0 1024x768x24 -nolisten tcp > /tmp/xvfb.log 2>&1 &
for i in $(seq 1 50); do xdpyinfo -display :96 >/dev/null 2>&1 && break; sleep 0.2; done
fluxbox > /tmp/fluxbox.log 2>&1 &
sleep 3
mkdir -p /tmp/desktop-cu /tmp/loprofile
printf 'item,qty,price\napple,3,0.50\nbanana,2,0.25\ncherry,5,1.00\n' > /tmp/desktop-cu/input.csv
rm -rf /tmp/loprofile; mkdir -p /tmp/loprofile
cd /tmp
HOME=/tmp/loprofile soffice --norestore --calc /tmp/desktop-cu/input.csv > /tmp/soffice.log 2>&1 &
for i in $(seq 1 60); do sleep 1; xdotool search --name "Text Import" 2>/dev/null | grep -q . && break; done
D=$(xdotool search --name "Text Import" | head -1)
xdotool key --window "$D" Return
for i in $(seq 1 60); do sleep 1; xdotool search --name "input.csv" 2>/dev/null | grep -q . && break; done
sleep 3
W=$(xdotool search --name "input.csv" | head -1)
xdotool windowactivate --sync $W; xdotool windowfocus --sync $W
sleep 1
eval "$(xdotool getwindowgeometry --shell $W)"
echo "GEO X=$X Y=$Y W=$WIDTH H=$HEIGHT"
import -window root /tmp/s0.png
# Name box: click it
xdotool mousemove $((X+92)) $((Y+96)) click 1
sleep 0.5
xdotool key ctrl+a; sleep 0.3
xdotool type --delay 30 "D1"; sleep 0.5
xdotool key Return; sleep 1
xdotool type --delay 30 "total"; sleep 0.5
xdotool key Return; sleep 1.5
import -window root /tmp/s1.png
echo "=== windows ==="
xdotool search --name "." | while read w; do echo "win $w [$(xdotool getwindowname $w 2>/dev/null)]"; done
