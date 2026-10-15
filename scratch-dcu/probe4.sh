#!/usr/bin/env bash
# Probe 4: full flow - type into cells via Name Box, save as xlsx.
set -ux
export DISPLAY=:94
pkill Xvfb 2>/dev/null; pkill fluxbox 2>/dev/null; sleep 1
Xvfb :94 -screen 0 1024x768x24 -nolisten tcp > /tmp/xvfb.log 2>&1 &
for i in $(seq 1 50); do xdpyinfo -display :94 >/dev/null 2>&1 && break; sleep 0.2; done
DISPLAY=:94 fluxbox > /tmp/fluxbox.log 2>&1 &
sleep 3
mkdir -p /tmp/desktop-cu /tmp/loprofile
printf 'item,qty,price\napple,3,0.50\nbanana,2,0.25\ncherry,5,1.00\n' > /tmp/desktop-cu/input.csv
rm -rf /tmp/loprofile; mkdir -p /tmp/loprofile
cd /tmp
HOME=/tmp/loprofile DISPLAY=:94 soffice --norestore --calc /tmp/desktop-cu/input.csv > /tmp/soffice.log 2>&1 &
sleep 6
# dismiss text import
D=$(xdotool search --name "Text Import" | head -1)
[ -n "$D" ] && xdotool key --window "$D" Return
sleep 4
# dismiss tip of the day
T=$(xdotool search --name "Tip of the Day" | head -1)
[ -n "$T" ] && xdotool key --window "$T" Escape
sleep 2
W=$(xdotool search --name "input.csv - LibreOffice Calc" | head -1)
echo "CALC WIN=$W"
xdotool windowactivate --sync $W
xdotool windowfocus --sync $W
sleep 1
eval "$(xdotool getwindowgeometry --shell $W)"
echo "geo X=$X Y=$Y WIDTH=$WIDTH HEIGHT=$HEIGHT"
DISPLAY=:94 import -window root /tmp/s0.png

# Name box: click it
xdotool mousemove $((X+92)) $((Y+96)) click 1
sleep 0.5
xdotool key ctrl+a
sleep 0.3
xdotool type --delay 30 "D1"
sleep 0.5
xdotool key Return
sleep 1
xdotool type --delay 30 "total"
xdotool key Return
sleep 1
DISPLAY=:94 import -window root /tmp/s1.png
echo "=== after typing total"
ls -la /tmp/s1.png
