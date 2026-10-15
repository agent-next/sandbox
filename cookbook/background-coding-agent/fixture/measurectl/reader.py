"""Reading measurement rows out of a CSV file.

The file grammar is two columns per line: a metric name and a value.
Blank lines and lines whose first non-blank character is ``#`` are
comments.  A header line is not required, but if the first data line has a
non-numeric second column it is taken as a header and skipped.
"""

from __future__ import annotations

import math

COLUMNS = 2


class InputError(Exception):
    """A file could not be read or a row is malformed."""


def _split(line: str, lineno: int) -> tuple[str, str]:
    parts = line.split(",")
    if len(parts) != COLUMNS:
        raise InputError(
            f"line {lineno}: expected {COLUMNS} comma-separated columns, "
            f"got {len(parts)}"
        )
    return parts[0], parts[1]


def _value(text: str, lineno: int) -> float:
    try:
        value = float(text)
    except ValueError:
        raise InputError(
            f"line {lineno}: {text.strip()!r} is not a number"
        ) from None
    if not math.isfinite(value):
        raise InputError(f"line {lineno}: {text.strip()!r} is not finite")
    return value


def read_rows(path: str) -> list[tuple[str, float]]:
    """Return ``[(metric, value), ...]`` in file order.

    Raises :class:`InputError` for an unreadable file, a malformed row or
    an empty metric name.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc.strerror or exc}") from exc

    rows: list[tuple[str, float]] = []
    for lineno, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, raw_value = _split(line, lineno)
        name = name.strip()
        if not rows and name.lower() == "metric":
            # Header row: only when the second column is not a number.
            try:
                float(raw_value)
            except ValueError:
                continue
        if not name:
            raise InputError(f"line {lineno}: empty metric name")
        rows.append((name, _value(raw_value, lineno)))
    return rows
