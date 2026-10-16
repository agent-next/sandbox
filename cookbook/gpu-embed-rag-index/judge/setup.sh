#!/bin/sh
# Install the pinned judge toolchain into $HOME/.venvs/gpu-embed-rag-index and
# the pinned model snapshot into $HOME/.cache/gpu-embed-rag-index (an offline
# huggingface-hub cache), so grading never touches the network.
#
# Everything is pinned and sha256-checked:
#   - python packages: judge/requirements.lock via pip --require-hashes
#     (fails non-zero on any checksum mismatch);
#   - model weights: sentence-transformers/all-MiniLM-L6-v2 at commit
#     1110a243fdf4706b3f48f1d95db1a4f5529b4d41, every file sha256-checked
#     against the MODEL_SHA256 manifest below (fails non-zero on mismatch).
#
# Idempotent: an existing venv that already provides the pinned versions and
# an existing verified snapshot are left untouched.

set -eu

VENV="$HOME/.venvs/gpu-embed-rag-index"
CACHE="$HOME/.cache/gpu-embed-rag-index"
HERE=$(cd "$(dirname "$0")" && pwd)

case "$(uname -s):$(uname -m)" in
    Linux:x86_64) ;;
    *) echo "setup.sh: unsupported platform $(uname -s) $(uname -m) \
(supported: x86-64 Linux, CPython 3.10-3.12)" >&2; exit 2 ;;
esac

# torch 2.3.1+cpu ships wheels for CPython 3.10-3.12 only (3.13 wheels start
# at torch 2.4); refuse other Pythons loudly instead of failing inside pip.
case "$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')" in
    3.10|3.11|3.12) ;;
    *) echo "setup.sh: unsupported Python \
$(python3 -c 'import sys; print(sys.version.split()[0])') (supported: 3.10-3.12; \
the pinned torch 2.3.1+cpu wheels cover cp310-cp312)" >&2
       exit 2 ;;
esac

# --- pinned python toolchain ---------------------------------------------
if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" - <<EOF
import sys
sys.path.insert(0, "$VENV/lib")
import importlib.util as u
def have(name, ver):
    spec = u.find_spec(name)
    if spec is None:
        return False
    mod = __import__(name)
    return getattr(mod, "__version__", "") == ver
sys.exit(0 if have("torch", "2.3.1+cpu")
           and have("sentence_transformers", "2.7.0")
           and have("faiss", "1.8.0") else 1)
EOF
then
    echo "setup.sh: venv already provides the pinned toolchain"
else
    echo "setup.sh: creating venv at $VENV"
    # An interrupted previous run may have left a half-built venv; start clean
    # so the pinned set is installed into a fresh environment or not at all.
    rm -rf "$VENV"
    python3 -m venv "$VENV"
    # --require-hashes: pip verifies every wheel against requirements.lock
    # and exits non-zero on any mismatch or install failure (set -e).
    # The extra index is passed as a flag, not written into the lock: an
    # option line inside a --require-hashes file makes pip ignore every
    # indented --hash that follows it.
    "$VENV/bin/pip" install --require-hashes \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r "$HERE/requirements.lock"
fi

# --- pinned model snapshot (offline huggingface-hub cache) ---------------
# Downloaded from the pinned commit with a pip-like User-Agent (the network
# path blocks default urllib agents); every file is sha256-verified.
MODEL_REPO="sentence-transformers/all-MiniLM-L6-v2"
MODEL_SHA="1110a243fdf4706b3f48f1d95db1a4f5529b4d41"

VENV="$VENV" CACHE="$CACHE" MODEL_REPO="$MODEL_REPO" MODEL_SHA="$MODEL_SHA" \
    python3 - <<'EOF'
import hashlib
import os
import sys
import urllib.request

repo = os.environ["MODEL_REPO"]
sha = os.environ["MODEL_SHA"]
cache = os.environ["CACHE"]
venv = os.environ["VENV"]

# name -> sha256 of every file the judge needs from the pinned snapshot
MANIFEST = {
    "1_Pooling/config.json":
        "4be450dde3b0273bb9787637cfbd28fe04a7ba6ab9d36ac48e92b11e350ffc23",
    "config.json":
        "953f9c0d463486b10a6871cc2fd59f223b2c70184f49815e7efbcab5d8908b41",
    "config_sentence_transformers.json":
        "061ca9d39661d6c6d6de5ba27f79a1cd5770ea247f8d46412a68a498dc5ac9f3",
    "model.safetensors":
        "53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db",
    "modules.json":
        "84e40c8e006c9b1d6c122e02cba9b02458120b5fb0c87b746c41e0207cf642cf",
    "sentence_bert_config.json":
        "fc1993fde0a95c24ec6c022539d41cf6e2f7c9721e5415d6fb6897472a9cd4b7",
    "special_tokens_map.json":
        "303df45a03609e4ead04bc3dc1536d0ab19b5358db685b6f3da123d05ec200e3",
    "tokenizer.json":
        "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037",
    "tokenizer_config.json":
        "acb92769e8195aabd29b7b2137a9e6d6e25c476a4f15aa4355c233426c61576b",
    "vocab.txt":
        "07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3",
}

snap = os.path.join(cache, "hub", "models--" + repo.replace("/", "--"),
                    "snapshots", sha)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verified():
    for name, want in MANIFEST.items():
        path = os.path.join(snap, name)
        if not os.path.exists(path) or sha256(path) != want:
            return False
    return True


if verified():
    print("setup.sh: model snapshot already present and verified")
    sys.exit(0)

os.makedirs(snap, exist_ok=True)
base = f"https://huggingface.co/{repo}/resolve/{sha}/"
for name, want in MANIFEST.items():
    path = os.path.join(snap, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # pip-like User-Agent: the network path blocks default urllib agents
    req = urllib.request.Request(base + name,
                                 headers={"User-Agent": "pip/25.0.1"})
    tmp = path + ".part"
    with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as out:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    got = sha256(tmp)
    if got != want:
        print(f"setup.sh: checksum mismatch for {name}: got {got}, "
              f"want {want}", file=sys.stderr)
        sys.exit(1)
    os.replace(tmp, path)

# refs/main -> pinned commit, so huggingface_hub resolves the snapshot
refs = os.path.join(cache, "hub", "models--" + repo.replace("/", "--"), "refs")
os.makedirs(refs, exist_ok=True)
with open(os.path.join(refs, "main"), "w") as fh:
    fh.write(sha + "\n")

if not verified():
    print("setup.sh: model snapshot failed verification after download",
          file=sys.stderr)
    sys.exit(1)
print(f"setup.sh: model snapshot downloaded and verified at {snap}")
EOF

# Record what was actually installed, for RECEIPT.md.
"$VENV/bin/pip" list --format=freeze > "$HERE/VERSIONS.txt"
printf '## judge venv: torch %s, sentence-transformers %s, faiss %s, \
python %s; model snapshot %s\n' \
    "$("$VENV/bin/python" -c 'import torch; print(torch.__version__)')" \
    "$("$VENV/bin/python" -c 'import sentence_transformers; print(sentence_transformers.__version__)')" \
    "$("$VENV/bin/python" -c 'import faiss; print(faiss.__version__)')" \
    "$("$VENV/bin/python" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')" \
    "$MODEL_SHA" > "$HERE/VERSIONS.head"
cat "$HERE/VERSIONS.head" "$HERE/VERSIONS.txt" > "$HERE/VERSIONS.tmp"
mv "$HERE/VERSIONS.tmp" "$HERE/VERSIONS.txt"
rm -f "$HERE/VERSIONS.head"

echo "setup.sh: ok"
