#!/usr/bin/env bash
#
# grade.sh -- judge the firmware artifact.  Every gate compares the artifact
# against something outside itself: the toolchain, the emulator, Python's
# zlib, and checksums of this judge directory.
#
#   grade.sh <artifact-dir> [--seed N] [--json out.json]
#
# Prints exactly one JSON verdict object.  Exit 0 only if all gates pass.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "${HERE}")"

ARTIFACT=""
SEED=20260814
JSON_OUT=""

while [ $# -gt 0 ]; do
    case "$1" in
        --seed) SEED="$2"; shift 2 ;;
        --json) JSON_OUT="$2"; shift 2 ;;
        --) shift ;;
        -*) echo "grade: unknown flag $1" >&2; exit 2 ;;
        *) if [ -z "$ARTIFACT" ]; then ARTIFACT="$1"; shift; else echo "grade: extra arg $1" >&2; exit 2; fi ;;
    esac
done

if [ -z "$ARTIFACT" ]; then
    echo "usage: grade.sh <artifact-dir> [--seed N] [--json out.json]" >&2
    exit 2
fi
if [ ! -d "$ARTIFACT" ]; then
    echo "grade: not a directory: $ARTIFACT" >&2
    exit 2
fi
ARTIFACT="$(cd "$ARTIFACT" && pwd)"

# ----------------------------------------------------------------- tools ---
TC_DIR="${HOME}/.firmware-qemu-tools/arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi"
if [ ! -x "${TC_DIR}/bin/arm-none-eabi-gcc" ]; then
    # fall back to anything on PATH, so the judge still runs on a host
    # where the toolchain was installed elsewhere
    if command -v arm-none-eabi-gcc >/dev/null 2>&1; then
        TC_DIR=""
    else
        echo "grade: arm-none-eabi-gcc not found; run judge/setup.sh first" >&2
        exit 3
    fi
fi
tool() {
    if [ -n "$TC_DIR" ]; then
        echo "${TC_DIR}/bin/arm-none-eabi-$1"
    else
        echo "arm-none-eabi-$1"
    fi
}
CC="$(tool gcc)"; READELF="$(tool readelf)"; SIZE="$(tool size)"

QEMU="${QEMU_BIN:-qemu-system-arm}"
MACHINE="${MACHINE:-lm3s6965evb}"
BOOT_S="${BOOT_S:-10}"
SHELL_S="${SHELL_S:-30}"

# ------------------------------------------------------- judge integrity ---
# Checksum the judge before anything is built, so an artifact cannot edit
# the rules it is being graded by.
JUDGE_HASH_BEFORE="$( (cd "$HERE" && find . -type f ! -name '*.pyc' -print0 \
    | sort -z | xargs -0 sha256sum) 2>/dev/null | sha256sum | awk '{print $1}')"

WORK="$(mktemp -d /tmp/fq-grade.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

# Python is the independent oracle: zlib.crc32 and the RNG.
PY="${PYTHON:-python3}"

PASS=1
declare -a GATE_NAMES=() GATE_VERDICTS=() GATE_DETAILS=()
record() {
    GATE_NAMES+=("$1"); GATE_VERDICTS+=("$2"); GATE_DETAILS+=("$3")
    if [ "$2" != "pass" ]; then PASS=0; fi
}

# =====================================================================
# Gate 1: build_clean -- -Wall -Werror must exit 0 and print nothing.
# =====================================================================
BUILD_DIR="$WORK/art"
mkdir -p "$BUILD_DIR"
cp -a "$ARTIFACT"/. "$BUILD_DIR"/

( cd "$BUILD_DIR" && make clean >/dev/null 2>&1 )
BUILD_LOG="$WORK/build.log"
# The artifact Makefile builds $(CROSS)gcc, so the prefix ends in arm-none-eabi-.
if [ -n "$TC_DIR" ]; then
    TC_PREFIX="${TC_DIR}/bin/arm-none-eabi-"
else
    TC_PREFIX="arm-none-eabi-"
fi
( cd "$BUILD_DIR" && make CROSS="${TC_PREFIX}" build/firmware.elf ) \
    > "$BUILD_LOG" 2>&1
BUILD_RC=$?
if [ "$BUILD_RC" -ne 0 ]; then
    tail -20 "$BUILD_LOG" >&2
fi

if [ $BUILD_RC -ne 0 ]; then
    record "build_clean" "fail" "make exited $BUILD_RC"
else
    # Real diagnostics are "file:line:col: warning|error: ...".  Match that
    # shape, not the flag names echoed in the command line.
    WARN="$(grep -Ec ':[0-9]+:[0-9]+: (warning|error|fatal error):' "$BUILD_LOG" || true)"
    if [ "${WARN:-0}" -gt 0 ]; then
        record "build_clean" "fail" "compiler emitted ${WARN} diagnostic line(s)"
    else
        record "build_clean" "pass" "no diagnostics"
    fi
fi

