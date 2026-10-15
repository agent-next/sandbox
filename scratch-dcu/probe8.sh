#!/usr/bin/env bash
set -ux
export DISPLAY=:98
pkill Xvfb 2>/dev/null; pkill fluxbox 2>/dev/null; sleep 1
Xvfb :98 -screen 0 1024x768x24 -nolisten tcp > /tmp/xvfb.log 2>&1 &
for i in $(seq 1 50); do xdpyinfo -display :98 >/dev/null 2>&1 && break; sleep 0.2; done
fluxbox > /tmp/fluxbox.log 2>&1 &
sleep 3
mkdir -p /tmp/desktop-cu /tmp/loprofile
printf 'item,qty,price\napple,3,0.50\nbanana,2,0.25\ncherry,5,1.00\n' > /tmp/desktop-cu/input.csv
rm -rf /tmp/loprofile; mkdir -p /tmp/loprofile
export HOME=/tmp/loprofile
cd /tmp
# Seed the config: write registrymodifications.xcu with the tips disabled.
mkdir -p /tmp/loprofile/.config/libreoffice/4/user
cat > /tmp/loprofile/.config/libreoffice/4/user/registrymodifications.xcu <<'XCU'
<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Common/Save/Document"><prop oor:name="Load/Settings" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="FirstRun" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Help"><prop oor:name="TipsOnStart" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Help"><prop oor:name="ShowTips" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Setup/Office/Factories"><prop oor:name="ooSetupFactoryAboutLastStep" oor:op="fuse"><value>false</value></prop></item>
</oor:items>
XCU
DISPLAY=:98 soffice --norestore --calc /tmp/desktop-cu/input.csv > /tmp/soffice.log 2>&1 &
for i in $(seq 1 60); do sleep 1; xdotool search --name "Text Import" 2>/dev/null | grep -q . && break; done
D=$(xdotool search --name "Text Import" | head -1)
xdotool key --window "$D" Return
for i in $(seq 1 60); do sleep 1; xdotool search --name "input.csv" 2>/dev/null | grep -q . && break; done
sleep 3
echo "=== windows ==="
xdotool search --name "." | while read w; do echo "win $w [$(xdotool getwindowname $w 2>/dev/null)]"; done
echo "=== xcu now (tips-related) ==="
grep -o 'Name="[^"]*"' /tmp/loprofile/.config/libreoffice/4/user/registrymodifications.xcu | grep -i 'tip\|first' | head
