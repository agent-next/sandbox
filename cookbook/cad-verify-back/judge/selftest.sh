#!/usr/bin/env bash
# cookbook/cad-verify-back self-test: prove the judge can fail.
#
# 1. the known-good example must pass every gate
# 2. every scripted mutant must fail at least one gate
# 3. determinism: same seed -> identical verdict JSON (except timing)
# 4. prints the kill rate; exits non-zero if kill rate < 90 %
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
GOOD="${ROOT}/examples/good"
MUTDIR="$(mktemp -d)/mutants"
LOGDIR="$(mktemp -d)"
trap 'rm -rf "$LOGDIR" "$(dirname "$MUTDIR")"' EXIT

fail_banner() { echo "selftest: $*" >&2; }

# --- 0. the good example's delivered files must exist ------------------
# (they are gitignored; regenerate them from part.py if absent)
if [ ! -f "${GOOD}/part.step" ] || [ ! -f "${GOOD}/part.stl" ] || [ ! -f "${GOOD}/part.dxf" ]; then
    echo "selftest: good example exports missing; regenerating with part.py"
    ( cd "$GOOD" && python3 part.py ) >/dev/null
fi

# --- 1. known-good must pass -------------------------------------------
if ! bash "$HERE/grade.sh" "$GOOD" --json "$LOGDIR/good.json" >"$LOGDIR/good.log" 2>&1; then
    fail_banner "known-good example FAILED the judge:"
    cat "$LOGDIR/good.log" >&2
    exit 1
fi
echo "selftest: known-good PASS"

# --- 1b. artifact-controlled python must never run ---------------------
# An artifact dir containing a cadquery.py / ezdxf.py must not have them
# imported: grading is invoked from INSIDE the artifact dir so the
# exploit only fails if the judge runs python with a clean sys.path.
EVIL="$(dirname "$MUTDIR")/evil_artifact"
mkdir -p "$EVIL"
cp "${GOOD}"/part.step "${GOOD}"/part.stl "${GOOD}"/part.dxf "$EVIL"/
for mod in cadquery ezdxf trimesh; do
    cat > "${EVIL}/${mod}.py" <<'EOF'
import os
_marker = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "PWNED_" + os.path.splitext(os.path.basename(__file__))[0])
with open(_marker, "w") as _f:
    _f.write("artifact python ran during grading\n")
EOF
done
( cd "$EVIL" && bash "$HERE/grade.sh" . --json "$LOGDIR/evil.json" ) \
    >"$LOGDIR/evil.log" 2>&1 || {
        fail_banner "grading the evil-import artifact dir failed:"
        cat "$LOGDIR/evil.log" >&2
        exit 1
    }
if ls "$EVIL"/PWNED_* >/dev/null 2>&1; then
    fail_banner "artifact-controlled python executed during grading:"
    ls "$EVIL"/PWNED_* >&2
    exit 1
fi
echo "selftest: artifact cannot inject python (no PWNED_* markers written)"

# --- 2. every mutant must fail -----------------------------------------
python3 "$HERE/mutants.py" --list >/dev/null
PASSDIR="$(dirname "$MUTDIR")/passcases"
python3 "$HERE/mutants.py" "$GOOD" "$MUTDIR" "$PASSDIR" >/dev/null

