#!/usr/bin/env bash
# Proves the judge can fail: the known-good artifacts pass, every generated mutant fails at
# least one gate, grading is deterministic, and grading leaves judge/ untouched.
set -euo pipefail
J=$(cd "$(dirname "$0")" && pwd)
GOOD="$J/../examples/good"
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
before=$(cd "$J" && find . -type f ! -name VERSIONS.txt -print0 | sort -z | xargs -0 sha256sum | sha256sum)

for a in "Tally-sim.zip ios-sim" "Tally.ipa ios" "SbxBar-mac.zip mac"; do
  set -- $a
  "$J/grade.sh" "$GOOD/$1" "$2" --json "$W/$1.1.json" >/dev/null || { echo "good artifact failed: $1"; exit 1; }
  "$J/grade.sh" "$GOOD/$1" "$2" --json "$W/$1.2.json" >/dev/null
  cmp -s "$W/$1.1.json" "$W/$1.2.json" || { echo "non-deterministic verdict: $1"; exit 1; }
  echo "good  PASS  $1"
done

total=0; killed=0
while read -r f kind what; do
  total=$((total + 1))
  if "$J/grade.sh" "$f" "$kind" --json "$W/m.json" >/dev/null; then
    echo "MISSED      $(basename "$f") ($what)"
  else
    killed=$((killed + 1))
    gates=$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(",".join(n for n,g in sorted(d["gates"].items()) if not g["pass"] and g["measured"]!="not reached"))' "$W/m.json")
    echo "bad   FAIL  $(basename "$f") [$gates] ($what)"
  fi
done < <(python3 "$J/mutants.py" "$GOOD" "$W/mutants")

after=$(cd "$J" && find . -type f ! -name VERSIONS.txt -print0 | sort -z | xargs -0 sha256sum | sha256sum)
[ "$before" = "$after" ] || { echo "judge/ changed during grading"; exit 1; }
echo "kill rate: $killed/$total"
[ "$killed" -eq "$total" ] && [ "$total" -ge 5 ]
