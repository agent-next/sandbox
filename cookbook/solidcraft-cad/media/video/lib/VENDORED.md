# Vendored Three.js

`lib/three.module.js`, `lib/three.core.js`, `lib/GLTFLoader.js` and
`lib/BufferGeometryUtils.js` are verbatim copies of the pinned npm package
**three 0.180.0** (`package.json` / `package-lock.json`), with exactly one class
of edit so they load as plain ES modules next to this composition without a
bundler: every `from 'three'` import specifier is rewritten to
`from './three.module.js'`, and GLTFLoader's relative import of
`../utils/BufferGeometryUtils.js` becomes `./BufferGeometryUtils.js`.

```
lib/three.module.js         = node_modules/three/build/three.module.js        (unmodified)
lib/three.core.js           = node_modules/three/build/three.core.js          (unmodified)
lib/GLTFLoader.js           = node_modules/three/examples/jsm/loaders/GLTFLoader.js         (imports rewritten)
lib/BufferGeometryUtils.js  = node_modules/three/examples/jsm/utils/BufferGeometryUtils.js  (imports rewritten)
```

Vendoring keeps the render deterministic and offline: HyperFrames loads these
files directly, so no node_modules resolution, CDN fetch or version drift is
involved in producing `media/demo.mp4`.

Licence: MIT, Copyright © 2010-2025 three.js authors — see
[LICENSE-three.txt](LICENSE-three.txt).

To re-vendor after bumping the pin:
`npm ci`, copy the four files above out of `node_modules/three/`, and apply the
import rewrites shown here.
