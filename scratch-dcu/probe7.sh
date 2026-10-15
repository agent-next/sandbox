#!/usr/bin/env bash
set -ux
export DISPLAY=:97
pkill Xvfb 2>/dev/null; pkill fluxbox 2>/dev/null; sleep 1
Xvfb :97 -screen 0 1024x768x24 -nolisten tcp > /tmp/xvfb.log 2>&1 &
for i in $(seq 1 50); do xdpyinfo -display :97 >/dev/null 2>&1 && break; sleep 0.2; done
fluxbox > /tmp/fluxbox.log 2>&1 &
sleep 3
mkdir -p /tmp/desktop-cu /tmp/loprofile
printf 'item,qty,price\napple,3,0.50\nbanana,2,0.25\ncherry,5,1.00\n' > /tmp/desktop-cu/input.csv
rm -rf /tmp/loprofile; mkdir -p /tmp/loprofile
export HOME=/tmp/loprofile
cd /tmp
DISPLAY=:97 soffice --headless --terminate_after_init > /tmp/seed.log 2>&1
echo "=== profile files ==="
find /tmp/loprofile -maxdepth 3 -name 'registrymodifications*' -o -maxdepth 3 -name '*.xcu' | head
echo "=== grep tip/firstrun in xcu ==="
grep -o 'Name="[^"]*"' /tmp/loprofile/.config/libreoffice/4/user/registrymodifications.xcu | grep -i 'tip\|firstrun\|welcome' | head -20
echo "=== lines around Tips ==="
grep -n -i 'tip\|firstrunning' /tmp/loprofile/.config/libreoffice/4/user/registrymodifications.xcu | head -20
DISPLAY=:97 soffice --norestore --calc /tmp/desktop-cu/input.csv > /tmp/soffice.log 2>&1 &
for i in $(seq 1 60); do sleep 1; xdotool search --name "Text Import" 2>/dev/null | grep -q . && break; done
D=$(xdotool search --name "Text Import" | head -1)
xdotool key --window "$D" Return
for i in $(seq 1 60); do sleep 1; xdotool search --name "input.csv" 2>/dev/null | grep -q . && break; done
sleep 3
echo "=== windows ==="
xdotool search --name "." | while read w; do echo "win $w [$(xdotool getwindowname $w 2>/dev/null)]"; done