ELF="$BUILD_DIR/build/firmware.elf"
TEXT_BYTES=0
if [ ! -f "$ELF" ]; then
    record "elf_ok" "fail" "build/firmware.elf missing"
    record "maps_ok" "fail" "no ELF to size"
    # Without an ELF the runtime gates cannot run, but must still be reported.
    record "boot" "fail" "no ELF"
    record "shell" "fail" "no ELF"
    record "crc_oracle" "fail" "no ELF"
    record "no_hardfault" "fail" "no ELF"
    record "judge_intact" "fail" "skipped"
    emit() { :; }
else
# =====================================================================
# Gate 2: elf_ok -- a real Cortex-M3 executable ELF.
# =====================================================================
ELFINFO="$WORK/elfinfo"
"$READELF" -h "$ELF" > "$WORK/elf.hdr" 2>&1
"$READELF" -S "$ELF" > "$WORK/elf.sec" 2>&1
# readelf output is easy to mis-split in awk; let python parse it once.
# Emits: e_type e_machine entry_dec text_addr text_size text_rodata_bytes
"$PY" -I - "$WORK/elf.hdr" "$WORK/elf.sec" > "$ELFINFO" <<'PYINFO'
import re, sys
hdr = open(sys.argv[1], errors="replace").read()
sec = open(sys.argv[2], errors="replace").read()

def hdr_field(name):
    m = re.search(r"^\s*%s\s*:?\s*(.+)$" % re.escape(name), hdr, re.M)
    return m.group(1).strip() if m else ""

etype = hdr_field("Type:").split("(")[0].strip()
emach = hdr_field("Machine:")
entry = hdr_field("Entry point address")

# readelf -S columns: Nr Name Type Address Off Size ES Flg Lk Inf Al
m = re.search(r"\[\s*\d+\]\s+\.text\s+\S+\s+(\S+)\s+(\S+)\s+(\S+)", sec)
if m:
    text_addr, text_size = m.group(1), m.group(3)
else:
    text_addr, text_size = "0", "0"


def drop_prefix(value):
    """`0x205` -> `205`.  The caller needs base-10, and bash arithmetic would
    read `0008b0` as octal (`b` is invalid) rather than hex, so do the
    conversion here where it is unambiguous."""
    return value[2:] if value[:2] == "0x" else value or "0"


def to_dec(value):
    return str(int(drop_prefix(value), 16))


print(etype, emach, to_dec(entry), to_dec(text_addr), to_dec(text_size))
PYINFO
read -r ETYPE EMACH ENTRY_DEC TEXT_ADDR TEXT_SIZE < "$ELFINFO"

if [ "$EMACH" != "ARM" ]; then
    record "elf_ok" "fail" "e_machine=${EMACH} (want ARM)"
elif [ "$ETYPE" != "EXEC" ]; then
    record "elf_ok" "fail" "e_type=${ETYPE} (want EXEC)"
elif [ "$ENTRY_DEC" -lt "$TEXT_ADDR" ] || [ "$ENTRY_DEC" -ge $((TEXT_ADDR + TEXT_SIZE)) ]; then
    record "elf_ok" "fail" "entry 0x$(printf %x "$ENTRY_DEC") outside .text [0x$(printf %x "$TEXT_ADDR"),+$(printf %d "$TEXT_SIZE")]"
else
    record "elf_ok" "pass" "entry 0x$(printf %x "$ENTRY_DEC") is inside .text"
fi

# =====================================================================
# Gate 3: maps_ok -- the firmware must stay small.
# =====================================================================
"$SIZE" -A "$ELF" > "$WORK/elf.size" 2>&1
TEXT_BYTES="$(awk '$1==".text"{s+=$2} $1==".rodata"{s+=$2} END{print s+0}' "$WORK/elf.size")"
LIMIT_BYTES=8192
if [ "$TEXT_BYTES" -gt "$LIMIT_BYTES" ]; then
    record "maps_ok" "fail" ".text+.rodata=${TEXT_BYTES}B > ${LIMIT_BYTES}B"
else
    record "maps_ok" "pass" ".text+.rodata=${TEXT_BYTES}B <= ${LIMIT_BYTES}B"
fi

# =====================================================================
# Runtime session: one QEMU run, driven by a script, watched by Python.
#
# The session script (written below) prints each response on its own line
# prefixed with "CMD:", so the transcript and the expected mask line up.
# =====================================================================
RESULT_FILE="$WORK/result.json"
QEMU_OUT="$WORK/drive.out"

"$PY" -I "$HERE/drive.py" "$HERE/spec.json" "$ELF" "$MACHINE" \
    "$BOOT_S" "$SHELL_S" "$SEED" > "$QEMU_OUT" 2>"$WORK/drive.err"
SESSION_RC=$?

RESULT_LINE="$(grep -a '@@@RESULT@@@' "$QEMU_OUT" | tail -1 | sed 's/.*@@@RESULT@@@//')"
if [ -n "$RESULT_LINE" ]; then
    printf '%s' "$RESULT_LINE" > "$RESULT_FILE"
