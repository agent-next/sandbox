#!/usr/bin/env python3
"""Independent G-code interpreter + analytic STL model for the 3dprint judge.

Stdlib only. Two halves:

  GCode replay -- G0/G1/G28/G90/G91/G92/M82/M83/M104/M109/M140/M190, word
  parsing per the RepRap convention (N..* line numbers and checksums
  tolerated, ; and (...) comments stripped).  Measures: extruding segments
  with Z, deposited E length in whichever mode the file selects, layer Z
  sequence, temperature set points in order, and a constant-velocity print
  time lower bound.

  STL model -- volume by signed tetrahedra; per-layer rasterised slice
  (scanline fill at a fixed pitch) giving area and shell fraction, used to
  derive the expected deposited volume for a given wall count and infill
  density; and the part footprint polygon (union of slice boundary
  segments) for the near-part gate.
"""

import math
import re


# ------------------------------------------------------------- gcode ----
WORD_RE = re.compile(r"([A-Za-z])\s*(-?\d*\.?\d+)")


def strip_comment(line):
    """Remove ; and (...) comments and the leading Nn/checksum tail."""
    out = []
    depth = 0
    for ch in line:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth = max(0, depth - 1)
        elif ch == ';' and depth == 0:
            break
        elif depth == 0:
            out.append(ch)
    s = ''.join(out).strip()
    # strip "N123 " line-number prefix and "*45" checksum
    if s.startswith('N'):
        i = s.find(' ')
        if i > 0:
            s = s[i + 1:]
    if '*' in s:
        s = s[:s.index('*')]
    return s.strip()


class Machine:
    def __init__(self):
        self.pos = {'X': 0.0, 'Y': 0.0, 'Z': 0.0}
        self.e = 0.0
        self.off = {'X': 0.0, 'Y': 0.0, 'Z': 0.0, 'E': 0.0}
        self.absolute_xyz = True       # G90/G91
        self.absolute_e = True         # M82/M83
        self.feed = 0.0                # mm/min
        self.time_s = 0.0
        self.extr_moves = []           # (z, x0,y0, x1,y1, dE, feed)
        self.travel_moves = []
        self.layer_first_z = []        # ordered Z values at which extrusion starts
        self.e_total = 0.0             # sum of positive dE (gross extrusion)
        self.e_consumed = 0.0          # signed sum of dE: net filament consumed
        self.nozzle_cmds = []          # (seq, temp)
        self.bed_cmds = []             # (seq, temp)
        self.first_extrude_seq = None
        self.last_extrude_seq = None
        self.seq = 0
        self.errors = []

    def _target(self, cur, word, absolute):
        return word if absolute else cur + word

    def cmd(self, raw):
        self.seq += 1
        line = strip_comment(raw)
        if not line:
            return
        words = WORD_RE.findall(line)
        if not words:
            return
        code = words[0][0].upper() + ('%g' % float(words[0][1]))
        args = {w[0].upper(): float(w[1]) for w in words[1:]}
        if code == 'G90':
            self.absolute_xyz = True
        elif code == 'G91':
            self.absolute_xyz = False
        elif code == 'M82':
            self.absolute_e = True
        elif code == 'M83':
            self.absolute_e = False
        elif code == 'G92':
            # set logical position: adjust offsets
            for ax in 'XYZE':
                if ax in args:
                    cur = self.e if ax == 'E' else self.pos[ax]
                    self.off[ax] = cur - args[ax]
            if 'E' in args:
                self.e = args['E']
            for ax in 'XYZ':
                if ax in args:
                    self.pos[ax] = args[ax]
        elif code == 'G28':
            homes = [a for a in 'XYZ' if a in args] or ['X', 'Y', 'Z']
            for ax in homes:
                self.pos[ax] = 0.0
                self.off[ax] = 0.0
        elif code in ('G0', 'G1'):
            self._move(args)
        elif code == 'G4':
            self.time_s += args.get('S', args.get('P', 0.0) / 1000.0)
        elif code in ('M104', 'M109'):
            self.nozzle_cmds.append((self.seq, args.get('S', args.get('R', 0.0))))
        elif code in ('M140', 'M190'):
            self.bed_cmds.append((self.seq, args.get('S', args.get('R', 0.0))))
        # everything else is accepted but ignored (fans, accel, M73, ...)

    def _move(self, args):
        if 'F' in args:
            self.feed = args['F']
        x0, y0, z0, e0 = self.pos['X'], self.pos['Y'], self.pos['Z'], self.e
        # E mode: Marlin semantics -- G91 makes every axis incl. E relative;
        # under G90, M83 selects relative E.
        e_relative = not self.absolute_e or not self.absolute_xyz
        de = 0.0
        if 'E' in args:
            de = args['E'] if e_relative else args['E'] - e0
            self.e = e0 + de
        for ax in 'XYZ':
            if ax in args:
                self.pos[ax] = self._target(self.pos[ax], args[ax],
                                            self.absolute_xyz)
        x1, y1, z1 = self.pos['X'], self.pos['Y'], self.pos['Z']
        # RepRap feedrate: F is the XYZ(E)-vector speed; the move takes the
        # time of the longest contributing component.
        dist = math.dist((x0, y0, z0), (x1, y1, z1))
        if dist == 0.0:
            dist = abs(de)
        if self.feed > 0:
            self.time_s += dist / self.feed * 60.0
        self.e_consumed += de
        if de > 0:
            self.e_total += de
            if self.first_extrude_seq is None:
                self.first_extrude_seq = self.seq
            self.last_extrude_seq = self.seq
            self.extr_moves.append((z1, x0, y0, x1, y1, de, self.feed))
            if not self.layer_first_z or z1 > self.layer_first_z[-1][0] + 0.05:
                self.layer_first_z.append((z1, self.seq))
            elif z1 < self.layer_first_z[-1][0] - 0.05:
                self.errors.append(
                    'extrusion layer Z regression %.3f -> %.3f at line %d'
                    % (self.layer_first_z[-1][0], z1, self.seq))
        else:
            self.travel_moves.append((z1, x0, y0, x1, y1, de, self.feed))


