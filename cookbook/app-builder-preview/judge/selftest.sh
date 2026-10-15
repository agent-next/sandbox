#!/bin/sh
# Self-test: prove the judge can fail. See SPEC.md.
#
# 1. the known-good example passes grade.sh;
# 2. every scripted mutant of it fails at least one gate;
# 3. grading is deterministic: two runs of the good artifact produce
#    byte-identical verdicts (the `timing` key is excluded - wall times are
#    inherently noisy);
# 4. judge/ checksums are unchanged after everything.
#
# Prints the kill rate; exits non-zero unless the good app passes, every
# mutant is killed, determinism holds and judge/ is untouched.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
GOOD="$HERE/../examples/good/app"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

sha() { find "$HERE" -type f ! -name '*.pyc' ! -path '*__pycache__*' \
        -exec sha256sum {} + | sort -k2; }
sha > "$WORK/sha_before"

echo "selftest: generating mutants"
MUT="$WORK/mutants"
python3 "$HERE/mutants.py" "$MUT" > "$WORK/names.txt"

echo "selftest: grading known-good"
if bash "$HERE/grade.sh" "$GOOD" --json "$WORK/good.json" >/dev/null 2>&1; then
    echo "selftest: known-good: PASS"
else
    echo "selftest: known-good FAILED (judge broken or good example broken)" >&2
    exit 1
fi

killed=0
total=0
fails=""
while read -r name; do
    total=$((total + 1))
    if bash "$HERE/grade.sh" "$MUT/$name" --json "$WORK/$name.json" \
            >/dev/null 2>&1; then
        fails="$fails $name"
        echo "selftest: mutant $name: SURVIVED (judge did not kill it)" >&2
    else
        killed=$((killed + 1))
        gate=$(python3 - "$WORK/$name.json" <<'EOF'
import json, sys
v = json.load(open(sys.argv[1]))
failed = [k for k, g in v.get("gates", {}).items()
          if isinstance(g, dict) and not g.get("pass")]
print(",".join(failed) or "?")
EOF
)
        echo "selftest: mutant $name: killed (gate: $gate)"
    fi
done < "$WORK/names.txt"

rate=$(python3 -c "print(f'{$killed / $total * 100:.0f}')")
echo "selftest: kill rate: $killed/$total = ${rate}%"
if [ "$killed" -lt "$total" ]; then
    echo "selftest: SURVIVED mutants:$fails" >&2
fi

echo "selftest: determinism check (two grades of the good artifact)"
bash "$HERE/grade.sh" "$GOOD" --json "$WORK/det1.json" >/dev/null
bash "$HERE/grade.sh" "$GOOD" --json "$WORK/det2.json" >/dev/null
if python3 - "$WORK/det1.json" "$WORK/det2.json" <<'EOF'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
a.pop("timing", None), b.pop("timing", None)
sys.exit(0 if a == b else 1)
EOF
then
    echo "selftest: determinism: OK"
else
    echo "selftest: determinism FAILED (two runs differ beyond timing)" >&2
    exit 1
fi

# A failing verdict quotes tool output, which can carry the per-run scratch
# dir; grade the build-breaking mutant twice and require the same
# byte-identical-verdict guarantee there. Without _grade.py's workdir
# scrubbing this fails on the temp path inside the npm error text.
echo "selftest: determinism check (two grades of a failing artifact)"
bash "$HERE/grade.sh" "$MUT/build_broken" --json "$WORK/detf1.json" >/dev/null 2>&1 || true
bash "$HERE/grade.sh" "$MUT/build_broken" --json "$WORK/detf2.json" >/dev/null 2>&1 || true
if python3 - "$WORK/detf1.json" "$WORK/detf2.json" <<'EOF'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
a.pop("timing", None), b.pop("timing", None)
sys.exit(0 if a == b else 1)
EOF
then
    echo "selftest: determinism on a failing artifact: OK"
else
    echo "selftest: determinism FAILED on a failing artifact (two runs \
differ beyond timing)" >&2
    exit 1
fi

sha > "$WORK/sha_after"
if cmp -s "$WORK/sha_before" "$WORK/sha_after"; then
    echo "selftest: judge/ checksums unchanged"
else
    echo "selftest: judge/ CHANGED during grading:" >&2
    diff "$WORK/sha_before" "$WORK/sha_after" >&2 || true
    exit 1
fi

[ "$rate" -ge 90 ] || { echo "selftest: kill rate below 90%" >&2; exit 1; }
echo "selftest: ok"
