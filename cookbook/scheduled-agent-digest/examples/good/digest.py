#!/usr/bin/env python3
"""Nightly digest: summarise yesterday's request log as one JSON object.

    python3 -I digest.py --log events.csv --date 2026-10-12 --out digest.json

Reads the CSV event log (`ts,project,ms,code`), keeps only the rows whose UTC
timestamp falls on `--date`, and writes the digest to `--out`.  Runs inside the
sandbox for the few seconds a fire takes; the sandbox is paused the rest of the
day, which is the point of the schedule around it.

Stdlib only.  The aggregates are chosen so an independent implementation (the
judge's sqlite3 oracle) can reproduce them exactly:

* `error_rate` = errors / events (0.0 when there are no rows);
* percentiles are *nearest-rank*: sort the day's latencies and take the value
  at 1-based index `ceil(q * n)`;
* an empty selection is reported as `"status": "no events"` with zeroed
  numerics — never as zeros dressed up as a real day.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

HEADER = ["ts", "project", "ms", "code"]
STATUS_OK = "ok"
STATUS_NO_EVENTS = "no events"


class LogError(RuntimeError):
    """A malformed event log: the run must fail loudly, not half-report."""


def day_of(ts: str) -> str:
    """UTC calendar day of a `YYYY-MM-DDTHH:MM:SSZ` stamp."""
    if len(ts) < 10 or ts[10:11] not in ("T", " "):
        raise LogError(f"timestamp {ts!r} is not YYYY-MM-DDTHH:MM:SSZ")
    return ts[:10]


def percentile(sorted_values: list[int], q: float) -> int:
    """Nearest-rank percentile: 1-based index ceil(q * n) of the sorted list."""
    n = len(sorted_values)
    if n == 0:
        return 0
    return sorted_values[max(1, math.ceil(q * n)) - 1]


def read_events(log: Path, date: str) -> list[dict]:
    """Rows of `log` whose UTC day is `date`, with typed columns."""
    rows: list[dict] = []
    with open(log, newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            raise LogError(f"{log}: the log is empty (no header row)") from None
        if [h.strip() for h in header] != HEADER:
            raise LogError(f"{log}: header {header} is not {HEADER}")
        for lineno, raw in enumerate(reader, start=2):
            if not raw or (len(raw) == 1 and not raw[0].strip()):
                continue  # a blank line is not an event
            if len(raw) != len(HEADER):
                raise LogError(f"{log}:{lineno}: expected {len(HEADER)} "
                               f"fields, found {len(raw)}")
            ts, project, ms, code = (field.strip() for field in raw)
            try:
                ms_value = int(ms)
                code_value = int(code)
            except ValueError:
                raise LogError(f"{log}:{lineno}: ms={ms!r} and/or code={code!r}"
                               f" are not integers") from None
            if ms_value < 0:
                raise LogError(f"{log}:{lineno}: negative latency {ms_value}")
            if day_of(ts) == date:
                rows.append({"ts": ts, "project": project, "ms": ms_value,
                             "code": code_value})
    return rows


def summarise(date: str, rows: list[dict]) -> dict:
    """The digest object.  An empty selection is `"no events"`, not zeros."""
    status = STATUS_OK if rows else STATUS_NO_EVENTS
    events = len(rows)
    errors = sum(1 for r in rows if r["code"] >= 400)
    server_errors = sum(1 for r in rows if r["code"] >= 500)
    latencies = sorted(r["ms"] for r in rows)

    projects: dict[str, dict[str, int]] = {}
    for row in rows:
        entry = projects.setdefault(row["project"],
                                    {"events": 0, "errors": 0})
        entry["events"] += 1
        if row["code"] >= 400:
            entry["errors"] += 1

    busiest = ""
    if projects:
        busiest = min(projects.items(),
                      key=lambda kv: (-kv[1]["events"], kv[0]))[0]

    return {
        "date": date,
        "status": status,
        "events": events,
        "errors": errors,
        "server_errors": server_errors,
        "error_rate": round(errors / events, 6) if events else 0.0,
        "mean_ms": round(sum(latencies) / events, 3) if events else 0.0,
        "p50_ms": percentile(latencies, 0.50),
        "p95_ms": percentile(latencies, 0.95),
        "max_ms": latencies[-1] if events else 0,
        "projects": {name: projects[name] for name in sorted(projects)},
        "busiest_project": busiest,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarise one UTC day of an event log as JSON.")
    parser.add_argument("--log", required=True, type=Path,
                        help="the CSV event log (ts,project,ms,code)")
    parser.add_argument("--date", required=True,
                        help="the UTC day to digest (YYYY-MM-DD)")
    parser.add_argument("--out", required=True, type=Path,
                        help="where to write the digest JSON")
    args = parser.parse_args(argv)

    try:
        rows = read_events(args.log, args.date)
    except (LogError, OSError) as exc:
        print(f"digest: {exc}", file=sys.stderr)
        return 1

    digest = summarise(args.date, rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # write to a sibling temp file and rename, so a failed run never leaves a
    # half-written or stale digest behind
    tmp = args.out.with_name(args.out.name + ".partial")
    tmp.write_text(json.dumps(digest, indent=2, sort_keys=False) + "\n")
    tmp.replace(args.out)
    print(f"digest: {digest['date']} -> {args.out} "
          f"({digest['events']} events, {digest['errors']} errors, "
          f"{digest['status']})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
