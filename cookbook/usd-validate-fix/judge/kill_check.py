#!/usr/bin/env python3
"""Self-test helper: report how a mutant died, or refuse to call it a kill.

Used by judge/selftest.sh so a kill is only counted when the grade produced
a verdict JSON whose `failed_gate` names a real judging gate AND that gate
reported at least one error.  A mutant that dies because a gate raised -- no
JSON at all, or a verdict with no `failed_gate` -- is reported as CRASHED
and is *not* counted as a kill (DEMO-STANDARD: "Every mutant must be killed
BY A JUDGE GATE ... not by the artifact crashing").

Usage: kill_check.py <verdict.json> <comma-separated gates>
  on a kill:   prints "<gate> <error-count>" and exits 0
  otherwise:   prints the reason and exits 1
"""
from __future__ import annotations

import json
import sys

USAGE = "usage: kill_check.py <verdict.json> <comma-separated gates>"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(USAGE, file=sys.stderr)
        return 2
    path, gates = argv[1], set(argv[2].split(","))
    try:
        with open(path, encoding="utf-8") as fh:
            verdict = json.load(fh)
    except FileNotFoundError:
        print("no verdict JSON was written")
        return 1
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print("verdict JSON unreadable: %s" % type(exc).__name__)
        return 1

    if not isinstance(verdict, dict):
        print("verdict JSON is not an object")
        return 1
    gate = verdict.get("failed_gate")
    if not gate:
        print("verdict has no failed_gate")
        return 1
    if gate not in gates:
        # the engine only ever names its own gates; anything else is a bug or
        # a forged verdict, not a kill by a judging gate
        print("failed_gate %r is not a judging gate" % gate)
        return 1
    errors = (verdict.get("gates") or {}).get(gate, {}).get("errors")
    if not isinstance(errors, list) or not errors:
        print("gate %r reported no errors" % gate)
        return 1
    print("%s %d" % (gate, len(errors)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
