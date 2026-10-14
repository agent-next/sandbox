#!/usr/bin/env bash
#
# collect_data.sh -- regenerate media/data/ from the judge.
#
# Everything the figures plot is produced here by a real run:
#   - verdict-*.json      grade.sh --seed 20260814 --json on examples/good
#                         and on each mutants.py artifact
#   - uart-*.json         the real wire transcript, captured with the
#                         judge's own drive.py machinery (media/capture.py)
#   - size-good.txt       arm-none-eabi-size -A on the real ELF
#   - firmware-good.map   the linker map the real build wrote
#   - selftest.log        judge/selftest.sh output
#
# Needs judge/setup.sh to have run.  Takes ~15 minutes (14 mutant
# sessions with real boot/shell timeouts).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "${HERE}")"
DATA="${HERE}/data"
SEED=20260814

TC_DIR="${HOME}/.firmware-qemu-tools/arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi"
if [ ! -x "${TC_DIR}/bin/arm-none-eabi-gcc" ] \
    && ! command -v arm-none-eabi-gcc >/dev/null 2>&1; then
    echo "collect_data: arm-none-eabi-gcc missing; run judge/setup.sh" >&2
    exit 3
fi
if [ -x "${TC_DIR}/bin/arm-none-eabi-gcc" ]; then
    CROSS="${TC_DIR}/bin/arm-none-eabi-"
else
    CROSS="arm-none-eabi-"
fi
command -v qemu-system-arm >/dev/null 2>&1 || {
    echo "collect_data: qemu-system-arm missing; run judge/setup.sh" >&2
    exit 3; }

mkdir -p "${DATA}"
MUT="$(mktemp -d /tmp/fq-media-mut.XXXXXX)"
trap 'rm -rf "${MUT}"' EXIT

echo "== grade examples/good"
bash "${DEMO}/judge/grade.sh" "${DEMO}/examples/good" \
    --seed "${SEED}" --json "${DATA}/verdict-good.json"

echo "== generate + grade mutants"
python3 "${DEMO}/judge/mutants.py" make-all "${MUT}" > /dev/null
for m in "${MUT}"/*/; do
    name="$(basename "${m}")"
    echo "   grade ${name}"
    bash "${DEMO}/judge/grade.sh" "${MUT}/${name}" \
        --seed "${SEED}" --json "${DATA}/verdict-${name}.json" || true
done

echo "== selftest"
bash "${DEMO}/judge/selftest.sh" > "${DATA}/selftest.log" 2>&1

echo "== real ELF + size/map evidence"
make -C "${DEMO}/examples/good" CROSS="${CROSS}" build/firmware.elf
"${CROSS}size" -A "${DEMO}/examples/good/build/firmware.elf" \
    > "${DATA}/size-good.txt"
cp "${DEMO}/examples/good/build/firmware.map" "${DATA}/firmware-good.map"

echo "== UART transcripts"
python3 "${HERE}/capture.py" \
    "${DEMO}/examples/good/build/firmware.elf" \
    "${DATA}/uart-good.json" --seed "${SEED}"
make -C "${MUT}/crc-poly" CROSS="${CROSS}" build/firmware.elf
python3 "${HERE}/capture.py" \
    "${MUT}/crc-poly/build/firmware.elf" \
    "${DATA}/uart-crc-poly.json" --seed "${SEED}" || true

echo "collect_data: done -> ${DATA}"
