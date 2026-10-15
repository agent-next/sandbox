#!/usr/bin/env bash
# Verifier for task cron-repair.
#
# Oracle: spec mask over the expanded field sets.  expected.json records the
# intent as the exact set of minutes/hours/days/months/weekdays each job
# must match.  The verifier parses the repaired crontab with its own field
# expander and compares those sets numerically, so a line with the right
# command but the wrong schedule fails.
set -euo pipefail

WORK="${1:?usage: verify.sh <work-dir>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 -I - "$WORK" "$HERE/expected.json" <<'PY'
import json
import os
import sys

work, exp_path = sys.argv[1], sys.argv[2]
exp = json.load(open(exp_path))
path = os.path.join(work, exp["crontab"])
problems = []


def bad(msg):
    problems.append(msg)
    print("FAIL:", msg)


def expand(field, low, high):
    """Expand one cron field to the set of values it matches.

    Supports `*`, `n`, `a-b`, `*/n` and `a-b/n`, comma separated.  Anything
    else raises ValueError.
    """
    if not field or any(ch.isalpha() for ch in field):
        raise ValueError(f"field {field!r} is empty or uses names")
    out = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            if not step_s.isdigit():
                raise ValueError(f"step {step_s!r} is not a number")
            step = int(step_s)
        if step < 1:
            raise ValueError(f"step {step} must be >= 1")
        if part == "*":
            start, end = low, high
        elif "-" in part:
            a, b = part.split("-", 1)
            if not (a.isdigit() and b.isdigit()):
                raise ValueError(f"range {part!r} is not numeric")
            start, end = int(a), int(b)
        else:
            if not part.isdigit():
                raise ValueError(f"value {part!r} is not numeric")
            start = end = int(part)
        if start < low or end > high or start > end:
            raise ValueError(f"{part!r} is outside {low}-{high}")
        out.update(range(start, end + 1, step))
    if not out:
        raise ValueError(f"field {field!r} matches nothing")
    return out


if not os.path.isfile(path):
    bad(f"{exp['crontab']} is missing")
    sys.exit(1)

lines = []
for lineno, raw in enumerate(open(path), start=1):
    text = raw.rstrip("\n")
    if text.strip() == "" or text.lstrip().startswith("#"):
        continue
    if text != text.strip():
        bad(f"line {lineno} has leading/trailing whitespace")
    fields = text.split(" ")
    if "" in fields:
        bad(f"line {lineno} is not single-space separated")
    lines.append((lineno, fields))

if len(lines) != exp["line_count"]:
    bad(f"{len(lines)} active lines, expected {exp['line_count']}")

# compare as a multiset of (schedule sets, command)
want = [row for row in exp["lines"]]
got = []
for lineno, fields in lines:
    if len(fields) != 6:
        bad(f"line {lineno} has {len(fields)} fields, expected 5 + command")
        continue
    minute, hour, dom, month, dow, cmd = fields
    row = {"command": cmd, "schedule": " ".join(fields[:5])}
    for name, field, low, high in (
            ("minute", minute, 0, 59), ("hour", hour, 0, 23),
            ("dom", dom, 1, 31), ("month", month, 1, 12),
            ("dow", dow, 0, 6)):
        try:
            row[name] = sorted(expand(field, low, high))
        except ValueError as exc:
            bad(f"line {lineno} {name} field: {exc}")
            row[name] = None
    got.append((lineno, row))

if not problems:
    by_cmd = {}
    for lineno, row in got:
        by_cmd.setdefault(row["command"], []).append((lineno, row))
    for row in want:
        cands = by_cmd.get(row["command"], [])
        if not cands:
            bad(f"no line schedules {row['command']}")
            continue
        if len(cands) > 1:
            bad(f"{row['command']} is scheduled on "
                f"{len(cands)} lines: {[c[0] for c in cands]}")
        lineno, actual = cands[0]
        for key in ("minute", "hour", "dom", "month", "dow"):
            if actual.get(key) != row[key]:
                bad(f"line {lineno} ({row['command']}) {key} expands to "
                    f"{actual.get(key)}, expected {row[key]}")
    for cmd in by_cmd:
        if cmd not in {r["command"] for r in want}:
            bad(f"unexpected job scheduled: {cmd}")

if problems:
    print(f"cron-repair: {len(problems)} problem(s)")
    sys.exit(1)
print(f"cron-repair: OK ({exp['line_count']} jobs, every field expands to "
      "the intended set)")
PY
