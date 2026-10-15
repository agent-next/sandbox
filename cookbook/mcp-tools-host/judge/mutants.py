#!/usr/bin/env python3
"""Generate single-edit mutants of the known-good MCP server.

Each mutant is one textual edit of ``examples/good/server.py`` (the edit
must match exactly once) and breaks one behaviour the judge gates:

    tool_removed        G2  a tool missing from tools/list
    extra_tool          G2  a fifth tool in tools/list
    wrong_schema        G2  a wrong inputSchema for unit_convert
    wrong_query_result  G3  sqlite rows returned in reverse order
    unsorted_search     G4  file_search matches returned unsorted
    wrong_conversion    G5  factor applied inverted
    traversal_allowed   G7  path containment check disabled
    exits_on_bad_input  G6/G8 the server exits on a malformed expression
    exit_at_launch      G1  the server exits before speaking MCP

Usage: mutants.py [--out DIR]   (default: a fresh temp dir, printed)

Writes ``DIR/<name>/server.py`` for each mutant plus ``DIR/manifest.json``.
Exits non-zero if any edit does not apply exactly once or a mutant does
not parse.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tempfile
from pathlib import Path

GOOD = Path(__file__).resolve().parent.parent / "examples" / "good" / "server.py"

MUTANTS = [
    ("tool_removed",
     "calculate is no longer registered as a tool",
     "@mcp.tool()\ndef calculate(expression: str) -> dict:",
     "def calculate(expression: str) -> dict:"),
    ("extra_tool",
     "a fifth tool appears in tools/list",
     "@mcp.tool()\ndef file_search(",
     "@mcp.tool()\ndef _extra() -> dict:\n"
     "    \"\"\"extra tool that must not be there\"\"\"\n"
     "    return {\"ping\": \"pong\"}\n"
     "\n"
     "\n"
     "@mcp.tool()\ndef file_search("),
    ("wrong_schema",
     "unit_convert declares value as string, not number",
     "def unit_convert(value: float, from_unit: str, to_unit: str) -> dict:",
     "def unit_convert(value: str, from_unit: str, to_unit: str) -> dict:"),
    ("wrong_query_result",
     "sqlite_query returns the rows in reverse order",
     "rows = [list(r) for r in cur.fetchall()]",
     "rows = [list(r) for r in cur.fetchall()][::-1]"),
    ("unsorted_search",
     "file_search returns matches sorted backwards",
     "        hits.sort()",
     "        hits.sort(reverse=True)"),
    ("wrong_conversion",
     "unit factors applied inverted",
     "            return value * table[src] / table[dst]",
     "            return value * table[dst] / table[src]"),
    ("traversal_allowed",
     "the workspace containment check is disabled",
     "    if target != base and base not in target.parents:",
     "    if False and target != base and base not in target.parents:"),
    ("exits_on_bad_input",
     "the server exits when calculate gets a malformed expression",
     "    except Exception as exc:\n"
     "        # Malformed input, forbidden constructs, division by zero: a\n"
     "        # clean tool error (isError: true), never a crash.\n"
     "        raise ValueError(f\"{type(exc).__name__}: {exc}\") from exc\n"
     "\n"
     "\n"
     "def main() -> int:",
     "    except Exception:\n"
     "        import sys\n"
     "        sys.exit(1)\n"
     "\n"
     "\n"
     "def main() -> int:"),
    ("exit_at_launch",
     "the server exits before speaking MCP at all",
     "def main() -> int:",
     "def main() -> int:\n"
     "    import sys\n"
     "    sys.exit(0)"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    out = args.out or Path(tempfile.mkdtemp(prefix="mcp-mutants-"))
    out.mkdir(parents=True, exist_ok=True)
    src = GOOD.read_text(encoding="utf-8")

    manifest = {}
    failures = []
    for name, what, old, new in MUTANTS:
        n = src.count(old)
        if n != 1:
            print(f"mutants: FAIL — edit for {name} matched {n} times "
                  f"(expected exactly 1)", file=sys.stderr)
            failures.append(name)
            continue
        mutated = src.replace(old, new)
        try:
            ast.parse(mutated)
        except SyntaxError as exc:
            print(f"mutants: FAIL — {name} does not parse: {exc}",
                  file=sys.stderr)
            failures.append(name)
            continue
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "server.py").write_text(mutated, encoding="utf-8")
        manifest[name] = {"edit": what, "path": str(d / "server.py")}
        print(f"mutants: wrote {name} ({what})")

    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(f"mutants: {len(manifest)}/{len(MUTANTS)} mutants in {out}")
    return 1 if failures or len(manifest) != len(MUTANTS) else 0


if __name__ == "__main__":
    raise SystemExit(main())
