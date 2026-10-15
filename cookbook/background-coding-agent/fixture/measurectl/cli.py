"""Command-line interface for measurectl."""

from __future__ import annotations

import argparse
import sys

from .reader import InputError, read_rows
from .stats import Metric, summarise

SORT_KEYS = ("name", "count")

EXIT_OK = 0
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="measurectl",
        description="Summarise a CSV file of measurements.",
    )
    parser.add_argument("path", help="CSV file to summarise")
    parser.add_argument(
        "--sort",
        choices=SORT_KEYS,
        default="name",
        help="order the table by this column (default: name)",
    )
    return parser


def ordered(metrics: dict[str, Metric], key: str) -> list[Metric]:
    """Order metrics for display; ties break on name for a stable table."""
    if key == "count":
        return sorted(metrics.values(), key=lambda m: (-m.count, m.name))
    return sorted(metrics.values(), key=lambda m: m.name)


def format_number(value: float) -> str:
    """Render a float for the table: no trailing zeros, at most 6 places."""
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-", "-0") else text


def render_table(metrics: list[Metric]) -> str:
    rows = [
        (
            metric.name,
            str(metric.count),
            format_number(metric.mean),
            format_number(metric.min),
            format_number(metric.max),
        )
        for metric in metrics
    ]
    headers = ("metric", "count", "mean", "min", "max")
    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows))
        if rows
        else len(headers[i])
        for i in range(len(headers))
    ]

    def line(cells: tuple[str, ...]) -> str:
        return "  ".join(
            cells[i].ljust(widths[i]) for i in range(len(headers))
        ).rstrip()

    lines = [line(headers), line(tuple("-" * width for width in widths))]
    lines.extend(line(row) for row in rows)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        rows = read_rows(args.path)
    except InputError as exc:
        print(f"measurectl: {exc}", file=sys.stderr)
        return EXIT_USAGE
    metrics = summarise(rows)
    if not metrics:
        print(f"measurectl: {args.path} contains no data rows", file=sys.stderr)
        return EXIT_USAGE
    print(render_table(ordered(metrics, args.sort)))
    return EXIT_OK
