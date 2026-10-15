#!/usr/bin/env bash
#
# setup.sh -- install the pinned toolchain this demo uses, then build the
# three stripped target binaries.  Idempotent: a second run is a no-op
# except for the cheap rebuild/verify steps.
#
# Pinned, sha256-checked downloads into $HOME/.rea-demo-tools:
#   Eclipse Temurin JDK 21.0.9+10        (Ghidra's runtime)
#   Ghidra 12.1.2 PUBLIC                 (REA's only supported version)
#   rea-agents 3.1.0 npm tarball         (the REA CLI, sha512-checked)
#   Node.js v24.9.0                      (only if PATH lacks node >= 24.11)
#
# The C compiler is the image's Debian gcc, verified to be exactly 12.2.0;
# if it is missing, an exact pinned gcc-12 package install is attempted.
# The built binaries' sha256 must match judge/ground_truth/EXPECTED.sha256,
# which is what the committed REA evidence in examples/good/ was produced
# against.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "${HERE}")"
GT="${HERE}/ground_truth"

TOOLS="${HOME}/.rea-demo-tools"
BIN="${TOOLS}/bin"
DL="${HOME}/.cache/rea-demo"
mkdir -p "${TOOLS}" "${BIN}" "${DL}"

log() { printf 'setup: %s\n' "$*"; }
die() { printf 'setup: %s\n' "$*" >&2; exit 1; }

fetch() { # fetch <url> <dest> <sha256|sha512:hex>
    local url="$1" dest="$2" want="$3" have=""
    if [ ! -s "${dest}" ]; then
        log "downloading $(basename "${dest}")"
        curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors \
            -o "${dest}.part" "${url}"
        mv "${dest}.part" "${dest}"
    else
        log "reusing cached $(basename "${dest}")"
    fi
    case "${want}" in
        sha512:*) have="$(sha512sum "${dest}" | awk '{print $1}')"
                  want="${want#sha512:}" ;;
        *)        have="$(sha256sum "${dest}" | awk '{print $1}')" ;;
    esac
    if [ "${have}" != "${want}" ]; then
        rm -f "${dest}"
        die "checksum mismatch for ${dest}; bad download removed, re-run"
    fi
}

# ---------------------------------------------------------------------------
# 0. Host prerequisites: gcc 12.2.0 (exact), plus curl/unzip/ps on PATH.
# ---------------------------------------------------------------------------
need_apt=0
for t in curl unzip ps gcc nm; do
    command -v "$t" >/dev/null 2>&1 || need_apt=1
done
if [ "${need_apt}" -eq 1 ]; then
    log "apt-get update (image apt lists may be empty)"
    sudo -n env DEBIAN_FRONTEND=noninteractive apt-get update -qq
    # The update must really have fetched lists before we trust apt.
    apt-cache policy gcc-12 2>/dev/null | grep -q 'Candidate: [0-9]' \
        || die "apt-get update fetched no usable package lists"
    sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y \
        --no-install-recommends gcc-12 procps unzip curl binutils
fi
command -v gcc >/dev/null 2>&1 || die "gcc not available"
GCC_VER="$(gcc -dumpfullversion 2>/dev/null || gcc -dumpversion)"
if [ "${GCC_VER}" != "12.2.0" ]; then
    die "gcc ${GCC_VER} found; this demo pins Debian gcc 12.2.0 \
(binaries must match judge/ground_truth/EXPECTED.sha256)"
fi
log "gcc ${GCC_VER} ok"

# ---------------------------------------------------------------------------
# 1. Node.js >= 24.11 (rea-agents 3.1.0 engine floor).  Use the image's node
#    when it qualifies; else unpack the pinned tarball into $HOME.
# ---------------------------------------------------------------------------
NODE_VER=""
if command -v node >/dev/null 2>&1; then
    NODE_VER="$(node --version)"
