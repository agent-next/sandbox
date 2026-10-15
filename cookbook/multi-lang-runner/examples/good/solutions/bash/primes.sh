#!/usr/bin/env bash
set -euo pipefail
read -r lo hi
if ((hi < 2)); then
    echo 0
    exit 0
fi
# sieve using an associative array for "is composite"
declare -a composite
for ((i = 2; i * i <= hi; i++)); do
    if [[ -z "${composite[$i]:-}" ]]; then
        for ((j = i * i; j <= hi; j += i)); do
            composite[$j]=1
        done
    fi
done
count=0
for ((i = lo; i <= hi; i++)); do
    if ((i >= 2)) && [[ -z "${composite[$i]:-}" ]]; then
        ((count++))
    fi
done
echo "$count"
