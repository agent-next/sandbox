#!/usr/bin/env bash
# cookbook/layerfs-race: install the pinned toolchain idempotently into
# $HOME/layerfs-race. Rules (cookbook/DEMO-STANDARD.md): exact versions,
# sha/commit-verified downloads, no "latest", nothing published in the last
# two weeks. What was installed is recorded in $PREFIX/VERSIONS.txt.
#
#   LayerFS v0.1.7 (commit e7713d03..., MIT) built from source with Rust 1.85.1
#   runtime image node:24.21.0-bookworm pinned by digest (judge/runtime/)
#   express v5.2.1 (commit dbac741a...) + npm ci from judge/express-package-lock.json
#   (upstream has no lockfile; the resolved tree must match judge/resolved-deps.txt)
#   clean-baseline mocha pass count -> $PREFIX/baseline.json
#
# Usage: bash judge/setup.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${HOME}/layerfs-race"
SRC="${PREFIX}/src"

LAYERFS_TAG="v0.1.7"
LAYERFS_COMMIT="e7713d034b029c358c657959b7737e8d23c9d1e7"
EXPRESS_TAG="v5.2.1"
EXPRESS_COMMIT="dbac741a49a5a64336b70c06e85c2e2706e36336"
RUST="1.85.1"

log() { echo "[setup] $*"; }

mkdir -p "${SRC}"

# --- docker ---------------------------------------------------------------
if ! docker info >/dev/null 2>&1; then
  log "starting docker"
  start-docker
fi
docker info >/dev/null

# --- rust toolchain -------------------------------------------------------
if ! rustup toolchain list | grep -q "^${RUST}"; then
  log "making rustup dirs writable and installing rust ${RUST}"
  sudo chown -R "$(id -un):$(id -gn)" /usr/local/rustup /usr/local/cargo
  rustup toolchain install "${RUST}" --profile minimal
fi

# --- LayerFS source at the pinned tag -------------------------------------
LFS="${SRC}/layerfs"
if [ ! -d "${LFS}/.git" ]; then
  log "cloning layerfs ${LAYERFS_TAG}"
  rm -rf "${LFS}"
  git clone --depth 1 --branch "${LAYERFS_TAG}" \
    https://github.com/Ephemeral-AI-Lab/layerfs "${LFS}"
fi
LFS_HEAD="$(git -C "${LFS}" rev-parse HEAD)"
[ "${LFS_HEAD}" = "${LAYERFS_COMMIT}" ] || {
  echo "[setup] ERROR: layerfs HEAD ${LFS_HEAD} != pinned ${LAYERFS_COMMIT} (${LAYERFS_TAG})" >&2
  exit 1
}
log "layerfs HEAD ${LFS_HEAD}"

# --- build layerfs-node + layerfs-daemon (offline, locked) ------------------
if [ ! -f "${LFS}/core/target/release/liblayerfs_node.so" ] \
   || [ ! -x "${LFS}/core/target/release/layerfs-daemon" ]; then
  log "cargo fetch --locked"
  cargo +"${RUST}" fetch --locked --manifest-path "${LFS}/core/Cargo.toml"
  log "cargo build --release -p layerfs-node -p layerfs-daemon (a few minutes)"
  cargo +"${RUST}" build --manifest-path "${LFS}/core/Cargo.toml" \
    --offline --locked --release -p layerfs-node -p layerfs-daemon
fi
cp "${LFS}/core/target/release/liblayerfs_node.so" "${LFS}/sdk/js/native/layerfs.node"
LAYERFS_DAEMON="${LFS}/core/target/release/layerfs-daemon"

# --- runtime image (vendored Dockerfile; base pinned by digest) ------------
if ! docker image inspect layerfs-race-runtime >/dev/null 2>&1; then
  log "building runtime image layerfs-race-runtime"
  docker build -t layerfs-race-runtime "${HERE}/runtime"
fi
LAYERFS_IMAGE="$(docker image inspect layerfs-race-runtime --format '{{.Id}}')"

# --- express source at the pinned tag + npm install ------------------------
EXP="${SRC}/express"
if [ ! -d "${EXP}/.git" ]; then
  log "cloning express ${EXPRESS_TAG}"
  rm -rf "${EXP}"
  git clone --depth 1 --branch "${EXPRESS_TAG}" \
    https://github.com/expressjs/express "${EXP}"
fi
EXP_HEAD="$(git -C "${EXP}" rev-parse HEAD)"
[ "${EXP_HEAD}" = "${EXPRESS_COMMIT}" ] || {
  echo "[setup] ERROR: express HEAD ${EXP_HEAD} != pinned ${EXPRESS_COMMIT}" >&2
  exit 1
}
# express v5.2.1 ships no lockfile (.npmrc package-lock=false), so a plain
# npm install floats; install from the committed lockfile instead. It pins
# the tag-era send@1.1.0 (send@1.2.x breaks 55 res.sendFile/res.download tests).
if [ ! -d "${EXP}/node_modules" ]; then
  log "npm ci from judge/express-package-lock.json"
  cp "${HERE}/express-package-lock.json" "${EXP}/package-lock.json"
  ( cd "${EXP}" && npm ci --package-lock=true --no-audit --no-fund )
fi
# The full resolved dependency tree is recorded, one name@version per line,
# with its complete sha256 (committed snapshot: judge/resolved-deps.txt).
# npm ls can exit non-zero on peer/invalid notes while still printing the tree
( cd "${EXP}" && npm ls --all --json || true ) | node -e '
  const data = JSON.parse(require("fs").readFileSync(0, "utf8"));
  const lines = [];
  const walk = (name, node) => {
    if (!node || !node.version) return;
    lines.push(`${name}@${node.version}`);
    for (const [n, dep] of Object.entries(node.dependencies ?? {})) walk(n, dep);
  };
  if (data.name && data.version) lines.push(`${data.name}@${data.version}`);
  for (const [n, dep] of Object.entries(data.dependencies ?? {})) walk(n, dep);
  console.log([...new Set(lines)].sort().join("\n"));
