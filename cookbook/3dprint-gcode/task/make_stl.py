#!/usr/bin/env python3
"""Generate the demo STLs deterministically (stdlib only, no CAD package).

Parts:
  bracket.stl -- an L-bracket: a 40 x 20 x 4 base plate and a 24 x 20 x 11
      upright fused at its end into one solid, bounding box 40 x 20 x 15 mm,
      with a 5 mm through-hole bored vertically in the base and a 4 mm
      through-hole bored horizontally along Y in the upright.  Min corner at
      (20, 20, 0) so the printed part sits inside the bed with room for a
      skirt -- the judge slices with auto-arrange disabled, so the print
      position on the bed equals the STL position.
  cube.stl    -- a 25 mm calibration cube, min corner at (60, 60, 0)
      (judge cross-check oracle only).

The mesh is marching tetrahedra over the *analytic* signed distance function
of each solid (boxes minus cylinders).  Distances are exact, so vertices
land on edges and hole walls to bisection tolerance and flat faces are
planar to ~1e-6 mm -- no voxel staircase.  The STL volume and footprint match
the analytic solid to well under the judge's volume-band half-width.
Grid pitch 1 mm -> bracket.stl is ~29k triangles (~5 MB ASCII).

Usage: make_stl.py [--outdir DIR]
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

BISECT_STEPS = 24  # 1 mm / 2^24 < 1e-6 mm of vertex error


# ------------------------------------------------------------- SDFs -------
def sd_bracket(x, y, z):
    """Signed distance to the L-bracket solid. Negative inside."""
    def box(cx, cy, cz, hx, hy, hz):
        qx = abs(x - cx) - hx
        qy = abs(y - cy) - hy
        qz = abs(z - cz) - hz
        ox, oy, oz = max(qx, 0.0), max(qy, 0.0), max(qz, 0.0)
        outside = math.sqrt(ox * ox + oy * oy + oz * oz)
        inside = min(max(qx, max(qy, qz)), 0.0)
        return outside + inside

    base = box(20.0, 10.0, 2.0, 20.0, 10.0, 2.0)         # 40x20x4 @ z 0..4
    upright = box(28.0, 10.0, 9.5, 12.0, 10.0, 5.5)      # 24x20x11 @ z 4..15
    solid = min(base, upright)
    # vertical hole through the base: axis (8,10), r 2.5, z 0..4
    hole_v = max(math.hypot(x - 8.0, y - 10.0) - 2.5, abs(z - 2.0) - 2.0)
    # horizontal hole through the upright: axis along Y at (x=28, z=10), r 2
    hole_h = max(math.hypot(x - 28.0, z - 10.0) - 2.0, abs(y - 10.0) - 10.0)
    return max(solid, -hole_v, -hole_h)


def sd_cube(x, y, z):
    qx, qy, qz = (abs(x - 12.5) - 12.5, abs(y - 12.5) - 12.5,
                  abs(z - 12.5) - 12.5)
    ox, oy, oz = max(qx, 0.0), max(qy, 0.0), max(qz, 0.0)
    return math.sqrt(ox * ox + oy * oy + oz * oz) + \
        min(max(qx, max(qy, qz)), 0.0)


# -------------------------------------------------- marching tetrahedra ---
# Split each grid cube into 6 tetrahedra around the v000-v111 body diagonal.
# Vertices are bit-coded: bit2=x, bit1=y, bit0=z offsets within the cube
# (so v000=(0,0,0), v111=(dx,dy,dz)).  The 6 tets are the 6 monotone paths
# from v000 to v111 on the permutation cube:
#   v000 -> v100 -> v110 -> v111   and permutations.
TETS = [
    (0b000, 0b100, 0b110, 0b111),
    (0b000, 0b110, 0b010, 0b111),
    (0b000, 0b010, 0b011, 0b111),
    (0b000, 0b011, 0b001, 0b111),
    (0b000, 0b001, 0b101, 0b111),
    (0b000, 0b101, 0b100, 0b111),
]
TEDGES = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]


def mesh_surface(sd, bbox, pitch=1.0):
    minx, miny, minz, maxx, maxy, maxz = bbox
    nx = int(round((maxx - minx) / pitch))
    ny = int(round((maxy - miny) / pitch))
    nz = int(round((maxz - minz) / pitch))
    dx, dy, dz = (maxx - minx) / nx, (maxy - miny) / ny, (maxz - minz) / nz

    offsets = {b: ((b >> 2 & 1) * dx, (b >> 1 & 1) * dy, (b & 1) * dz)
               for b in range(8)}

    vcache = {}
    def sdf(i, j, k):
        key = (i, j, k)
        v = vcache.get(key)
        if v is None:
            v = sd(minx + i * dx, miny + j * dy, minz + k * dz)
            vcache[key] = v
        return v

    tris = []

    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                d = {b: sdf(i + (b >> 2 & 1), j + (b >> 1 & 1), k + (b & 1))
                     for b in range(8)}
                if all(v < 0 for v in d.values()) or \
                        all(v > 0 for v in d.values()):
                    continue
                base = (minx + i * dx, miny + j * dy, minz + k * dz)
                pts = {b: (base[0] + offsets[b][0],
                           base[1] + offsets[b][1],
                           base[2] + offsets[b][2]) for b in range(8)}

                for tet in TETS:
                    tpts = [pts[b] for b in tet]
                    tds = [d[b] for b in tet]
                    inside = [t < 0 for t in tds]
                    nin = sum(inside)
                    if nin == 0 or nin == 4:
                        continue

                    edge = {}
                    for a, b in TEDGES:
                        if inside[a] == inside[b]:
                            continue
                        pa, pb = tpts[a], tpts[b]
                        if not inside[a]:
                            pa, pb = pb, pa
                        lo, hi = 0.0, 1.0
                        for _ in range(BISECT_STEPS):
                            m = (lo + hi) * 0.5
                            q = (pa[0] + (pb[0] - pa[0]) * m,
                                 pa[1] + (pb[1] - pa[1]) * m,
                                 pa[2] + (pb[2] - pa[2]) * m)
                            if sd(*q) < 0:
                                lo = m
                            else:
                                hi = m
                        m = (lo + hi) * 0.5
                        edge[(a, b)] = (pa[0] + (pb[0] - pa[0]) * m,
                                        pa[1] + (pb[1] - pa[1]) * m,
                                        pa[2] + (pb[2] - pa[2]) * m)

                    if nin == 1:
                        a = inside.index(True)
                        others = [b for b in range(4) if b != a]
                        poly = [edge[(min(a, b), max(a, b))] for b in others]
                    elif nin == 3:
                        a = inside.index(False)
                        others = [b for b in range(4) if b != a]
                        poly = [edge[(min(a, b), max(a, b))] for b in others]
                        poly = [poly[0], poly[2], poly[1]]
                    else:  # nin == 2 -> one quad
                        ins = [t for t in range(4) if inside[t]]
                        out = [t for t in range(4) if not inside[t]]
                        q00 = edge[(min(ins[0], out[0]), max(ins[0], out[0]))]
                        q01 = edge[(min(ins[0], out[1]), max(ins[0], out[1]))]
                        q11 = edge[(min(ins[1], out[1]), max(ins[1], out[1]))]
                        q10 = edge[(min(ins[1], out[0]), max(ins[1], out[0]))]
                        poly = [q00, q10, q11, q01]

                    # Orient CCW seen from outside: flip if the triangle
                    # normal points into the solid (towards decreasing SDF).
                    def emit(p0, p1, p2):
                        cx = (p0[0] + p1[0] + p2[0]) / 3.0
                        cy = (p0[1] + p1[1] + p2[1]) / 3.0
                        cz = (p0[2] + p1[2] + p2[2]) / 3.0
                        eps = 0.02
                        g = (sd(cx + eps, cy, cz) - sd(cx - eps, cy, cz),
                             sd(cx, cy + eps, cz) - sd(cx, cy - eps, cz),
                             sd(cx, cy, cz + eps) - sd(cx, cy, cz - eps))
                        n = normal(p0, p1, p2)
                        if n[0] * g[0] + n[1] * g[1] + n[2] * g[2] < 0:
                            tris.append((p0, p2, p1))
                        else:
                            tris.append((p0, p1, p2))

                    emit(poly[0], poly[1], poly[2])
                    if len(poly) == 4:
                        emit(poly[0], poly[2], poly[3])
    return tris


def normal(a, b, c):
    ux, uy, uz = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    vx_, vy, vz = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    nx, ny, nz = (uy * vz - uz * vy, uz * vx_ - ux * vz, ux * vy - uy * vx_)
    n = (nx ** 2 + ny ** 2 + nz ** 2) ** 0.5 or 1.0
    return (nx / n, ny / n, nz / n)


def write_ascii_stl(path, tris, name, offset=(0.0, 0.0, 0.0)):
    ox, oy, oz = offset
    def sh(p):
        return (p[0] + ox, p[1] + oy, p[2] + oz)
    with open(path, "w") as fh:
        fh.write("solid %s\n" % name)
        for a, b, c in tris:
            n = normal(a, b, c)
            fh.write("  facet normal %.6g %.6g %.6g\n" % n)
            fh.write("    outer loop\n")
            for p_ in (a, b, c):
                q = sh(p_)
                fh.write("      vertex %.6f %.6f %.6f\n" % q)
            fh.write("    endloop\n  endfacet\n")
        fh.write("endsolid %s\n" % name)


def main():
    outdir = HERE
    if len(sys.argv) > 2 and sys.argv[1] == "--outdir":
        outdir = sys.argv[2]

    tris = mesh_surface(sd_bracket, (0.0, 0.0, 0.0, 40.0, 20.0, 15.0))
    write_ascii_stl(os.path.join(outdir, "bracket.stl"), tris, "bracket",
                    offset=(20.0, 20.0, 0.0))
    print("bracket.stl: %d triangles" % len(tris))

    tris = mesh_surface(sd_cube, (0.0, 0.0, 0.0, 25.0, 25.0, 25.0))
    write_ascii_stl(os.path.join(outdir, "cube.stl"), tris, "cube",
                    offset=(60.0, 60.0, 0.0))
    print("cube.stl: %d triangles" % len(tris))


if __name__ == "__main__":
    main()
