"""Self-contained binary/ASCII STL parser for the cad-verify-back judge.

Standard library only. Deliberately does NOT use any mesh library: a bad
export must not be laundered by the tool that produced it.

Parses, then checks:
  - watertight: every (undirected) edge is shared by exactly 2 triangles
  - orientation: every shared edge is traversed in opposite directions by
    its two triangles, and the divergence-theorem volume is positive
  - volume: signed tetrahedron sum, 1/3 scale-invariant of the divergence
    theorem for a closed mesh
"""
import struct
import sys


def parse_stl(path):
    """Return list of triangles [(v0, v1, v2)] as float triples, or exit 1."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 84:
        fail(f"STL too small to be valid ({len(data)} bytes)")
    # binary STL: 80-byte header + uint32 count + 50 bytes per triangle
    n_bin = struct.unpack_from("<I", data, 80)[0]
    looks_ascii = data[:5] == b"solid" and b"facet" in data[:512]
    tris = []
    if not looks_ascii and len(data) == 84 + 50 * n_bin and n_bin > 0:
        off = 84
        for _ in range(n_bin):
            vals = struct.unpack_from("<12fH", data, off)
            tris.append((
                (vals[3], vals[4], vals[5]),
                (vals[6], vals[7], vals[8]),
                (vals[9], vals[10], vals[11]),
            ))
            off += 50
        return tris
    # ASCII STL
    text = data.decode("utf-8", errors="replace")
    if "facet normal" not in text and "facet" not in text:
        fail("STL is neither a valid binary nor ASCII STL file")
    verts = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] == "vertex":
            try:
                verts.append(tuple(float(x) for x in parts[1:4]))
            except ValueError:
                fail("STL vertex line is not numeric")
    if len(verts) % 3 != 0:
        fail(f"STL has {len(verts)} vertices; not a multiple of 3")
    for i in range(0, len(verts), 3):
        tris.append((verts[i], verts[i + 1], verts[i + 2]))
    return tris


def check_mesh(tris):
    """Return (errors, metrics). errors non-empty -> not watertight/oriented.

    Every undirected edge must appear exactly twice, and in opposite
    directions (consistent winding).
    """
    errors = []
    edges = {}
    key = lambda v: (round(v[0], 5), round(v[1], 5), round(v[2], 5))
    for t in tris:
        ks = [key(v) for v in t]
        for i in range(3):
            e = (ks[i], ks[(i + 1) % 3])
            edges.setdefault(e, []).append(t)
    # each directed edge exactly once, each undirected pair exactly twice
    directed = {}
    for (a, b) in edges:
        directed.setdefault(frozenset((a, b)), []).append((a, b))
    n_bad = 0
    for und, dirs in directed.items():
        if len(dirs) != 2:
            errors.append(f"edge {sorted(und)[0]}->{sorted(und)[1]} shared by {len(dirs)} facets (need 2)")
            n_bad += 1
            if n_bad >= 5:
                errors.append("... (more)")
                break
        elif len(set(dirs)) != 2:
            errors.append(f"edge {sorted(und)[0]}->{sorted(und)[1]} duplicated in same direction (flipped facet)")
            n_bad += 1
            if n_bad >= 5:
                errors.append("... (more)")
                break
    # divergence-theorem volume: sum of signed tet volumes with origin apex
    vol = 0.0
    for (a, b, c) in tris:
        vol += (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        ) / 6.0
    return errors, {
        "triangles": len(tris),
        "volume_mm3": abs(vol),
        "signed_volume_mm3": vol,
    }


def fail(msg):
    print(f"stl: {msg}", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    tris = parse_stl(sys.argv[1])
    errs, m = check_mesh(tris)
    print(f"triangles={m['triangles']} volume={m['volume_mm3']:.3f} "
          f"watertight={'yes' if not errs else 'NO'}")
    for e in errs[:5]:
        print(f"  {e}", file=sys.stderr)