' > "${PREFIX}/resolved-deps.txt"
DEPS_SHA="$(sha256sum "${PREFIX}/resolved-deps.txt" | awk '{print $1}')"
echo "${DEPS_SHA}  resolved-deps.txt" > "${PREFIX}/resolved-deps.sha256"
# dependency drift breaks the pinned-suite oracle: refuse to go on when the
# freshly resolved tree differs from the committed snapshot.
if ! cmp -s "${PREFIX}/resolved-deps.txt" "${HERE}/resolved-deps.txt"; then
  echo "[setup] ERROR: resolved deps differ from judge/resolved-deps.txt:" >&2
  diff "${HERE}/resolved-deps.txt" "${PREFIX}/resolved-deps.txt" | head -20 >&2 || true
  exit 1
fi

# --- pristine bugged checkout + full-tree digest (oracle reference) --------
# express + the injected bug, digested over every file except .git
# (test/ and node_modules included). grade.sh copies this tree for the
# artifact and the grader re-digests the pre-publish base layer the same
# way, so an artifact that inits from a tampered tree fails base-intact.
BUGGED="${PREFIX}/bugged"
log "building the pristine bugged checkout"
rm -rf "${BUGGED}"
cp -a "${EXP}" "${BUGGED}"
( cd "${BUGGED}" && git apply --whitespace=nowarn "${HERE}/../examples/bug.patch" ) \
  || { echo "[setup] ERROR: bug.patch does not apply to ${EXP##*/}" >&2; exit 1; }
grep -q "subdomain offset', 3" "${BUGGED}/lib/application.js" \
  || { echo "[setup] ERROR: bug.patch did not inject the bug" >&2; exit 1; }
# Same digest as grader.mjs TREE_DIGEST: contents of every regular file plus
# type, mode and target of every file and symlink (a retargeted
# node_modules/.bin link changes it).
BUGGED_SHA="$(cd "${BUGGED}" && { find . -path ./.git -prune -o \( -type f -o -type l \) -printf "%y %m %p -> %l\\n" | LC_ALL=C sort; find . -path ./.git -prune -o -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum; } | sha256sum | cut -d" " -f1)"

# --- clean-baseline pass count ---------------------------------------------
if [ ! -f "${PREFIX}/baseline.json" ]; then
  log "measuring the clean-baseline suite count (one mocha run)"
  ( cd "${EXP}" && npx mocha --exit --require test/support/env --reporter dot \
      --check-leaks test/ test/acceptance/ 2>&1 | grep -E '[0-9]+ (passing|failing)' | tail -5 ) > "${PREFIX}/baseline.out" || true
  PASS="$(grep -oE '[0-9]+ passing' "${PREFIX}/baseline.out" | grep -oE '[0-9]+' || true)"
  FAILN="$(grep -oE '[0-9]+ failing' "${PREFIX}/baseline.out" | grep -oE '[0-9]+' || echo 0)"
  [ -n "${PASS}" ] && [ "${FAILN:-0}" = "0" ] || {
    echo "[setup] ERROR: clean baseline is not green:" >&2
    cat "${PREFIX}/baseline.out" >&2
    exit 1
  }
  printf '{"passing": %s, "failing": 0}\n' "${PASS}" > "${PREFIX}/baseline.json"
fi
BASELINE_PASS="$(grep -oE '"passing": [0-9]+' "${PREFIX}/baseline.json" | grep -oE '[0-9]+')"

# --- env file consumed by grade.sh ------------------------------------------
cat > "${PREFIX}/env.sh" <<EOF
LAYERFS_SRC="${LFS}"
LAYERFS_DAEMON="${LAYERFS_DAEMON}"
LAYERFS_IMAGE="${LAYERFS_IMAGE}"
LAYERFS_DOCKER="/var/run/docker.sock"
EXPRESS_SRC="${EXP}"
BUGGED_SRC="${BUGGED}"
BUGGED_SHA="${BUGGED_SHA}"
BASELINE_PASS="${BASELINE_PASS}"
CORRECT_INDEX="3"
EOF

# --- per-run versions record (what this install actually resolved) ---------
cat > "${PREFIX}/VERSIONS.txt" <<EOF
layerfs   ${LAYERFS_TAG} ${LFS_HEAD}
rust      ${RUST}
image     ${LAYERFS_IMAGE}
express   ${EXPRESS_TAG} ${EXP_HEAD}
baseline  ${BASELINE_PASS} passing / 0 failing
deps      ${PREFIX}/resolved-deps.txt ($(wc -l < "${PREFIX}/resolved-deps.txt") packages)
deps-sha256 ${DEPS_SHA}
bugged-sha256 ${BUGGED_SHA}
EOF

log "done."
echo "  layerfs   -> ${LFS} (${LAYERFS_TAG} ${LFS_HEAD})"
echo "  daemon    -> ${LAYERFS_DAEMON}"
echo "  image     -> ${LAYERFS_IMAGE}"
echo "  express   -> ${EXP} (${EXPRESS_TAG} ${EXP_HEAD})"
echo "  baseline  -> ${BASELINE_PASS} passing / 0 failing"
echo "  deps      -> ${PREFIX}/resolved-deps.txt (sha256 ${DEPS_SHA})"
echo "  bugged    -> ${BUGGED} (tree sha256 ${BUGGED_SHA})"
echo "  env       -> ${PREFIX}/env.sh"
