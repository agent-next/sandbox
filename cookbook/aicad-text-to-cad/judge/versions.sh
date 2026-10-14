#!/usr/bin/env bash
# judge/versions.sh — print exactly what the judge environment provides.
# Written to judge/VERSIONS.txt by setup.sh; also runnable standalone.
# The venv location matches setup.sh (AICAD_JUDGE_VENV overrides).

set -euo pipefail

VENV="${AICAD_JUDGE_VENV:-$HOME/.venvs/aicad-judge}"
if [[ ! -x "$VENV/bin/python" ]]; then
    echo "judge venv not found at $VENV — run judge/setup.sh first" >&2
    exit 1
fi

"$VENV/bin/python" - <<'PY'
import importlib.metadata as md
import sys

print(f"python = {sys.version.split()[0]}")

# the tool under demo + the judge oracles, in install order
pkgs = [
    "cadgen",                # the text-to-cad tool (github.com/earthtojake/text-to-cad, MIT)
    "build123d",             # geometry engine the tool's model runtime drives
    "cadquery-ocp-novtk",    # OCP CAD kernel (STEP re-import, BRepCheck, volumes)
    "trimesh",               # STL watertight/winding/volume oracle
    "manifold3d",            # boolean XOR oracle
    "ezdxf",                 # DXF audit/entity oracle (cadgen dep; no DXF in these specs)
    "numpy",
    "shapely",
]
for name in pkgs:
    try:
        print(f"{name} = {md.version(name)}")
    except md.PackageNotFoundError:
        print(f"{name} = MISSING")

try:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder  # noqa: F401
    print("OCP = importable")
except Exception as exc:
    print(f"OCP = IMPORT FAILED: {exc}")
PY
