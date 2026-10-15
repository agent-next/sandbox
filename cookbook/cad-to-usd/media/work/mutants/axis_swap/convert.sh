#!/usr/bin/env bash
# convert.sh — the conversion artifact for cad-to-usd.
#
# Contract (SPEC.md): run from a working directory that contains
# sources/ with the three pinned RC-Car-CAD files (original file names,
# commit 407bd553ee57668ceb58d81ffd7f4d617dee3dfa); the converter
# binary is in $USD_CONVERT_CAD (set by the judge) or on PATH. Writes
# the three <key>.usda files into the current directory and exits 0
# only if every conversion succeeded.
#
# Tool pin: usd-convert-cad 0.3.0 (pip wheel, see judge/setup.sh).
# Chosen flags:
#   --up-axis z              required scene up-axis (the sources are
#                            Z-up CAD assemblies; stated explicitly so
#                            the output never depends on file defaults)
#   --tess-lod 2             tessellation density: keeps each .usda well
#                            under 1 MB while staying inside the judge
#                            tolerances (bbox 1%/0.1 mm, area 3%)
#   --instancing-style none  every mesh a plain prim, so any USD reader
#                            sees the full geometry without prototype
#                            resolution

set -euo pipefail

CONV="${USD_CONVERT_CAD:-usd-convert-cad}"

convert_one() {  # convert_one <source-path> <key>
    local src="$1" key="$2"
    echo "[convert] $src -> $key.usda"
    "$CONV" -i "$src" -o "$key.usda" \
        --up-axis z --tess-lod 2 --instancing-style none >/dev/null 2>&1
    [[ -s "$key.usda" ]] || { echo "[convert] ERROR: $key.usda missing/empty" >&2; exit 1; }
}

convert_one "sources/Servo Futaba S3003 v6.step"       "Servo_Futaba_S3003_v6_step"
convert_one "sources/Servo Futaba S3003 v6.iges"       "Servo_Futaba_S3003_v6_iges"
convert_one "sources/ShockTowerFront/_ShockTowerFront.stp" "ShockTowerFront_stp"

echo "[convert] all three parts converted"
