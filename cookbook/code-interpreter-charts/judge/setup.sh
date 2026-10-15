#!/usr/bin/env bash
# Install pinned tools for the code-interpreter-charts judge, idempotently.
#
# One stack, from sha256-pinned wheels (judge/requirements.txt):
#   * the judge engine needs Pillow, to decode the PNGs;
#   * the artifact under test needs pandas + matplotlib, headless.
# judge/oracle.py and judge/charts_judge.py are Python >= 3.11 standard
# library only apart from Pillow.  Re-running is a no-op when the pinned
# requirements are unchanged.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${CHART_VENV:-$HOME/.cache/code-interpreter-charts/venv}"
PY="$VENV/bin/python"
STAMP="$VENV/.requirements.sha256"

# The pinned wheels are manylinux x86_64 for CPython 3.11-3.13; pandas
# 3.0.6 ships no wheel below cp311 and numpy 2.5.3 none below cp312.
base_py="$(command -v python3)"
base_ver="$("$base_py" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
case "$base_ver" in
    3.11|3.12|3.13) ;;
    *)
        echo "setup: python3 is $base_ver; the pinned wheels cover CPython" \
             "3.11-3.13 (pandas 3.0.6 has no wheel below 3.11)" >&2
        exit 1
        ;;
esac

req_sha="$(sha256sum "$JDIR/requirements.txt" | awk '{print $1}')"
if [ -x "$PY" ] && [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$req_sha" ]; then
    echo "setup: venv at $VENV already matches requirements.txt (skipping)"
else
    echo "setup: creating venv at $VENV (python $base_ver)"
    rm -rf "$VENV"
    "$base_py" -m venv "$VENV"
    "$PY" -m pip install --quiet --upgrade "pip==25.0.1"
    echo "setup: installing pinned wheels (sha256-checked) from requirements.txt"
    "$PY" -m pip install --quiet --no-cache-dir --require-hashes \
        -r "$JDIR/requirements.txt"
    printf '%s' "$req_sha" > "$STAMP"
fi

# Import exactly the pinned versions, so a stale venv fails loudly here
# rather than as a confusing error inside the judge.
"$PY" - <<'EOF' || { echo "setup: pinned stack is not importable" >&2; exit 1; }
import pandas, matplotlib, numpy, PIL
got = (pandas.__version__, matplotlib.__version__, numpy.__version__,
       PIL.__version__)
want = ("3.0.6", "3.11.2", "2.5.3", "12.3.0")
assert got == want, f"installed {got} != pinned {want}"
EOF

# Record what was actually installed (SPEC.md: judge/VERSIONS.txt).
{
    echo "# code-interpreter-charts judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm))"
    echo "python3 $("$PY" --version | awk '{print $2}')"
    "$PY" -c 'import pandas,matplotlib,numpy,PIL
print("pandas", pandas.__version__)
print("matplotlib", matplotlib.__version__)
print("numpy", numpy.__version__)
print("pillow", PIL.__version__)'
    echo "pip $("$PY" -m pip --version | awk '{print $2}')"
    echo "requirements.txt sha256 $req_sha"
    echo "venv $VENV"
} > "$JDIR/VERSIONS.txt"

echo "setup: tool versions"
cat "$JDIR/VERSIONS.txt"
echo "setup: wrote $JDIR/VERSIONS.txt"
echo "setup: done"
