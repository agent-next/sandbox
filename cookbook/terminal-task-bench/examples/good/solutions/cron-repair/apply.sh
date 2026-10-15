#!/usr/bin/env bash
# cron-repair: rewrite the crontab as the six jobs it was meant to hold.
#
# The broken lines carry the commands and (mostly) the intent; the header
# comment is kept.  Each repaired line is expanded with the same grammar the
# verifier uses and compared against the intended value sets, so a line that
# parses but fires at the wrong times is caught here.
set -euo pipefail

WORK="${WORK:?WORK must point at the task work directory}"
cd "$WORK"

# the tick job's minute is the one thing worth preserving from the broken
# file: read it from the line that already names tick.sh
minute="$(awk '/tick\.sh/ {print $1; exit}' crontab)"
case "$minute" in
    ''|*[!0-9]*) echo "cron-repair: cannot read the tick minute" >&2; exit 1 ;;
esac

cat > crontab <<EOF
# bench crontab
# fields: minute hour day-of-month month day-of-week command
# numeric fields only; day-of-week 0=Sunday
$minute * * * * /opt/bench/bin/tick.sh
*/15 * * * * /opt/bench/bin/poll.sh
0 2 * * * /opt/bench/bin/backup.sh
30 4 * * 1-5 /opt/bench/bin/report.sh
0 0 1 * * /opt/bench/bin/monthly.sh
0 6 * * 0 /opt/bench/bin/weekly.sh
EOF

python3 -I - "$WORK" "$minute" <<'PY'
import os
import sys

work, minute = sys.argv[1], sys.argv[2]


def expand(field, low, high):
    if not field or any(ch.isalpha() for ch in field):
        raise ValueError(f"field {field!r} is not numeric")
    out = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            step = int(step_s)
        if step < 1:
            raise ValueError(f"step {step} < 1")
        if part == "*":
            start, end = low, high
        elif "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        if start < low or end > high or start > end:
            raise ValueError(f"{part!r} outside {low}-{high}")
        out.update(range(start, end + 1, step))
    return out


want = {
    "/opt/bench/bin/tick.sh":    ([int(minute)], list(range(24)),
                                  list(range(1, 32)), list(range(1, 13)),
                                  list(range(7))),
    "/opt/bench/bin/poll.sh":    (sorted(range(0, 60, 15)), list(range(24)),
                                  list(range(1, 32)), list(range(1, 13)),
                                  list(range(7))),
    "/opt/bench/bin/backup.sh":  ([0], [2], list(range(1, 32)),
                                  list(range(1, 13)), list(range(7))),
    "/opt/bench/bin/report.sh":  ([30], [4], list(range(1, 32)),
                                  list(range(1, 13)), [1, 2, 3, 4, 5]),
    "/opt/bench/bin/monthly.sh": ([0], [0], [1], list(range(1, 13)),
                                  list(range(7))),
    "/opt/bench/bin/weekly.sh":  ([0], [6], list(range(1, 32)),
                                  list(range(1, 13)), [0]),
}

seen = {}
for lineno, raw in enumerate(open(os.path.join(work, "crontab")), 1):
    text = raw.rstrip("\n")
    if not text or text.lstrip().startswith("#"):
        continue
    fields = text.split(" ")
    if len(fields) != 6 or "" in fields:
        raise SystemExit(f"cron-repair: line {lineno} is not 5 fields + cmd")
    got = [sorted(expand(f, lo, hi)) for f, lo, hi in zip(
        fields[:5], (0, 0, 1, 1, 0), (59, 23, 31, 12, 6))]
    cmd = fields[5]
    if cmd not in want:
        raise SystemExit(f"cron-repair: unexpected job {cmd}")
    if cmd in seen:
        raise SystemExit(f"cron-repair: {cmd} scheduled twice")
    seen[cmd] = True
    for name, g, w in zip(("minute", "hour", "dom", "month", "dow"),
                          got, want[cmd]):
        if g != w:
            raise SystemExit(f"cron-repair: line {lineno} {name} = {g}, "
                             f"want {w}")
missing = set(want) - set(seen)
if missing:
    raise SystemExit(f"cron-repair: jobs missing: {sorted(missing)}")
print(f"cron-repair: {len(seen)} jobs, every field expands as intended")
PY
