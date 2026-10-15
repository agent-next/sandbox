#!/usr/bin/env bash
# multi-lang-runner: driver that builds and runs every solution on every
# case in <case_dir>, writing stdout to <case_dir>/../out/<lang>_<prob>.txt.
#
# Usage: bash run_all.sh <case_dir>
# Exit 0 iff every program ran; output files are the caller's to inspect.
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "usage: bash run_all.sh <case_dir>" >&2
    exit 2
fi

CASE_DIR="$(cd "$1" && pwd)"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${ROOT}/solutions"
OUT_DIR="${CASE_DIR}/../out"
BUILD="$(mktemp -d)"
trap 'rm -rf "${BUILD}"' EXIT

mkdir -p "${OUT_DIR}"

run_prog() {
    # run_prog <lang> <prob> : compile if needed, then run over cases.
    local lang="$1" prob="$2"
    local run
    case "${lang}" in
        go)   go build -o "${BUILD}/${lang}_${prob}" "${SRC}/go/${prob}.go" && run="${BUILD}/${lang}_${prob}" ;;
        rust) rustc -O -o "${BUILD}/${lang}_${prob}" "${SRC}/rust/${prob}.rs" && run="${BUILD}/${lang}_${prob}" ;;
        c)    gcc -O2 -o "${BUILD}/${lang}_${prob}" "${SRC}/c/${prob}.c" -lm && run="${BUILD}/${lang}_${prob}" ;;
        python) run="python3 ${SRC}/python/${prob}.py" ;;
        node)   run="node ${SRC}/node/${prob}.js" ;;
        bash)   run="bash ${SRC}/bash/${prob}.sh" ;;
        *) echo "run_all: unknown language ${lang}" >&2; return 2 ;;
    esac
    local cf
    for cf in "${CASE_DIR}"/${prob}_*.in; do
        ${run} < "${cf}" > "${OUT_DIR}/${lang}_${prob}.txt"
    done
}

for prob in sumsq rle primes; do
    for lang in python node go rust bash c; do
        run_prog "${lang}" "${prob}"
    done
done

echo "run_all: wrote 18 output files to ${OUT_DIR}"
