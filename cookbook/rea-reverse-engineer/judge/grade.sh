#!/usr/bin/env bash
#
# grade.sh -- judge the reverse-engineering artifact.  Every gate compares
# the artifact against something outside itself: the real binaries, their
# unstripped symbol tables, REA's own Evidence format, and checksums of this
# judge directory.
#
#   grade.sh <artifact-dir> [--seed N] [--json out.json]
#
# Prints exactly one JSON verdict object.  Exit 0 only if all gates pass.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "${HERE}")"
GT_BUILD="${HERE}/ground_truth/build"
TARGETS_DIR="${DEMO}/targets"

ARTIFACT=""
SEED=20261014
JSON_OUT=""
COUNT=500

while [ $# -gt 0 ]; do
    case "$1" in
        --seed) SEED="$2"; shift 2 ;;
        --json) JSON_OUT="$2"; shift 2 ;;
        --count) COUNT="$2"; shift 2 ;;
        --) shift ;;
        -*) echo "grade: unknown flag $1" >&2; exit 2 ;;
        *) if [ -z "$ARTIFACT" ]; then ARTIFACT="$1"; shift; else echo "grade: extra arg $1" >&2; exit 2; fi ;;
    esac
done

if [ -z "$ARTIFACT" ]; then
    echo "usage: grade.sh <artifact-dir> [--seed N] [--json out.json]" >&2
    exit 2
fi
[ -d "$ARTIFACT" ] || { echo "grade: not a directory: $ARTIFACT" >&2; exit 2; }
ARTIFACT="$(cd "$ARTIFACT" && pwd)"
for t in checksum proto keycheck; do
    [ -x "${TARGETS_DIR}/${t}" ] || {
        echo "grade: ${TARGETS_DIR}/${t} missing; run judge/setup.sh first" >&2
        exit 3; }
done
[ -f "${GT_BUILD}/symbols.json" ] || {
    echo "grade: symbols.json missing; run judge/setup.sh first" >&2; exit 3; }

PY="${PYTHON:-python3}"

# ------------------------------------------------------- judge integrity ---
JUDGE_HASH_BEFORE="$( (cd "$HERE" && find . -type f ! -name '*.pyc' \
    ! -path './ground_truth/build/*' -print0 | sort -z \
    | xargs -0 sha256sum) 2>/dev/null | sha256sum | awk '{print $1}')"

WORK="$(mktemp -d /tmp/rea-grade.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

PASS=1
declare -a GATE_NAMES=() GATE_VERDICTS=() GATE_DETAILS=()
record() {
    GATE_NAMES+=("$1"); GATE_VERDICTS+=("$2"); GATE_DETAILS+=("$3")
    if [ "$2" != "pass" ]; then PASS=0; fi
}

TARGET_LIST="checksum proto keycheck"

# =====================================================================
# Gate: targets_present
# =====================================================================
MISSING=""
for t in $TARGET_LIST; do
    [ -d "${ARTIFACT}/${t}" ] || MISSING="${MISSING:+$MISSING,}${t}"
done
if [ -z "$MISSING" ]; then
    record "targets_present" "pass" "all three target dirs present"
else
    record "targets_present" "fail" "missing: ${MISSING}"
fi

for t in $TARGET_LIST; do
    TDIR="${ARTIFACT}/${t}"
    TBIN="${TARGETS_DIR}/${t}"
    TSHA="$(sha256sum "$TBIN" | awk '{print $1}')"

    if [ ! -d "$TDIR" ]; then
        record "rea_evidence_${t}"   "fail" "target dir missing"
        record "report_schema_${t}"  "fail" "target dir missing"
        record "reimpl_static_${t}"  "fail" "target dir missing"
        record "differential_${t}"   "fail" "target dir missing"
        record "core_addr_${t}"      "fail" "target dir missing"
        record "no_phantom_${t}"     "fail" "target dir missing"
        continue
    fi

    # --------------------------------------------------------------
    # Gate: rea_evidence_<t> -- real REA Evidence v2 files bound to
    # this binary's sha256, >= 2 files, one a binary_overview.
    # --------------------------------------------------------------
    EV_VERDICT="$("$PY" -I - "$TDIR/rea" "$TSHA" <<'PYEV'
import glob, json, os, sys
rea_dir, want_sha = sys.argv[1], sys.argv[2]
files = sorted(glob.glob(os.path.join(rea_dir, "*.json")))
if len(files) < 2:
    print("fail|fewer than 2 evidence files (%d)" % len(files)); sys.exit()
bad = []
overviews = 0
for f in files:
    try:
        d = json.load(open(f))
    except Exception:
        bad.append(os.path.basename(f) + ":unparseable"); continue
    if not isinstance(d, dict) or "schema_version" not in d:
        bad.append(os.path.basename(f) + ":no schema_version"); continue
    if not str(d.get("predicate_type", "")).startswith("rea."):
        bad.append(os.path.basename(f) + ":bad predicate_type"); continue
    sha = ((d.get("subject") or {}).get("digest") or {}).get("sha256")
    if sha != want_sha:
        bad.append(os.path.basename(f) + ":sha256 mismatch"); continue
    if d.get("operation") == "binary_overview":
        overviews += 1
