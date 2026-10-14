#!/usr/bin/env bash
# Idempotent setup for the rf-openems demo judge.
# Installs micromamba + a pinned conda-forge env (pymeep 1.31.0) into $HOME/.rf-openems.
# All downloads are sha256-checked. No root required.

set -euo pipefail

ENV_DIR="${ENV_DIR:-$HOME/.rf-openems/env}"
MM_BIN="$HOME/.rf-openems/micromamba"
MICROMAMBA_VERSION="2.3.2"
MICROMAMBA_SHA256="5512233cdd8564a671626081026dc861537a963baa06706baab08fac6f3bb9d2"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$HOME/.rf-openems"

# 1. micromamba (sha256-checked) --------------------------------------------
if [ ! -x "$MM_BIN" ]; then
    tmp="$HOME/.rf-openems/mm.tar.bz2"
    curl -sfLo "$tmp" "https://micro.mamba.pm/api/micromamba/linux-64/${MICROMAMBA_VERSION}"
    echo "${MICROMAMBA_SHA256}  $tmp" | sha256sum -c -
    mkdir -p "$HOME/.rf-openems/mm-extract"
    tar -xjf "$tmp" -C "$HOME/.rf-openems/mm-extract" bin/micromamba
    mv "$HOME/.rf-openems/mm-extract/bin/micromamba" "$MM_BIN"
    rm -rf "$tmp" "$HOME/.rf-openems/mm-extract"
    chmod +x "$MM_BIN"
fi

# 2. pinned environment ------------------------------------------------------
export MAMBA_ROOT_PREFIX="$HOME/.rf-openems/pkgs"
if [ ! -x "$ENV_DIR/bin/python" ]; then
    "$MM_BIN" create -y -p "$ENV_DIR" -f "$HERE/environment.yml" --no-rc
fi

# 3. record + smoke test -----------------------------------------------------
"$MM_BIN" run -p "$ENV_DIR" python -I - <<'EOF'
import hashlib, json, subprocess, sys
import numpy, meep
info = {
    "python": sys.version.split()[0],
    "numpy": numpy.__version__,
    "meep": meep.__version__,
}
print("SETUP OK", json.dumps(info))
EOF

# 4. record locked package versions/sha256s (conda records the tarball hashes)
"$MM_BIN" list -p "$ENV_DIR" --json > "$HOME/.rf-openems/env-package-lock.json"
echo "setup.sh: environment ready at $ENV_DIR"
