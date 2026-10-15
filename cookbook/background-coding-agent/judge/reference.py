#!/usr/bin/env python3
"""Independent reference implementation of the issue's summary schema.

This is the judge's *oracle*: it recomputes every statistic from the raw
CSV so the artifact is never graded against itself.  It deliberately does
not import, call or copy `measurectl`:

  * it parses with `csv.reader` rather than `str.split(",")`;
  * it accumulates with `statistics.fsum` and `statistics.fmean`, which
    are correctly rounded and take a different code path from the
    fixture's naive running loop.

The judge compares the artifact's JSON against this module and requires
agreement to 1e-9 relative (counts exactly).  A correct implementation
lands ~1e-16 away; a rounded, truncated or hardcoded one does not.
"""

from __future__ import annotations

import csv
import io
import math
import statistics

SCHEMA = "measurectl/summary/v1"


class ReferenceError(Exception):
    """The input could not be parsed as a measurement file."""


def parse(text: str) -> list[tuple[str, float]]:
    """Return ``[(metric, value), ...]`` in file order.

    Same grammar as the fixture documents: blank lines and ``#`` comment
    lines are ignored, a leading ``metric,value`` header is skipped, metric
    names are stripped and values must be finite floats.
    """
    rows: list[tuple[str, float]] = []
    reader = csv.reader(io.StringIO(text))
    for lineno, cells in enumerate(reader, start=1):
        if not cells:
            continue
        joined = ",".join(cells).strip()
        if not joined or joined.startswith("#"):
            continue
        if len(cells) != 2:
            raise ReferenceError(
                f"line {lineno}: expected 2 columns, got {len(cells)}"
            )
        name = cells[0].strip()
        raw = cells[1].strip()
        if not rows and name.lower() == "metric":
            try:
                float(raw)
            except ValueError:
                continue
        if not name:
            raise ReferenceError(f"line {lineno}: empty metric name")
        try:
            value = float(raw)
        except ValueError:
            raise ReferenceError(f"line {lineno}: {raw!r} is not a number") from None
        if not math.isfinite(value):
            raise ReferenceError(f"line {lineno}: {raw!r} is not finite")
        rows.append((name, value))
    return rows


def summarise(rows: list[tuple[str, float]]) -> dict:
    """Build the schema document for ``rows`` (independent computation)."""
    grouped: dict[str, list[float]] = {}
    for name, value in rows:
        grouped.setdefault(name, []).append(value)

    metrics = []
    for name in sorted(grouped):
        values = grouped[name]
        metrics.append(
            {
                "name": name,
                "count": len(values),
                "sum": statistics.fsum(values),
                "mean": statistics.fmean(values),
                "min": min(values),
                "max": max(values),
            }
        )
    return {
        "schema": SCHEMA,
        "total_count": len(rows),
        "metrics": metrics,
    }


def summarise_text(text: str) -> dict:
    return summarise(parse(text))


if __name__ == "__main__":
    import json
    import sys

    with open(sys.argv[1], encoding="utf-8") as handle:
        print(json.dumps(summarise_text(handle.read()), indent=2))
