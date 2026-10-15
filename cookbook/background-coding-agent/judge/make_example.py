#!/usr/bin/env python3
"""Regenerate examples/good/ (delivery.patch + PR.md) from the fixture.

The good delivery is a small, deterministic edit of the pinned fixture:
one new module and two edits to the CLI.  Generating it from the fixture
(rather than storing a diff that can silently stop applying) keeps the
example reproducible and gives judge/mutants.py stable anchors to mutate.

Usage: python3 -I judge/make_example.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

JDIR = Path(__file__).resolve().parent
DEMO = JDIR.parent
FIXTURE = DEMO / "fixture"
OUT = DEMO / "examples" / "good"

JSONOUT = '''"""The `--json` summary document (see ISSUE.md)."""

from __future__ import annotations

import json

from .stats import Metric

SCHEMA = "measurectl/summary/v1"


def build_document(metrics: dict[str, Metric], total_count: int) -> dict:
    """Build the JSON-serialisable summary document.

    Metrics are ordered by name in Unicode code point order, which is what
    ``sorted`` on ``str`` gives.  Counts stay integers; the remaining
    fields are floats.
    """
    return {
        "schema": SCHEMA,
        "total_count": total_count,
        "metrics": [
            {
                "name": metric.name,
                "count": metric.count,
                "sum": metric.total,
                "mean": metric.mean,
                "min": metric.min,
                "max": metric.max,
            }
            for metric in sorted(metrics.values(), key=lambda m: m.name)
        ],
    }


def render(document: dict) -> str:
    """Render the document as one JSON object."""
    return json.dumps(document, indent=2)
'''

# (old, new) applied to measurectl/cli.py, in order; each must match once.
CLI_EDITS = [
    (
        "from .reader import InputError, read_rows\n",
        "from .jsonout import build_document, render\n"
        "from .reader import InputError, read_rows\n",
    ),
    (
        '''    parser.add_argument(
        "--sort",
        choices=SORT_KEYS,
        default="name",
        help="order the table by this column (default: name)",
    )
    return parser''',
        '''    parser.add_argument(
        "--sort",
        choices=SORT_KEYS,
        default="name",
        help="order the table by this column (default: name)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the summary as one JSON document instead of a table",
    )
    return parser''',
    ),
    (
        '''    print(render_table(ordered(metrics, args.sort)))
    return EXIT_OK''',
        '''    if args.json:
        print(render(build_document(metrics, total_count=len(rows))))
        return EXIT_OK
    print(render_table(ordered(metrics, args.sort)))
    return EXIT_OK''',
    ),
]

PR_MD = """# Add `--json` output to measurectl

## Summary

Implements `ISSUE.md`. A new `--json` flag prints the summary as a single
JSON document instead of the fixed-width table, so callers no longer have
to scrape column widths.

- `measurectl/jsonout.py` (new): builds and renders the
  `measurectl/summary/v1` document. Metrics are sorted by name in Unicode
  code point order; `count` stays an integer and the other fields are
  JSON numbers.
- `measurectl/cli.py`: adds the `--json` flag, wires it to the new
  module, and returns before the table path so `--json` output is the
  only thing on stdout. `--json` deliberately ignores `--sort` — the JSON
  array is always sorted by name.

Error handling, the table output, the existing flags and the exit codes
are unchanged. No new dependencies: the document is built from the
existing accumulator and serialised with the standard library.

## Test plan

- `python -m pytest` — the existing suite (26 tests) still passes; no
  test file was touched.
- `python -m measurectl --json data/sample.csv` — exits 0 and matches the
  schema in `ISSUE.md` (`total_count` 9, `alpha` sum 6.5, mean
  6.5 / 3).
- `python -m measurectl --json <missing-file>` — exits 2, stderr only.
- `python -m ruff check .` — clean.
"""


def build_worktree(workdir: Path) -> None:
    """Copy the fixture into workdir as a git repo with the change applied."""
    subprocess.run(["git", "init", "-q", str(workdir)], check=True)
    subprocess.run(["git", "-C", str(workdir), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(workdir), "-c", "user.email=demo@example.invalid",
         "-c", "user.name=demo", "commit", "-qm", "base"],
        check=True,
    )


def apply_change(root: Path) -> None:
    cli = root / "measurectl" / "cli.py"
    text = cli.read_text()
    for old, new in CLI_EDITS:
        if text.count(old) != 1:
            raise SystemExit(f"make_example: anchor not found exactly once:\n{old!r}")
        text = text.replace(old, new)
    cli.write_text(text)
    (root / "measurectl" / "jsonout.py").write_text(JSONOUT)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="measurectl-example-") as td:
        work = Path(td) / "fixture"
        subprocess.run(["cp", "-r", str(FIXTURE), str(work)], check=True)
        for junk in work.rglob("__pycache__"):
            subprocess.run(["rm", "-rf", str(junk)], check=True)
        build_worktree(work)
        apply_change(work)
        subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
        diff = subprocess.run(
            ["git", "-C", str(work), "-c", "user.email=demo@example.invalid",
             "-c", "user.name=demo", "diff", "--cached", "--no-color",
             "--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/"],
            check=True, capture_output=True, text=True,
        ).stdout
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "delivery.patch").write_text(diff)
    (OUT / "PR.md").write_text(PR_MD)
    print(f"make_example: wrote {OUT/'delivery.patch'} "
          f"({len(diff.splitlines())} lines)")
    print(f"make_example: wrote {OUT/'PR.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