else
    echo '{"error":"session produced no verdict"}' > "$RESULT_FILE"
    [ "$SESSION_RC" -ne 0 ] && tail -5 "$WORK/drive.err" >&2
fi

# Pull the session verdict out of the JSON in one place, so the gate wording
# below never has to re-derive it.
read -r BOOT_OK SAW_FAULT SHELL_TOTAL SHELL_FAILED SHELL_OK CRC_TOTAL CRC_FAILED CRC_OK \
    < <("$PY" -I - "$RESULT_FILE" <<'PYPARSE'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    d = {}
print(" ".join(str(x) for x in [
    "true" if d.get("boot_ok") else "false",
    "true" if d.get("saw_fault") else "false",
    d.get("shell_total", 0), d.get("shell_failed", 0),
    "true" if d.get("shell_ok") else "false",
    d.get("crc_total", 0), d.get("crc_failed", 0),
    "true" if d.get("crc_ok") else "false",
]))
PYPARSE
)

# =====================================================================
# Gates 4-7, from the session verdict.
# =====================================================================
if [ "$BOOT_OK" = "true" ]; then
    record "boot" "pass" "banner within ${BOOT_S}s"
else
    record "boot" "fail" "no banner within ${BOOT_S}s"
fi

if [ "$SHELL_OK" = "true" ]; then
    record "shell" "pass" "${SHELL_TOTAL}/${SHELL_TOTAL} exact responses"
else
    record "shell" "fail" "${SHELL_FAILED} of ${SHELL_TOTAL} responses wrong"
fi

if [ "$CRC_OK" = "true" ]; then
    record "crc_oracle" "pass" "${CRC_TOTAL}/${CRC_TOTAL} match zlib.crc32"
else
    record "crc_oracle" "fail" "CRC disagrees with zlib"
fi

if [ "$SAW_FAULT" = "false" ]; then
    record "no_hardfault" "pass" "no fault strings in UART output"
else
    record "no_hardfault" "fail" "fault string seen on UART"
fi

# =====================================================================
# Gate 8: the judge was not modified by the artifact.
# =====================================================================
JUDGE_HASH_AFTER="$( (cd "$HERE" && find . -type f ! -name '*.pyc' -print0 \
    | sort -z | xargs -0 sha256sum) 2>/dev/null | sha256sum | awk '{print $1}')"
if [ "$JUDGE_HASH_BEFORE" = "$JUDGE_HASH_AFTER" ]; then
    record "judge_intact" "pass" "judge checksum unchanged"
else
    record "judge_intact" "fail" "judge/ was modified during the run"
fi

fi   # end of the "ELF exists" branch

# ------------------------------------------------------------------ emit ---
# Collect the gates into one JSON verdict.  The gate list is passed through a
# file, so no word in a detail string can shift an argument.
GATE_FILE="$WORK/gates.tsv"
: > "$GATE_FILE"
i=0
while [ "$i" -lt "${#GATE_NAMES[@]}" ]; do
    printf '%s\t%s\t%s\n' \
        "${GATE_NAMES[$i]}" "${GATE_VERDICTS[$i]}" "${GATE_DETAILS[$i]}" >> "$GATE_FILE"
    i=$((i + 1))
done

# A short human summary first, then the verdict JSON itself.
echo
echo "verdict: $([ "$PASS" = 1 ] && echo PASS || echo FAIL) " \
     "(${PASS:+x}$([ "$PASS" = 1 ] && echo 1 || echo 0)) gates:"
while IFS=$'\t' read -r g v d; do
    printf '  %-14s %-4s  %s\n' "$g" "$v" "$d"
done < "$GATE_FILE"

"$PY" -I - "$PASS" "$ARTIFACT" "$SEED" "$JSON_OUT" "$GATE_FILE" "$SECONDS" <<'PYEMIT'
import datetime, json, sys

pass_all = sys.argv[1] == "1"
artifact, seed, json_out, gate_file, elapsed_s = sys.argv[2:7]

gates = {}
with open(gate_file) as fh:
    for raw in fh:
        name, verdict, detail = raw.rstrip("\n").split("\t", 2)
        gates[name] = {"verdict": verdict, "detail": detail}

verdict = {
    "schema": "firmware-qemu/grade/1",
    "artifact": artifact,
    "seed": int(seed),
    "pass": pass_all,
    "gates_passed": sum(1 for g in gates.values() if g["verdict"] == "pass"),
    "gates_total": len(gates),
    "gates": gates,
    # Everything non-deterministic lives under `timing`: selftest.sh
    # proves two same-seed runs are byte-identical apart from this key.
    "timing": {
        "generated_at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
        "elapsed_s": int(elapsed_s),
    },
}
text = json.dumps(verdict, indent=2, sort_keys=True)
print(text)
if json_out:
    with open(json_out, "w") as fh:
        fh.write(text + "\n")
        fh.flush()
PYEMIT

[ "$PASS" = 1 ] && exit 0
exit 1
