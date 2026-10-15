#!/usr/bin/env python3
"""Write a tiny torus .glb (binary glTF) for the model3d shot — pure stdlib,
no committed binary needed. Usage: gen_glb.py <out.glb>
"""

from __future__ import annotations

import json
import math
import struct
import sys

# Teal from the composition palette.
TEAL = (0.180, 0.769, 0.714, 1.0)


def torus(major: float, minor: float, nu: int, nv: int):
    """positions, normals, indices for a Z-up torus centred at origin."""
    pos, nrm, idx = [], [], []
    for i in range(nu):
        u = 2 * math.pi * i / nu
        cu, su = math.cos(u), math.sin(u)
        for j in range(nv):
            v = 2 * math.pi * j / nv
            cv, sv = math.cos(v), math.sin(v)
            pos += [(major + minor * cv) * cu,
                    (major + minor * cv) * su,
                    minor * sv]
            nrm += [cv * cu, cv * su, sv]
    for i in range(nu):
        for j in range(nv):
            a = i * nv + j
            b = ((i + 1) % nu) * nv + j
            c = ((i + 1) % nu) * nv + (j + 1) % nv
            d = i * nv + (j + 1) % nv
            idx += [a, b, d, b, c, d]
    return pos, nrm, idx


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <out.glb>", file=sys.stderr)
        return 2
    pos, nrm, idx = torus(1.0, 0.42, 40, 20)
    pos_b = struct.pack(f"<{len(pos)}f", *pos)
    nrm_b = struct.pack(f"<{len(nrm)}f", *nrm)
    idx_b = struct.pack(f"<{len(idx)}H", *idx)
    blob = pos_b + nrm_b + idx_b

    views = [
        {"buffer": 0, "byteOffset": 0, "byteLength": len(pos_b),
         "target": 34962},
        {"buffer": 0, "byteOffset": len(pos_b), "byteLength": len(nrm_b),
         "target": 34962},
        {"buffer": 0, "byteOffset": len(pos_b) + len(nrm_b),
         "byteLength": len(idx_b), "target": 34963},
    ]
    n_verts = len(pos) // 3
    lo = [min(pos[k::3]) for k in range(3)]
    hi = [max(pos[k::3]) for k in range(3)]
    gltf = {
        "asset": {"version": "2.0", "generator": "gen_glb.py"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{
            "attributes": {"POSITION": 0, "NORMAL": 1},
            "indices": 2, "material": 0,
        }]}],
        "materials": [{"pbrMetallicRoughness": {
            "baseColorFactor": list(TEAL),
            "metallicFactor": 0.65,
            "roughnessFactor": 0.32,
        }}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": n_verts,
             "type": "VEC3", "min": lo, "max": hi},
            {"bufferView": 1, "componentType": 5126, "count": n_verts,
             "type": "VEC3"},
            {"bufferView": 2, "componentType": 5123, "count": len(idx),
             "type": "SCALAR"},
        ],
        "bufferViews": views,
        "buffers": [{"byteLength": len(blob)}],
    }
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)  # JSON chunk pads with spaces
    bin_pad = blob + b"\x00" * (-len(blob) % 4)
    total = 12 + 8 + len(js) + 8 + len(bin_pad)
    with open(argv[1], "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, total))
        fh.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        fh.write(struct.pack("<II", len(bin_pad), 0x004E4942) + bin_pad)
    print(f"wrote {argv[1]} ({total} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