def replay(path):
    m = Machine()
    with open(path, 'r', errors='replace') as fh:
        for line in fh:
            m.cmd(line)
    return m


def slicer_estimated_time_s(path):
    """Parse the slicer's own time estimate comment (cross-check only)."""
    for line in open(path, 'r', errors='replace'):
        m = re.search(r'model printing time:\s*(\d+)m\s*(\d+)s', line)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
        m = re.search(r'model printing time:\s*(\d+)h\s*(\d+)m\s*(\d+)s', line)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        m = re.search(r'estimated printing time.*=\s*(\d+)m\s*(\d+)s', line)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
    return None


def slicer_filament_mm(path):
    for line in open(path, 'r', errors='replace'):
        m = re.search(r'filament used \[mm\]\s*=\s*([\d.]+)', line)
        if m:
            return float(m.group(1))
    return None


# --------------------------------------------------------------- stl ----
def load_stl(path):
    tris = []
    cur = []
    for line in open(path, 'r', errors='replace'):
        t = line.split()
        if len(t) == 4 and t[0] == 'vertex':
            cur.append((float(t[1]), float(t[2]), float(t[3])))
            if len(cur) == 3:
                tris.append(tuple(cur))
                cur = []
    return tris


def stl_volume(tris):
    v = 0.0
    for a, b, c in tris:
        v += (a[0] * (b[1] * c[2] - b[2] * c[1])
              - a[1] * (b[0] * c[2] - b[2] * c[0])
              + a[2] * (b[0] * c[1] - b[1] * c[0]))
    return abs(v) / 6.0


def stl_bbox(tris):
    xs = [p[0] for t in tris for p in t]
    ys = [p[1] for t in tris for p in t]
    zs = [p[2] for t in tris for p in t]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def slice_segments(tris, z):
    """Intersect the mesh with plane z -> list of 2D segments ((x0,y0),(x1,y1))."""
    segs = []
    for a, b, c in tris:
        pts = []
        for p, q in ((a, b), (b, c), (c, a)):
            z0, z1 = p[2] - z, q[2] - z
            if (z0 < 0) != (z1 < 0):
                den = z0 - z1
                if den == 0:
                    continue
                t = z0 / den
                pts.append((p[0] + (q[0] - p[0]) * t,
                            p[1] + (q[1] - p[1]) * t))
            elif z0 == 0:
                pts.append((p[0], p[1]))
            elif z1 == 0:
                pts.append((q[0], q[1]))
        # dedupe consecutive points
        uniq = []
        for p in pts:
            if not uniq or math.hypot(p[0] - uniq[-1][0], p[1] - uniq[-1][1]) > 1e-9:
                uniq.append(p)
        if len(uniq) == 2:
            segs.append((uniq[0], uniq[1]))
        elif len(uniq) == 3:
            segs.append((uniq[0], uniq[1]))
            segs.append((uniq[1], uniq[2]))
    return segs


