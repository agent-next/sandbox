#!/usr/bin/env bash
# Install pinned tools for the llm-eval-harness judge, idempotently.
# The judge is Python >= 3.10 stdlib only (no packages to install); setup
# verifies the interpreter and the sha256 of the pinned dataset, then
# writes judge/VERSIONS.txt.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$JDIR/.." && pwd)"

# --- 1. Python >= 3.10 ---------------------------------------------------
python3 - <<'EOF' || { echo "setup: python3 >= 3.10 required" >&2; exit 1; }
import sys
assert sys.version_info >= (3, 10), sys.version
EOF
echo "setup: $(python3 --version)"

# --- 2. pinned dataset sha256 --------------------------------------------
PINNED="$DEMO/judge/dataset-sha256.txt"
DATA="$DEMO/data/mbpp_subset.jsonl"
expected="$(awk '{print $1}' "$PINNED")"
echo "setup: checking sha256 of $DATA"
echo "$expected  $DATA" | sha256sum -c - || {
    echo "setup: sha256 mismatch on $DATA" >&2
    exit 1
}

# --- 3. reference solutions pass their own tests (provenance check) ------
echo "setup: verifying the pinned dataset's reference solutions"
python3 -I - "$DATA" <<'EOF' || { echo "setup: dataset reference solutions failed" >&2; exit 1; }
import json, subprocess, sys, tempfile
from pathlib import Path

data = Path(sys.argv[1])
ok = 0
with data.open() as fh:
    for line in fh:
        row = json.loads(line)
        body = row["test_setup_code"] + "\n" + row["code"] + "\n" + \
            "\n".join(row["test_list"])
        with tempfile.TemporaryDirectory(prefix="setup-check-") as td:
            p = Path(td) / "probe.py"
            p.write_text(body)
            proc = subprocess.run([sys.executable, "-I", str(p)], cwd=td,
                                  capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, \
            f"task {row['task_id']}: {proc.stderr.strip()[-400:]}"
        ok += 1
print(f"setup: {ok} tasks verified")
EOF

# --- 4. what got installed ------------------------------------------------
{
    echo "# llm-eval-harness judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm))"
    echo "python3 $(python3 --version | awk '{print $2}')"
    echo "dataset $DATA sha256 $expected"
} > "$JDIR/VERSIONS.txt"
echo "setup: wrote $JDIR/VERSIONS.txt"
echo "setup: done"
