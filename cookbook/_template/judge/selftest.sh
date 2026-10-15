#!/bin/bash
# selftest.sh — proves the judge can fail. Required before the demo is
# done (cookbook/DEMO-STANDARD.md, Judge rules):
#   * examples/good passes
#   * every known-bad artifact (examples/bad or judge/mutants.py) fails
#     at least one gate — print the failing gate per mutant
#   * kill rate >= 90 %
#   * two grades of the good artifact with the same --seed are
#     byte-identical except the "timing" key
#   * checksums of judge/ before and after grading are equal
set -euo pipefail
echo "TODO: implement judge/selftest.sh" >&2
exit 1
