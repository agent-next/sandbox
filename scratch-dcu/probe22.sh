#!/usr/bin/env bash
set -ux
export DISPLAY=:112
pkill Xvfb 2>/dev/null; pkill fluxbox 2>/dev/null; sleep 1
Xvfb :112 -screen 0 1024x768x24 -nolisten tcp > /tmp/xvfb.log 2>&1 &
for i in $(seq 1 50); do xdpyinfo -display :112 >/dev/null 2>&1 && break; sleep 0.2; done
fluxbox > /tmp/fluxbox.log 2>&1 &
sleep 3
mkdir -p /tmp/desktop-cu /tmp/loprofile
printf 'item,qty,price\napple,3,0.50\nbanana,2,0.25\ncherry,5,1.00\n' > /tmp/desktop-cu/input.csv
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
xdotool key ctrl+shift+s; sleep 4
S=$(xdotool search --name "Save as" | head -1)
xdotool windowactivate --sync $S; xdotool windowfocus --sync $S
sleep 1
# zoom into the file-type row and the arrow region with a crop
import -window root /tmp/n0.png
convert /tmp/n0.png -crop 460x60+220+565 +repage -scale 200% /tmp/n1.png
import -window root /tmp/n2.png
# Try the exact filter name and pressing Tab out of the field
xdotool mousemove 700 594 click 1; sleep 0.4
xdotool key ctrl+a; sleep 0.3
xdotool type --delay 40 "Excel 2007 XML"; sleep 1
xdotool key Tab; sleep 0.5
import -window root /tmp/n3.png
# now click Save
xdotool mousemove 920 570 click 1; sleep 5
import -window root /tmp/n4.png
xdotool search --name "." 2>/dev/null | while read w; do echo "  win $w [$(xdotool getwindowname $w 2>/dev/null)]"; done
ls -la /tmp/desktop-cu/