if bad:
    print("fail|" + "; ".join(bad))
elif overviews < 1:
    print("fail|no binary_overview evidence")
else:
    print("pass|%d evidence files bound to binary sha256" % len(files))
PYEV
)"
    record "rea_evidence_${t}" "${EV_VERDICT%%|*}" "${EV_VERDICT#*|}"

    # --------------------------------------------------------------
    # Gate: report_schema_<t>
    # --------------------------------------------------------------
    RS_VERDICT="$("$PY" -I - "$TDIR/report.json" "$t" "$TSHA" <<'PYRS'
import json, sys
path, target, want_sha = sys.argv[1:4]
try:
    d = json.load(open(path))
except Exception as e:
    print("fail|report.json unparseable"); sys.exit()
if d.get("schema") != "rea-demo/report/1":
    print("fail|schema is not rea-demo/report/1"); sys.exit()
if d.get("target") != target:
    print("fail|target field is %r" % d.get("target")); sys.exit()
if d.get("sha256") != want_sha:
    print("fail|sha256 does not match binary"); sys.exit()
cf = d.get("core_function") or {}
try:
    int(str(cf.get("address", "")), 16)
except Exception:
    print("fail|core_function.address not hex"); sys.exit()
fns = d.get("functions")
if not isinstance(fns, list) or len(fns) < 1:
    print("fail|functions list missing or empty"); sys.exit()
for f in fns:
    try:
        int(str((f or {}).get("address", "")), 16)
    except Exception:
        print("fail|a functions[].address is not hex"); sys.exit()
if not str(d.get("algorithm") or "").strip():
    print("fail|algorithm text empty"); sys.exit()
print("pass|schema ok, %d functions claimed" % len(fns))
PYRS
)"
    record "report_schema_${t}" "${RS_VERDICT%%|*}" "${RS_VERDICT#*|}"

    # --------------------------------------------------------------
    # Gate: reimpl_static_<t> -- reimpl.py exists, is small, and does
    # not delegate to the binary or the OS.
    # --------------------------------------------------------------
    REIMPL="${TDIR}/reimpl.py"
    if [ ! -f "$REIMPL" ]; then
        record "reimpl_static_${t}" "fail" "reimpl.py missing"
    elif [ "$(wc -c < "$REIMPL")" -gt 65536 ]; then
        record "reimpl_static_${t}" "fail" "reimpl.py over 64 KiB"
    elif grep -Eq 'subprocess|os\.system|os\.popen|posix_spawn|ctypes|socket|targets/' "$REIMPL"; then
        record "reimpl_static_${t}" "fail" "reimpl.py delegates or reaches the OS"
    elif ! "$PY" -I -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$REIMPL" 2>/dev/null; then
        record "reimpl_static_${t}" "fail" "reimpl.py does not parse"
    else
        record "reimpl_static_${t}" "pass" "self-contained python"
    fi

    # --------------------------------------------------------------
    # Gate: differential_<t> -- 500 seeded inputs, byte-exact.
    # --------------------------------------------------------------
    if [ -f "$REIMPL" ]; then
        IN_DIR="${WORK}/in-${t}"
        "$PY" -I "${HERE}/gen_inputs.py" "$t" "$SEED" "$COUNT" "$IN_DIR"
        DIFF_OUT="$("$PY" -I "${HERE}/diff.py" "$TBIN" "$REIMPL" "$IN_DIR" "$COUNT" 2>&1)"
        if [ "${DIFF_OUT%% *}" = "OK" ]; then
            record "differential_${t}" "pass" "${COUNT} inputs byte-identical"
        else
            record "differential_${t}" "fail" "${DIFF_OUT:0:140}"
        fi
    else
        record "differential_${t}" "fail" "no reimpl.py"
    fi

    # --------------------------------------------------------------
    # Gates: core_addr_<t>, no_phantom_<t> -- addresses vs the real
    # symbol table of the identical unstripped build.  An address
    # counts in ELF space or Ghidra space (+0x100000).
    # --------------------------------------------------------------
    ADDR_VERDICT="$("$PY" -I - "$TDIR/report.json" "${GT_BUILD}/symbols.json" "$t" <<'PYAD'
import json, sys
report_path, sym_path, target = sys.argv[1:4]
try:
    report = json.load(open(report_path))
    syms = json.load(open(sym_path))[target]
except Exception:
    print("fail|unparseable report or symbols"); sys.exit()
ranges = [(s["start"], s["end"]) for s in syms if s["end"] > s["start"]]
core = target == "checksum" and "checksum_update" \
    or target == "proto" and "proto_parse" \
    or "key_verify"
core_ranges = [(s["start"], s["end"]) for s in syms
               if s["name"] == core or s["name"].startswith(core + ".")]
