#!/usr/bin/env bash
# cookbook/layerfs-race: install the pinned toolchain idempotently into
# $HOME/.layerfs-race. Rules (cookbook/DEMO-STANDARD.md): exact versions,
# sha/commit-verified downloads, no "latest", nothing published in the last
# two weeks. What was installed is recorded in judge/VERSIONS.txt.
#
#   LayerFS v0.1.7 (commit e7713d03..., MIT) built from source with Rust 1.85.1
#   runtime image node:24.21.0-bookworm pinned by digest (judge/runtime/)
#   express v5.2.1 (commit dbac741a...) + npm install (no upstream lockfile;
#   the resolved tree is recorded in judge/resolved-deps.txt)
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
if [ ! -d "${EXP}/node_modules" ]; then
  log "npm install (express has no lockfile at ${EXPRESS_TAG}; resolved tree recorded)"
  ( cd "${EXP}" && npm install --no-audit --no-fund )
fi
# express@5.2.1 floats send@^1.1.0; send@1.2.x (current) breaks 55
# res.sendFile/res.download tests. Pin the tag-era send@1.1.0.
SEND_VER="$(cd "${EXP}" && node -e 'console.log(require("send/package.json").version)' 2>/dev/null || echo none)"
if [ "${SEND_VER}" != "1.1.0" ]; then
  log "pinning send@1.1.0 (was ${SEND_VER})"
  ( cd "${EXP}" && npm install --no-save --no-audit --no-fund send@1.1.0 )
fi
if [ ! -f "${PREFIX}/resolved-deps.txt" ]; then
  # express's .npmrc sets package-lock=false — there is no lockfile; the
  # resolved dependency tree is recorded instead.
  ( cd "${EXP}" && npm ls --all > "${PREFIX}/resolved-deps.txt" 2>/dev/null || npm ls > "${PREFIX}/resolved-deps.txt" )
  sha256sum "${PREFIX}/resolved-deps.txt" | awk '{print $1}' > "${PREFIX}/resolved-deps.sha256"
fi

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
BASELINE_PASS="${BASELINE_PASS}"
CORRECT_INDEX="3"
EOF

log "done."
echo "  layerfs   -> ${LFS} (${LAYERFS_TAG} ${LFS_HEAD})"
echo "  daemon    -> ${LAYERFS_DAEMON}"
echo "  image     -> ${LAYERFS_IMAGE}"
echo "  express   -> ${EXP} (${EXPRESS_TAG} ${EXP_HEAD})"
echo "  baseline  -> ${BASELINE_PASS} passing / 0 failing"
echo "  env       -> ${PREFIX}/env.sh"
