#!/usr/bin/env bash
# Find the config paths in LibreOffice 7.4 that disable the Tip of the Day.
set -u
X=/tmp/loprofile/.config/libreoffice/4/user/registrymodifications.xcu
echo "=== exists: $([ -f $X ] && echo yes || echo no) ==="
grep -o -i 'ShowTips\|TipsOnStart\|/Help/[A-Za-z]*\|/Misc/[A-Za-z]*' $X | sort -u | head -30
echo "=== all Help items ==="
grep -o 'oor:path="[^"]*Help[^"]*"' $X | sort -u
echo "=== binary strings for tip ==="
strings /usr/lib/libreoffice/pro/libreoffice-impress* 2>/dev/null | head -0
for lib in $(ls /usr/lib/libreoffice/pro/*.so 2>/dev/null | head -200); do
  if strings -a "$lib" 2>/dev/null | grep -q 'ShowTips'; then echo "HIT $lib"; strings -a "$lib" | grep -o -A0 'ShowTips\|TipsOnStart' | head -3; fi
done 2>/dev/null | head -20
