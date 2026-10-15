"""Deterministic generator for the nightly-digest event-log fixtures.

The judge grades a digest built for a given *log date*; a fixture log holds
that day's events plus a few rows before and after it (late-arriving events
early the next morning, and a few from the previous day) so a digester that
filters by date is distinguished from one that just totals the file.

Every number comes from `random` seeded per night, so the files are
byte-identical on every machine.  Usage:

    python3 -I judge/make_fixtures.py --outdir judge/fixtures
"""

import argparse
import csv
import datetime as dt
import random
from pathlib import Path

SEED = 20261015


PROJECTS = ["web", "api", "batch", "auth"]
# per-project latency windows in ms
LAT = {"web": (40, 900), "api": (10, 300), "batch": (2000, 20000),
       "auth": (5, 60)}
# relative event volumes, matching a service where web/api dominate
WEIGHTS = [0.34, 0.30, 0.26, 0.10]
# response-code mix: 84 % success, 8 % client errors, 8 % server errors
CODES = [(200, 0.80), (201, 0.04), (400, 0.04), (404, 0.05), (429, 0.03),
         (500, 0.02), (503, 0.02)]

# night -> (log date, fire date, rows on the log date, rows in the two hours
#           after midnight, rows from the previous day)
NIGHTS = [
    ("2026-10-12", "2026-10-13", 128, 7, 3),
    ("2026-10-13", "2026-10-14", 141, 5, 4),
    ("2026-10-14", "2026-10-15", 96, 11, 2),
]

HEADER = ["ts", "project", "ms", "code"]


def pick_code(rng):
    r = rng.random()
    acc = 0.0
    for code, weight in CODES:
        acc += weight
        if r < acc:
            return code
    return CODES[-1][0]


def stamp(rng, day, hour_lo, hour_hi):
    start = dt.datetime.strptime(day, "%Y-%m-%d").replace(
        tzinfo=dt.timezone.utc)
    return (start + dt.timedelta(
        seconds=rng.randrange(hour_lo * 3600, hour_hi * 3600))).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def night_rows(rng, log_day, n_main, n_spill, n_stale):
    prev = (dt.date.fromisoformat(log_day) - dt.timedelta(days=1)).isoformat()
    rows = []
    for _ in range(n_main):
        project = rng.choices(PROJECTS, WEIGHTS)[0]
        lo, hi = LAT[project]
        rows.append([stamp(rng, log_day, 0, 24), project,
                     rng.randrange(lo, hi + 1), pick_code(rng)])
    for _ in range(n_spill):
        project = rng.choices(PROJECTS, WEIGHTS)[0]
        lo, hi = LAT[project]
        # late arrivals in the two hours after midnight of the fire day
        rows.append([stamp(rng, str(dt.date.fromisoformat(log_day)
                                    + dt.timedelta(days=1)), 0, 2),
                     project, rng.randrange(lo, hi + 1), pick_code(rng)])
    for _ in range(n_stale):
        project = rng.choices(PROJECTS, WEIGHTS)[0]
        lo, hi = LAT[project]
        rows.append([stamp(rng, prev, 0, 24), project,
                     rng.randrange(lo, hi + 1), pick_code(rng)])
    rng.shuffle(rows)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    for i, (log_day, fire_day, n_main, n_spill, n_stale) in enumerate(
            NIGHTS, start=1):
        rng = random.Random(SEED + i)
        rows = night_rows(rng, log_day, n_main, n_spill, n_stale)
        with open(out / f"night{i}.csv", "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(HEADER)
            writer.writerows(rows)
        print(f"{out}/night{i}.csv: log_date={log_day} fire={fire_day} "
              f"rows={len(rows)} (log-date {n_main}, next-morning {n_spill}, "
              f"previous-day {n_stale})")

    # negative controls
    with open(out / "empty.csv", "w", newline="") as fh:
        fh.write(",".join(HEADER) + "\n")
    print(f"{out}/empty.csv: header only (the empty-log control)")
    with open(out / "malformed.csv", "w", newline="") as fh:
        fh.write(",".join(HEADER) + "\n")
        fh.write("2026-10-12T00:00:00Z,web,120,200\n")
        fh.write("2026-10-12T01:00:00Z,api,not-a-number,200\n")
        fh.write("2026-10-12T02:00:00Z,web\n")
    print(f"{out}/malformed.csv: header plus three malformed rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
