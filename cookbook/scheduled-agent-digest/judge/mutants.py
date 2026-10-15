#!/usr/bin/env python3
"""Generate single-edit mutants of the known-good artifact for selftest.

Each mutant copies the good artifact and applies exactly one textual edit,
so the self-test proves the judge catches a specific, named defect.

Usage:
    python3 judge/mutants.py <good-dir> <out-dir>
    python3 judge/mutants.py --list
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# (name, file, old, new) — each pair is one single-line (or single-expression)
# edit.  The judge must kill every one of these.
MUTANTS: list[tuple[str, str, str, str]] = [
    # --- digest.py mutants -------------------------------------------------
    (
        "no-events-as-zero",
        "digest.py",
        "    status = STATUS_OK if rows else STATUS_NO_EVENTS",
        "    status = STATUS_OK",
    ),
    (
        "all-rows-counted",
        "digest.py",
        "            if day_of(ts) == date:",
        "            if True:",
    ),
    (
        "mean-unrounded",
        "digest.py",
        '        "mean_ms": round(sum(latencies) / events, 3) if events else 0.0,',
        '        "mean_ms": sum(latencies) / events if events else 0.0,',
    ),
    (
        # a plausible-looking but wrong rate: 5xx-only over events
        "error-rate-wrong",
        "digest.py",
        '        "error_rate": round(errors / events, 6) if events else 0.0,',
        '        "error_rate": round(server_errors / events, 6) if events else 0.0,',
    ),
    (
        "p95-off-by-one",
        "digest.py",
        "    return sorted_values[max(1, math.ceil(q * n)) - 1]",
        "    return sorted_values[max(1, math.ceil(q * n))]",
    ),
    (
        "busiest-tie-wrong",
        "digest.py",
        "        busiest = min(projects.items(),\n"
        "                      key=lambda kv: (-kv[1][\"events\"], kv[0]))[0]",
        "        busiest = next(iter(projects))",
    ),
    (
        "extra-key",
        "digest.py",
        '        "busiest_project": busiest,',
        '        "busiest_project": busiest,\n'
        '        "generated_at": "2026-10-15T02:00:00Z",',
    ),
    (
        # bad input must not be silently swallowed: this one skips malformed
        # rows instead of failing, so the judge must catch it at G7
        "malformed-swallowed",
        "digest.py",
        "            except ValueError:\n"
        "                raise LogError(f\"{log}:{lineno}: ms={ms!r} and/or code={code!r}\"\n"
        "                               f\" are not integers\") from None",
        "            except ValueError:\n"
        "                continue",
    ),
    # --- schedule.json mutants ----------------------------------------------
    (
        "paused-skipped",
        "schedule.json",
        '{"name": "pause the sandbox", "uses": "pause"}',
        '{"name": "pause the sandbox", "uses": "collect"}',
    ),
    (
        "cron-hour-3",
        "schedule.json",
        '"0 2 * * *"',
        '"0 3 * * *"',
    ),
]


def list_mutants() -> int:
    for name, fname, _old, _new in MUTANTS:
        print(f"{name:24s}  {fname}")
    return 0


def generate(good_dir: Path, out_dir: Path) -> int:
    good_dir = Path(good_dir).resolve()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, fname, old, new in MUTANTS:
        dest = out_dir / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(good_dir, dest)
        target = dest / fname
        text = target.read_text()
        if old not in text:
            print(f"mutants: {name}: pattern not found in {fname}", file=sys.stderr)
            return 1
        if text.count(old) != 1:
            print(f"mutants: {name}: pattern not unique in {fname}", file=sys.stderr)
            return 1
        target.write_text(text.replace(old, new, 1))
        print(f"mutants: {name} -> {dest}")

    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("good_dir", nargs="?")
    ap.add_argument("out_dir", nargs="?")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)

    if args.list:
        return list_mutants()
    if not args.good_dir or not args.out_dir:
        ap.error("need <good-dir> <out-dir> (or --list)")
    return generate(Path(args.good_dir), Path(args.out_dir))


if __name__ == "__main__":
    raise SystemExit(main())
