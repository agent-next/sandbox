#!/usr/bin/env bash
# P3 primes: count primes p with lo <= p <= hi.
# One GNU coreutils `factor` invocation reads the whole range from stdin
# (C speed): for n >= 2 it prints "n: f1 f2 ...", so n is prime iff the
# line has exactly two fields (n and a single factor).
set -euo pipefail
read -r lo hi
start=$((lo < 2 ? 2 : lo))
if ((hi < start)); then
    echo 0
    exit 0
fi
seq "$start" "$hi" | factor -- 2>/dev/null | awk 'NF == 2 { n++ } END { print n + 0 }'
