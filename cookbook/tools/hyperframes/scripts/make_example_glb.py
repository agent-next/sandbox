#!/usr/bin/env python3
"""Write a tiny binary glTF (2.0) torus, for the template's 3D turntable shot.

    python3 make_example_glb.py out.glb [--major N] [--minor N]

The mesh is generated from a parametric torus, so the committed artifact is
this ~5 KB script rather than a binary. Default output is ~18 KB, well under
the 50 KB the test asserts. Standard library only; no glTF library needed —
glb is a 12-byte header followed by a JSON chunk and a BIN chunk, both 4-byte
aligned, so it is packed by hand here.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys

GLB_MAGIC = 0x46546C67  # 'glTF'
CHUNK_JSON = 0x4E4F534A  # 'JSON'
CHUNK_BIN = 0x004E4942  # 'BIN\0'


def torus(major: int, minor: int, r_major: float = 0.72, r_minor: float = 0.30):
    """Return (positions, normals, indices) for a torus of major/minor radii."""
    positions: list[float] = []
    normals: list[float] = []
    indices: list[int] = []

    for i in range(major):
        u = 2.0 * math.pi * i / major
        cu, su = math.cos(u), math.sin(u)
        for j in range(minor):
            v = 2.0 * math.pi * j / minor
            cv, sv = math.cos(v), math.sin(v)
            # Point on the torus surface.
            x = (r_major + r_minor * cv) * cu
            y = r_minor * sv
            z = (r_major + r_minor * cv) * su
            positions += [x, y, z]
            # Surface normal = (point - centre of tube) normalised.
            nx = cv * cu
            ny = sv
            nz = cv * su
            normals += [nx, ny, nz]

    for i in range(major):
        i2 = (i + 1) % major
        for j in range(minor):
            j2 = (j + 1) % minor
            a = i * minor + j
            b = i2 * minor + j
            c = i2 * minor + j2
            d = i * minor + j2
            indices += [a, b, c, a, c, d]

    return positions, normals, indices


def build_glb(positions: list[float], normals: list[float], indices: list[int]) -> bytes:
    pos_bytes = struct.pack(f"<{len(positions)}f", *positions)
    nrm_bytes = struct.pack(f"<{len(normals)}f", *normals)
    # uint16 indices; pad the index block + bin chunk to a 4-byte boundary.
    idx_bytes = struct.pack(f"<{len(indices)}H", *indices)
    if len(idx_bytes) % 4:
        idx_bytes += b"\x00" * (4 - len(idx_bytes) % 4)

    vertex_count = len(positions) // 3
    xs = positions[0::3]
    ys = positions[1::3]
    zs = positions[2::3]
    pos_min = [min(xs), min(ys), min(zs)]
    pos_max = [max(xs), max(ys), max(zs)]

    bin_blob = pos_bytes + nrm_bytes + idx_bytes
    pos_len, nrm_len, idx_len = len(pos_bytes), len(nrm_bytes), len(idx_bytes)

    gltf = {
        "asset": {"version": "2.0", "generator": "hyperframes-template/1.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "turntable-mesh"}],
        "meshes": [
            {
                "name": "torus",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1},
                        "indices": 2,
                        "mode": 4,  # TRIANGLES
                    }
                ],
            }
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,  # FLOAT
                "count": vertex_count,
                "type": "VEC3",
                "min": pos_min,
                "max": pos_max,
            },
            {
                "bufferView": 1,
                "componentType": 5126,
                "count": vertex_count,
                "type": "VEC3",
            },
            {
                "bufferView": 2,
                "componentType": 5123,  # UNSIGNED_SHORT
                "count": len(indices),
                "type": "SCALAR",
            },
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": pos_len, "target": 34962},
            {
                "buffer": 0,
                "byteOffset": pos_len,
                "byteLength": nrm_len,
                "target": 34962,
            },
            {
                "buffer": 0,
                "byteOffset": pos_len + nrm_len,
                "byteLength": idx_len,
                "target": 34963,
            },
        ],
        "buffers": [{"byteLength": len(bin_blob)}],
    }

    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)

    total = 12 + 8 + len(json_bytes) + 8 + len(bin_blob)
    out = struct.pack("<III", GLB_MAGIC, 2, total)
    out += struct.pack("<II", len(json_bytes), CHUNK_JSON) + json_bytes
    out += struct.pack("<II", len(bin_blob), CHUNK_BIN) + bin_blob
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", help="path to the .glb to write")
    parser.add_argument("--major", type=int, default=32, help="major segments")
    parser.add_argument("--minor", type=int, default=16, help="minor segments")
    args = parser.parse_args(argv)

    positions, normals, indices = torus(args.major, args.minor)
    blob = build_glb(positions, normals, indices)
    with open(args.out, "wb") as fh:
        fh.write(blob)
    print(f"wrote {args.out} ({len(blob)} bytes, {len(positions) // 3} verts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
