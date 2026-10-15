#!/usr/bin/env bash
# P3 primes: count primes p with lo <= p <= hi.
# Uses GNU coreutils `factor` (one invocation, C speed): for n >= 2 the
# first field after the colon is n itself iff n is prime.
set -euo pipefail
read -r lo hi
count=0
for ((i = lo; i <= hi; i++)); do
    if ((i >= 2)); then
        # factor prints "n: f1 f2 ..."; a prime has exactly one factor.
        fields=$(factor "$i" | tr ' ' '\n' | wc -l)
        if ((fields == 2)); then
            count=$((count + 1))
        fi
    fi
done
echo "$count"