fi
node_ok() {
    node -e 'const v=process.versions.node.split(".").map(Number);
             process.exit((v[0]>24)||(v[0]===24&&v[1]>=11)||(v[0]===22&&v[1]>=19)?0:1)' \
        >/dev/null 2>&1
}
if ! node_ok; then
    NODE_TAR="node-v24.9.0-linux-x64.tar.xz"
    NODE_SHA256="f52ec50e959d72d5c680d9731420b2661cd2a8070e94c7369b6ddfcd8b7278be"
    fetch "https://nodejs.org/dist/v24.9.0/${NODE_TAR}" \
          "${DL}/${NODE_TAR}" "${NODE_SHA256}"
    if [ ! -x "${TOOLS}/node-v24.9.0-linux-x64/bin/node" ]; then
        log "extracting ${NODE_TAR}"
        tar -xJf "${DL}/${NODE_TAR}" -C "${TOOLS}"
    fi
    export PATH="${TOOLS}/node-v24.9.0-linux-x64/bin:${PATH}"
    node_ok || die "pinned node still unusable"
    NODE_VER="$(node --version)"
fi
log "node ${NODE_VER} ok"

# ---------------------------------------------------------------------------
# 2. Temurin JDK 21.0.9+10 (Ghidra runtime).
# ---------------------------------------------------------------------------
JDK_TAR="OpenJDK21U-jdk_x64_linux_hotspot_21.0.9_10.tar.gz"
JDK_SHA256="810d3773df7e0d6c4394e4e244b264c8b30e0b05a0acf542d065fd78a6b65c2f"
JDK_URL="https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.9%2B10/${JDK_TAR}"
JDK_DIR="${TOOLS}/jdk-21.0.9+10"
if [ ! -x "${JDK_DIR}/bin/java" ]; then
    fetch "${JDK_URL}" "${DL}/${JDK_TAR}" "${JDK_SHA256}"
    log "extracting ${JDK_TAR}"
    tar -xzf "${DL}/${JDK_TAR}" -C "${TOOLS}"
else
    log "jdk already present"
fi
export JAVA_HOME="${JDK_DIR}"
export PATH="${JDK_DIR}/bin:${PATH}"

# ---------------------------------------------------------------------------
# 3. Ghidra 12.1.2 PUBLIC (the only release rea-agents 3.1.0 accepts).
# ---------------------------------------------------------------------------
GH_ZIP="ghidra_12.1.2_PUBLIC_20260605.zip"
GH_SHA256="b62e81a0390618466c019c60d8c2f796ced2509c4c1aea4a37644a77272cf99d"
GH_URL="https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.2_build/${GH_ZIP}"
GH_DIR="${TOOLS}/ghidra_12.1.2_PUBLIC"
GH_PROPS="${GH_DIR}/Ghidra/application.properties"
if [ ! -f "${GH_PROPS}" ]; then
    fetch "${GH_URL}" "${DL}/${GH_ZIP}" "${GH_SHA256}"
    log "extracting ${GH_ZIP}"
    unzip -q "${DL}/${GH_ZIP}" -d "${TOOLS}"
else
    log "ghidra already present"
fi
export GHIDRA_INSTALL_DIR="${GH_DIR}"

# ---------------------------------------------------------------------------
# 4. rea-agents 3.1.0 -- npm tarball, sha512-checked, global-style install
#    into $HOME/.rea-demo-tools/npm (no sudo, deterministic prefix).
# ---------------------------------------------------------------------------
REA_TGZ="rea-agents-3.1.0.tgz"
REA_SHA512="8a9f637633af4ec2b034be57a2bf69860919a93c48fb8a08e3436bfd2743126e734d3c06bf12213b4e661d43f208e37c49c6ca7bf2826256780d320f768e7444"
REA_URL="https://registry.npmjs.org/rea-agents/-/${REA_TGZ}"
NPM_PREFIX="${TOOLS}/npm"
if [ ! -x "${NPM_PREFIX}/bin/rea" ]; then
    fetch "${REA_URL}" "${DL}/${REA_TGZ}" "sha512:${REA_SHA512}"
    log "installing rea-agents 3.1.0 into ${NPM_PREFIX}"
    npm install --global --prefix "${NPM_PREFIX}" "${DL}/${REA_TGZ}" >/dev/null
else
    log "rea-agents already present"
fi
"${NPM_PREFIX}/bin/rea" --version | grep -q '3\.1\.0' \
    || die "rea --version is not 3.1.0"

