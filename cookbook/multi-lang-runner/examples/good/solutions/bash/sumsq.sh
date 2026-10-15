#!/usr/bin/env bash
set -euo pipefail
read -r n
total=0
cap=1000000000000000000
for ((i = 0; i < n; i++)); do
    read -r x
    total=$((total + x * x))
    if ((total > cap)); then
        total=$cap
        break
    fi
done
echo "$total"