nmut=0
killed=0
for m in "$MUTDIR"/*/; do
    name="$(basename "$m")"
    nmut=$((nmut + 1))
    if bash "$HERE/grade.sh" "$m" --json "$LOGDIR/${name}.json" >"$LOGDIR/${name}.log" 2>&1; then
        fail_banner "mutant ESCAPED: $name (judge passed on a bad artifact)"
        echo "--- ${name}.log ---" >&2
        python3 - "$LOGDIR/${name}.json" <<'EOF' >&2
import json, sys
v = json.load(open(sys.argv[1]))
print("verdict:", v.get("verdict"), v.get("reason", ""))
for k, g in v.get("gates", {}).items():
    if not g.get("pass"):
        print(f"  FAILED {k}: {g.get('error', '?')[:120]}")
EOF
        killed=$((killed + 0))
    else
        # list EVERY failing gate for this mutant (not just the first);
        # a kill only counts if at least one gate failed on its own
        # evidence (a verdict with only "skipped" gates is not a kill)
        first="$(python3 - "$LOGDIR/${name}.json" <<'EOF'
import json, sys
try:
    v = json.load(open(sys.argv[1]))
    fails = [(k, v["gates"][k].get("error", "?"))
             for k, g in v.get("gates", {}).items() if not g.get("pass")]
    named = [k for k, e in fails if not e.startswith("skipped:")]
    for k, e in fails:
        print(f"    FAILED {k}: {e[:110]}")
    if not named:
        print("NO_NAMED_GATE")
    else:
        print(f"KILLED_BY {', '.join(named)}")
except Exception as e:
    print(f"unreadable verdict: {e}")
    print("NO_NAMED_GATE")
EOF
)"
        if grep -q "NO_NAMED_GATE" <<<"$first"; then
            fail_banner "mutant $name produced a FAIL verdict but no named gate failed (only skipped gates)"
            exit 1
        fi
        gates="$(grep '^KILLED_BY' <<<"$first" | cut -d' ' -f2-)"
        echo "selftest: mutant KILLED: $name ($gates)"
        grep '^    FAILED' <<<"$first" || true
        killed=$((killed + 1))
    fi
done

# --- 2b. every pass-case must pass --------------------------------------
# near-miss artifacts that are inside tolerance (4-LINE rectangle, outline
# shifted 0.005 mm) must not be rejected: a judge that fails good parts is
# as broken as one that passes bad ones
for p in "$PASSDIR"/*/; do
    name="$(basename "$p")"
    if ! bash "$HERE/grade.sh" "$p" --json "$LOGDIR/${name}.json" \
            >"$LOGDIR/${name}.log" 2>&1; then
        fail_banner "pass-case REJECTED: $name (a correct artifact failed)"
        python3 - "$LOGDIR/${name}.json" <<'EOF' >&2
import json, sys
v = json.load(open(sys.argv[1]))
for k, g in v.get("gates", {}).items():
    if not g.get("pass"):
        print(f"  FAILED {k}: {g.get('error', '?')[:120]}")
EOF
        exit 1
    fi
    echo "selftest: pass-case PASS: $name"
done

rate=0
if [ "$nmut" -gt 0 ]; then
    rate=$(awk -v k="$killed" -v n="$nmut" 'BEGIN{printf "%.0f", 100*k/n}')
fi
echo "selftest: kill rate ${killed}/${nmut} (${rate}%)"

if [ "$nmut" -lt 5 ]; then
    fail_banner "need >= 5 known-bad examples; only $nmut present"
    exit 1
fi
if [ "$rate" -lt 90 ]; then
    fail_banner "kill rate ${rate}% < 90%"
    exit 1
fi

# --- 3. determinism: same seed -> identical verdict (except timing) ----
SEED=999999
bash "$HERE/grade.sh" "$GOOD" --seed "$SEED" --json "$LOGDIR/det1.json" >"$LOGDIR/det1.log" 2>&1
bash "$HERE/grade.sh" "$GOOD" --seed "$SEED" --json "$LOGDIR/det2.json" >"$LOGDIR/det2.log" 2>&1

python3 -c "
import json
with open('$LOGDIR/det1.json') as f:
    v1 = json.load(f)
with open('$LOGDIR/det2.json') as f:
    v2 = json.load(f)
v1.pop('timing', None)
v2.pop('timing', None)
if v1 != v2:
    import sys
    print('selftest: determinism FAILED: verdicts differ for same seed', file=sys.stderr)
    sys.exit(1)
print('selftest: determinism PASS (same seed -> identical verdict)')
" || exit 1

echo "selftest: PASS"