# ---------------------------------------------------------------------------
# 5. Build the three targets (stripped) + unstripped judge reference builds.
# ---------------------------------------------------------------------------
mkdir -p "${DEMO}/targets" "${GT}/build"
CFLAGS="-O2 -fno-asynchronous-unwind-tables"
for t in checksum proto keycheck; do
    gcc ${CFLAGS} -s -o "${DEMO}/targets/${t}" "${GT}/${t}.c"
    gcc ${CFLAGS}   -o "${GT}/build/${t}"    "${GT}/${t}.c"
done

# The build must be deterministic: build each target once more and compare.
for t in checksum proto keycheck; do
    gcc ${CFLAGS} -s -o "${GT}/build/.rebuild-${t}" "${GT}/${t}.c"
    cmp -s "${GT}/build/.rebuild-${t}" "${DEMO}/targets/${t}" \
        || die "non-deterministic build for ${t}"
    rm -f "${GT}/build/.rebuild-${t}"
done

# And it must be the same binary the committed REA evidence was made from.
if [ -f "${GT}/EXPECTED.sha256" ]; then
    ( cd "${DEMO}/targets" && sha256sum -c "${GT}/EXPECTED.sha256" ) \
        || die "built binaries differ from EXPECTED.sha256; see that file"
fi

# Symbol ranges for the address gates (from the unstripped builds).
python3 - "${GT}" <<'PYSYM'
import json, re, subprocess, sys, os
gt = sys.argv[1]
out = {}
for t in ("checksum", "proto", "keycheck"):
    syms = []
    nm = subprocess.run(["nm", "-S", "--defined-only",
                         os.path.join(gt, "build", t)],
                        capture_output=True, text=True, check=True).stdout
    for line in nm.splitlines():
        m = re.match(r"^([0-9a-f]+)\s+([0-9a-f]+)\s+[tT]\s+(\S+)$", line)
        if m:
            a, s, name = m.groups()
            syms.append({"name": name,
                         "start": int(a, 16),
                         "end": int(a, 16) + int(s, 16)})
    out[t] = syms
with open(os.path.join(gt, "build", "symbols.json"), "w") as fh:
    json.dump(out, fh, indent=1, sort_keys=True)
PYSYM

# ---------------------------------------------------------------------------
# 6. env.sh -- the one file the agent sources before running rea.
# ---------------------------------------------------------------------------
cat > "${DEMO}/env.sh" <<EOF
# generated by judge/setup.sh -- source before using the rea CLI
export GHIDRA_INSTALL_DIR="${GH_DIR}"
export JAVA_HOME="${JDK_DIR}"
export PATH="${NPM_PREFIX}/bin:${JDK_DIR}/bin:$(dirname "$(command -v node)"):\$PATH"
EOF

# ---------------------------------------------------------------------------
# 7. VERSIONS.txt -- record what actually got installed.
# ---------------------------------------------------------------------------
{
    echo "# VERSIONS.txt -- recorded by judge/setup.sh"
    echo "gcc (pinned 12.2.0)"
    gcc --version | head -1 | sed 's/^/  /'
    echo "node"
    echo "  ${NODE_VER} ($(command -v node))"
    echo "temurin jdk 21.0.9+10"
    echo "  url    : ${JDK_URL}"
    echo "  sha256 : ${JDK_SHA256}"
    "${JDK_DIR}/bin/java" -version 2>&1 | sed 's/^/  /'
    echo "ghidra 12.1.2 PUBLIC 20260605"
    echo "  url    : ${GH_URL}"
    echo "  sha256 : ${GH_SHA256}"
    grep -m1 application.version "${GH_PROPS}" | sed 's/^/  /'
    echo "rea-agents 3.1.0"
    echo "  url    : ${REA_URL}"
    echo "  sha512 : ${REA_SHA512}"
    "${NPM_PREFIX}/bin/rea" --version | sed 's/^/  /'
    echo "python3"
    python3 --version 2>&1 | sed 's/^/  /'
    echo "procps ps"
    ps --version | sed 's/^/  /'
} > "${HERE}/VERSIONS.txt"

log "targets built in ${DEMO}/targets (stripped)"
log "reference builds + symbols.json in ${GT}/build"
log "wrote ${DEMO}/env.sh and ${HERE}/VERSIONS.txt"
log "done"
