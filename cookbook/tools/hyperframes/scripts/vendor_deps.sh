#!/bin/bash
# Copy the exact pinned runtime libraries out of node_modules into vendor/, so
# the composition never touches the network at render time.
#
# The copies are git-ignored and rebuilt by `npm ci` + this script; versions are
# pinned by package.json (gsap, three). Run from anywhere:
#
#     bash cookbook/tools/hyperframes/scripts/vendor_deps.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ="$(cd "$HERE/.." && pwd)"
VENDOR="$PROJ/vendor"

if [ ! -d "$PROJ/node_modules/gsap" ] || [ ! -d "$PROJ/node_modules/three" ]; then
  echo "vendor_deps: node_modules missing; run 'npm ci' in $PROJ first" >&2
  exit 1
fi

mkdir -p "$VENDOR"

# GSAP: the UMD build the composition <script> tag loads.
cp "$PROJ/node_modules/gsap/dist/gsap.min.js" "$VENDOR/gsap.min.js"

# Three.js: the ES module build, resolved by the importmap in the composition.
# three.module.js re-exports from ./three.core.js, so that file must sit beside
# it or Chrome 404s and every WebGL shot renders blank.
cp "$PROJ/node_modules/three/build/three.module.js" "$VENDOR/three.module.js"
cp "$PROJ/node_modules/three/build/three.core.js" "$VENDOR/three.core.js"
# GLTFLoader, resolved by the importmap sub-path "three/addons/".
mkdir -p "$VENDOR/addons/loaders" "$VENDOR/addons/utils"
cp "$PROJ/node_modules/three/examples/jsm/loaders/GLTFLoader.js" \
   "$VENDOR/addons/loaders/GLTFLoader.js"
cp "$PROJ/node_modules/three/examples/jsm/utils/BufferGeometryUtils.js" \
   "$VENDOR/addons/utils/BufferGeometryUtils.js"

echo "vendored gsap + three into $VENDOR:"
ls -1 "$VENDOR" "$VENDOR/addons/loaders" "$VENDOR/addons/utils"
