#!/usr/bin/env bash
set -ux
export DISPLAY=:104
pkill Xvfb 2>/dev/null; pkill fluxbox 2>/dev/null; sleep 1
Xvfb :104 -screen 0 1024x768x24 -nolisten tcp > /tmp/xvfb.log 2>&1 &
for i in $(seq 1 50); do xdpyinfo -display :104 >/dev/null 2>&1 && break; sleep 0.2; done
fluxbox > /tmp/fluxbox.log 2>&1 &
sleep 3
mkdir -p /tmp/desktop-cu /tmp/loprofile
printf 'item,qty,price\napple,3,0.50\nbanana,2,0.25\ncherry,5,1.00\n' > /tmp/desktop-cu/input.csv
rm -f /tmp/desktop-cu/report.xlsx
rm -rf /tmp/loprofile; mkdir -p /tmp/loprofile
export HOME=/tmp/loprofile
cd /tmp
mkdir -p /tmp/loprofile/.config/libreoffice/4/user
cat > /tmp/loprofile/.config/libreoffice/4/user/registrymodifications.xcu <<'XCU'
<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="FirstRun" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Help"><prop oor:name="Tip" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="LastTipOfTheDayShown" oor:op="fuse"><value>20741</value></prop></item>
</oor:items>
XCU
timeout 400 soffice --norestore --calc /tmp/desktop-cu/input.csv > /tmp/soffice.log 2>&1 &
for i in $(seq 1 60); do sleep 1; xdotool search --name "Text Import" 2>/dev/null | grep -q . && break; done
D=$(xdotool search --name "Text Import" | head -1)
xdotool key --window "$D" Return
for i in $(seq 1 60); do sleep 1; xdotool search --name "input.csv - LibreOffice Calc" 2>/dev/null | grep -q . && break; done
W=$(xdotool search --name "input.csv - LibreOffice Calc" | head -1)
sleep 3
xdotool windowactivate --sync $W; xdotool windowfocus --sync $W
sleep 2
enter_cell() {
  xdotool mousemove 100 110 click 1; sleep 0.4
  xdotool key ctrl+a; sleep 0.2
  xdotool type --delay 30 "$1"; sleep 0.35
  xdotool key Return; sleep 1.0
}
enter_cell D1;  xdotool type --delay 30 "total";    xdotool key Return; sleep 1.2
enter_cell D2;  xdotool type --delay 30 "=B2*C2"; xdotool key Return; sleep 1.2
enter_cell D3;  xdotool type --delay 30 "=B3*C3"; xdotool key Return; sleep 1.2
enter_cell D4;  xdotool type --delay 30 "=B4*C4"; xdotool key Return; sleep 1.2
enter_cell A5;  xdotool type --delay 30 "total";    xdotool key Return; sleep 1.2
enter_cell B5;  xdotool type --delay 30 "=SUM(B2:B4)"; xdotool key Return; sleep 1.2
enter_cell D5;  xdotool type --delay 30 "=SUM(D2:D4)"; xdotool key Return; sleep 1.2
xdotool key ctrl+shift+s; sleep 4
S=$(xdotool search --name "Save as" | head -1)
xdotool windowactivate --sync $S; xdotool windowfocus --sync $S
sleep 1
xdotool mousemove 700 570 click 1; sleep 0.4
xdotool key ctrl+a; sleep 0.3
xdotool type --delay 40 "/tmp/desktop-cu/report.xlsx"; sleep 1
import -window root /tmp/e1.png
xdotool key Return; sleep 5
# Confirm File Format dialog -> "Use Text CSV Format!" is on the right.
C=$(xdotool search --name "Confirm File Format" | head -1)
echo "CONFIRM=[$C]"
A=$(xdotool search --name "Confirm" | head -1)
echo "ANY=[$A]"
import -window root /tmp/e2.png
if [ -n "$C" ]; then
  xdotool windowactivate --sync $C
  xdotool key --clearmodifiers Tab Tab Return
fi
sleep 6
import -window root /tmp/e3.png
echo "=== windows ==="
xdotool search --name "." 2>/dev/null | while read w; do echo "  win $w [$(xdotool getwindowname $w 2>/dev/null)]"; done
ls -la /tmp/desktop-cu/
echo "=== zip check ==="
unzip -l /tmp/desktop-cu/report.xlsx 2>&1 | head -20
