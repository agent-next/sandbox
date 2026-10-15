#!/usr/bin/env bash
set -euo pipefail
read -r s
if [[ -z "$s" ]]; then
    exit 0
fi
out=""
prev="${s:0:1}"
count=1
for ((i = 1; i < ${#s}; i++)); do
    ch="${s:$i:1}"
    if [[ "$ch" == "$prev" ]]; then
        ((count++))
    else
        out+="${count}${prev}"
        prev="$ch"
        count=1
    fi
done
out+="${count}${prev}"
echo "$out"