if not core_ranges:
    print("fail|core symbol %s absent from symbol table" % core); sys.exit()

def inside(a, rs):
    return any(s <= a < e or s <= a - 0x100000 < e for s, e in rs)

def hx(x):
    try: return int(str(x), 16)
    except Exception: return None

ca = hx((report.get("core_function") or {}).get("address"))
phantoms = [str(f.get("address")) for f in report.get("functions", [])
            if (lambda a: a is None or not inside(a, ranges))(hx((f or {}).get("address")))]
core_ok = ca is not None and inside(ca, core_ranges)
print("core=%s phantoms=%s" % ("ok" if core_ok else "bad",
      ",".join(phantoms) if phantoms else "none"))
PYAD
)"
    CA="$(printf '%s' "$ADDR_VERDICT" | sed -n 's/.*core=\([a-z]*\).*/\1/p')"
    PH="$(printf '%s' "$ADDR_VERDICT" | sed -n 's/.*phantoms=\(.*\)/\1/p')"
    if [ "$CA" = "ok" ]; then
        record "core_addr_${t}" "pass" "core_function.address inside ${t}'s core routine"
    elif [ "$CA" = "bad" ]; then
        record "core_addr_${t}" "fail" "core_function.address outside the core routine's range"
    else
        record "core_addr_${t}" "fail" "$ADDR_VERDICT"
    fi
    if [ "$PH" = "none" ]; then
        record "no_phantom_${t}" "pass" "all claimed addresses inside real functions"
    elif [ -n "$PH" ]; then
        record "no_phantom_${t}" "fail" "phantom addresses: ${PH:0:120}"
    else
        record "no_phantom_${t}" "fail" "$ADDR_VERDICT"
    fi
done

# =====================================================================
# Gate: key_accepted -- the binary alone judges the candidate key.
# =====================================================================
KEYFILE="${ARTIFACT}/keycheck/key.txt"
if [ -f "$KEYFILE" ]; then
    KEY_OUT="$("${TARGETS_DIR}/keycheck" < "$KEYFILE" 2>&1)"
    KEY_RC=$?
    if [ "$KEY_RC" -eq 0 ] && [ "$KEY_OUT" = "OK" ]; then
        record "key_accepted" "pass" "keycheck accepted key.txt"
    else
        record "key_accepted" "fail" "keycheck rc=${KEY_RC} out=${KEY_OUT:0:40}"
    fi
else
    record "key_accepted" "fail" "key.txt missing"
fi

# =====================================================================
# Gate: judge_intact
# =====================================================================
JUDGE_HASH_AFTER="$( (cd "$HERE" && find . -type f ! -name '*.pyc' \
    ! -path './ground_truth/build/*' -print0 | sort -z \
    | xargs -0 sha256sum) 2>/dev/null | sha256sum | awk '{print $1}')"
if [ "$JUDGE_HASH_BEFORE" = "$JUDGE_HASH_AFTER" ]; then
    record "judge_intact" "pass" "judge checksum unchanged"
else
    record "judge_intact" "fail" "judge/ was modified during the run"
fi

# ------------------------------------------------------------------ emit ---
GATE_FILE="$WORK/gates.tsv"
: > "$GATE_FILE"
i=0
while [ "$i" -lt "${#GATE_NAMES[@]}" ]; do
    printf '%s\t%s\t%s\n' "${GATE_NAMES[$i]}" "${GATE_VERDICTS[$i]}" \
        "${GATE_DETAILS[$i]}" >> "$GATE_FILE"
    i=$((i + 1))
done

echo
echo "verdict: $([ "$PASS" = 1 ] && echo PASS || echo FAIL)"
while IFS=$'\t' read -r g v d; do
    printf '  %-26s %-4s  %s\n' "$g" "$v" "$d"
done < "$GATE_FILE"

"$PY" -I - "$PASS" "$ARTIFACT" "$SEED" "$COUNT" "$JSON_OUT" "$GATE_FILE" "$SECONDS" <<'PYEMIT'
import datetime, json, sys
pass_all = sys.argv[1] == "1"
artifact, seed, count, json_out, gate_file, elapsed = sys.argv[2:8]
gates = {}
for raw in open(gate_file):
    name, verdict, detail = raw.rstrip("\n").split("\t", 2)
    gates[name] = {"verdict": verdict, "detail": detail}
verdict = {
    "schema": "rea-reverse-engineer/grade/1",
    "artifact": artifact,
    "seed": int(seed),
    "inputs_per_target": int(count),
    "pass": pass_all,
    "gates_passed": sum(1 for g in gates.values() if g["verdict"] == "pass"),
    "gates_total": len(gates),
    "gates": gates,
    "timing": {
        "generated_at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
        "elapsed_s": int(elapsed),
    },
}
text = json.dumps(verdict, indent=2, sort_keys=True)
print(text)
if json_out:
    with open(json_out, "w") as fh:
        fh.write(text + "\n")
PYEMIT

[ "$PASS" = 1 ] && exit 0
exit 1