def height_index(tris, zbins):
    """Bucket triangles into unit-z bins so a slice scan only walks the
    triangles whose z-range brackets the plane (typically 30x fewer)."""
    idx = [[] for _ in range(zbins + 2)]
    for t in tris:
        lo = max(0, int(min(p[2] for p in t)))
        hi = min(zbins, int(max(p[2] for p in t)) + 1)
        for b in range(lo, hi + 1):
            idx[b].append(t)
    return idx


def slice_segments_bucketed(bucket, z):
    """slice_segments over one z-bucket from height_index()."""
    return slice_segments(bucket, z)


def rasterize(segs, bbox, pitch):
    """Fill a grid: returns set of (i,j) inside cells.

    Scanline fill: for each grid row j (y = y0 + (j+0.5)*pitch) collect the
    x-intersections of segments crossing that row, sort, fill between pairs.
    """
    (x0, y0, _), (x1, y1, _) = bbox
    ny = int((y1 - y0) / pitch) + 1
    nx = int((x1 - x0) / pitch) + 1
    inside = set()
    for j in range(ny):
        y = y0 + (j + 0.5) * pitch
        xs = []
        for (ax, ay), (bx, by) in segs:
            if (ay <= y) != (by <= y):
                xs.append(ax + (bx - ax) * (y - ay) / (by - ay))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            i0 = int((xs[k] - x0) / pitch + 0.5)
            i1 = int((xs[k + 1] - x0) / pitch + 0.5)
            for i in range(i0, i1 + 1):
                inside.add((i, j))
    return inside, nx, ny


def shell_fraction(inside, shell_cells):
    """Fraction of inside cells within `shell_cells` dilations of the edge."""
    if not inside:
        return 0.0
    boundary = inside
    shell = set()
    frontier = set()
    for c in inside:
        i, j = c
        if any((i + di, j + dj) not in inside
               for di in (-1, 0, 1) for dj in (-1, 0, 1)):
            frontier.add(c)
    for _ in range(shell_cells):
        new = set()
        for (i, j) in frontier:
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    c = (i + di, j + dj)
                    if c in inside and c not in shell:
                        new.add(c)
        shell |= new
        frontier = new
    return len(shell) / len(inside)


def point_to_segments_dist(px, py, segs):
    best = float('inf')
    for (ax, ay), (bx, by) in segs:
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        if l2 == 0:
            d = math.hypot(px - ax, py - ay)
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
            d = math.hypot(px - ax - t * dx, py - ay - t * dy)
        if d < best:
            best = d
    return best


def point_in_segs(px, py, segs):
    """Ray cast +x against boundary segments."""
    n = 0
    for (ax, ay), (bx, by) in segs:
        if (ay <= py) != (by <= py):
            x = ax + (bx - ax) * (py - ay) / (by - ay)
            if x > px:
                n += 1
    return n % 2 == 1


def dist_to_footprint(px, py, fp_segs):
    if point_in_segs(px, py, fp_segs):
        return 0.0
    return point_to_segments_dist(px, py, fp_segs)


def expected_deposit(tris, bbox, layer_zs, layer_hs, pitch, wall_loops,
                     line_width, infill, solid_layers_bottom,
                     solid_layers_top):
    """Expected deposited volume (mm^3) for the part under a raster model.

    For each extrusion layer: slice at its mid height, rasterise at `pitch`,
    shell = cells within wall_loops*line_width of the boundary. Expected =
    area*lh*(shell + (1-shell)*infill); the bottom/top solid layers count
    as fully dense.
    """
    (x0, y0, z0), (x1, y1, z1) = bbox
    shell_cells = max(1, int(round(wall_loops * line_width / pitch)))
    n = len(layer_zs)
    hidx = height_index(tris, int(math.ceil(z1)))
    total = 0.0
    for idx, (z, lh) in enumerate(zip(layer_zs, layer_hs)):
        zmid = z - 0.5 * lh
        if zmid <= z0 or zmid >= z1:
            continue
        segs = slice_segments(hidx[min(int(zmid), len(hidx) - 1)], zmid)
        inside, nx, ny = rasterize(segs, bbox, pitch)
        area = len(inside) * pitch * pitch
        solid = idx < solid_layers_bottom or idx >= n - solid_layers_top
        if solid:
            fill = 1.0
        else:
            sf = shell_fraction(inside, shell_cells)
            fill = sf + (1.0 - sf) * infill
        total += area * lh * fill
    return total


def footprint_segments(tris, bbox, n_slices=6):
    """Union-ish boundary: segments of the slice at several heights.

    For distance queries we only need 'outside vs inside': we take the
    slice at the widest layer (z = zmin + 0.1*height) and reuse it.
    """
    (x0, y0, z0), (x1, y1, z1) = bbox
    z = z0 + 0.1 * (z1 - z0)
    return slice_segments(tris, z)
