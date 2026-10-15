#!/usr/bin/env bash
set -ux
export DISPLAY=:100
pkill Xvfb 2>/dev/null; pkill fluxbox 2>/dev/null; sleep 1
Xvfb :100 -screen 0 1024x768x24 -nolisten tcp > /tmp/xvfb.log 2>&1 &
for i in $(seq 1 50); do xdpyinfo -display :100 >/dev/null 2>&1 && break; sleep 0.2; done
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
<item oor:path="/org.openoffice.Office.Common/Help"><prop oor:name="Tip" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Help"><prop oor:name="ShowTips" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Setup/Office/Factories"><prop oor:name="ooSetupFactoryAboutLastStep" oor:op="fuse"><value>false</value></prop></item>
</oor:items>
XCU
timeout 200 soffice --norestore --calc /tmp/desktop-cu/input.csv > /tmp/soffice.log 2>&1 &
SOFF=$!
for i in $(seq 1 60); do sleep 1; xdotool search --name "Text Import" 2>/dev/null | grep -q . && break; done
echo "=== import dialog found, dumping all windows ==="
xdotool search --name "." | while read w; do echo "win $w [$(xdotool getwindowname $w 2>/dev/null)]"; done
echo "=== key Return to dialog ==="
D=$(xdotool search --name "Text Import" | head -1)
xdotool key --window "$D" Return
sleep 4
echo "=== windows after ==="
for i in $(seq 1 30); do
  sleep 1
  echo "-- t=$i"
  xdotool search --name "." 2>/dev/null | while read w; do echo "  win $w [$(xdotool getwindowname $w 2>/dev/null)]"; done
  if xdotool search --name "input.csv - LibreOffice Calc" 2>/dev/null | grep -q .; then echo FOUND; break; fi
done
echo "=== process alive ==="
kill -0 $SOFF && echo "soffice alive"
import -window root /tmp/loaded.png
