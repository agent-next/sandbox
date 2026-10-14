"""G-code parser and flat-endmill heightmap material-removal simulator.

cookbook/cnc-gcode judge engine.  Python 3.12 stdlib + numpy only.

Model (see SPEC.md):
  * the job is 2.5D milling with a cylindrical flat end mill;
  * the stock is a heightmap H on a grid of `grid_mm` cells (cell centres at
    (i+0.5)*g, (j+0.5)*g), initialised to Z = 0 (stock top);
  * a move sweeps the tool footprint -- grid cells within the tool radius
    (+1e-9 mm closed-set tie-break) of the move path (line or arc) -- and sets
    H = min(H, Z_end) there.  A ramping move is modelled at its end Z;
  * rapids remove material too: a rapid that hits stock is a crash the judge
    both flags (gate `rapid_safety`) and models.
"""
from __future__ import annotations

import math
import re

import numpy as np

TWO_PI = 2.0 * math.pi

# The judge interprets exactly this dialect; anything else is refused by name
# rather than silently reinterpreted.
SUPPORTED_G = {0, 1, 2, 3, 17, 21, 90}
SUPPORTED_M = {2, 3, 5, 30}
MAX_MOVES = 20000

_WORD_RE = re.compile(r"([A-Za-z])\s*([-+]?(?:\d+\.?\d*|\.\d+))")
_PAREN_RE = re.compile(r"\([^)]*\)")


class GCodeError(Exception):
    """The judge refuses to interpret this G-code (message names the cause)."""


# ---------------------------------------------------------------------------
# spec geometry
# ---------------------------------------------------------------------------

def geometry(spec):
    """Derived geometry dict from the machine-readable spec."""
    px, py = spec["pocket"]["center_xy_mm"]
    hx, hy = (s / 2.0 for s in spec["pocket"]["size_xy_mm"])
    icx, icy = spec["island"]["center_xy_mm"]
    r = spec["tool"]["diameter_mm"] / 2.0
    return {
        "px": px, "py": py, "hx": hx, "hy": hy,
        "depth": spec["pocket"]["depth_mm"],
        "cr": min(spec["pocket"]["corner_radius_mm"], hx, hy),
        "icx": icx, "icy": icy, "ir": spec["island"]["diameter_mm"] / 2.0,
        "r": r,
    }


def sdf_rounded_rect(X, Y, cx, cy, hx, hy, cr):
    """Signed distance to a rounded rectangle (<= 0 inside), exact."""
    cr = max(min(cr, hx, hy), 0.0)
    qx = np.maximum(np.abs(X - cx) - max(hx - cr, 0.0), 0.0)
    qy = np.maximum(np.abs(Y - cy) - max(hy - cr, 0.0), 0.0)
    return np.hypot(qx, qy) - cr


def oracle_heightmap(spec, xs, ys):
    """Analytic target heightmap + masks derived from the spec alone."""
    g = geometry(spec)
    X, Y = np.meshgrid(xs, ys)
    sdf_pocket = sdf_rounded_rect(X, Y, g["px"], g["py"], g["hx"], g["hy"], g["cr"])
    d_isl = np.hypot(X - g["icx"], Y - g["icy"])
    in_pocket = sdf_pocket <= 0.0
    in_island = d_isl <= g["ir"]
    target = np.where(in_pocket & ~in_island, -g["depth"], 0.0)
    # Cells no legal tool position can reach: farther than the tool radius
    # from the allowed-centre set (pocket inset by r, minus the disk of
    # radius ir + r around the island).  Empty whenever corner_radius >= r
    # and the island annulus is wider than the tool -- computed, not assumed.
    sdf_inset = sdf_rounded_rect(X, Y, g["px"], g["py"],
                                 g["hx"] - g["r"], g["hy"] - g["r"],
                                 g["cr"] - g["r"])
    dist_lb = np.maximum(sdf_inset, (g["ir"] + g["r"]) - d_isl)
    allowance = in_pocket & ~in_island & (dist_lb > g["r"])
    return {
        "target": target,
        "in_pocket": in_pocket,
        "in_island": in_island,
        "sdf_pocket": sdf_pocket,
        "d_island": d_isl,
        "must_clear": in_pocket & ~in_island & ~allowance,
        "allowance_cells": int(allowance.sum()),
    }


# ---------------------------------------------------------------------------
# G-code parsing
# ---------------------------------------------------------------------------

def scan_unit_words(text):
    """Lexical scan for unit-selection words, independent of full parsing.

    Returns (g20_lines, g21_line): the line numbers of every G20 and the line
    of the first G21.  Used by the `units` gate so an inch-mode program is
    failed by a *named gate* naming the offending line, even when the full
    parse refuses the program.
    """
    g20_lines = []
    g21_line = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = _PAREN_RE.sub(" ", raw.split(";", 1)[0]).strip()
        for letter, numtxt in _WORD_RE.findall(line):
            if letter.upper() != "G":
                continue
            gnum = int(round(float(numtxt)))
            if gnum == 20:
                g20_lines.append(lineno)
            elif gnum == 21 and g21_line is None:
                g21_line = lineno
    return g20_lines, g21_line


def parse_gcode(text, start_xy, safe_z):
    """Parse a G-code program into moves + program info.

    Returns (moves, info).  Raises GCodeError for anything outside the
    supported dialect (the message names the offending word).
    """
    pos = [float(start_xy[0]), float(start_xy[1]), float(safe_z)]
    motion = None           # modal motion mode: 0/1/2/3
    feed = None             # modal F (mm/min)
    spindle = None          # modal S (rpm)
    has_g17 = has_g21 = has_g90 = False
    m3_line = m5_line = None
    moves = []

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = _PAREN_RE.sub(" ", raw.split(";", 1)[0]).strip()
        if not line or line == "%":
            continue
        words = _WORD_RE.findall(line)
        if not words:
            continue

        line_motion = None
        axes = {}
        ijk = {}
        for letter, numtxt in words:
            letter = letter.upper()
            val = float(numtxt)
            if letter == "G":
                gnum = int(round(val))
                if gnum in (0, 1, 2, 3):
                    line_motion = gnum
                elif gnum == 17:
                    has_g17 = True
                elif gnum == 21:
                    has_g21 = True
                elif gnum == 90:
                    has_g90 = True
                elif gnum == 20:
                    raise GCodeError(
                        f"line {lineno}: G20 inch mode -- the job is specified "
                        f"in millimetres (G21)")
                elif gnum == 91:
                    raise GCodeError(
                        f"line {lineno}: G91 incremental distances are not "
                        f"supported; the program must be absolute (G90)")
                elif gnum in (18, 19):
                    raise GCodeError(
                        f"line {lineno}: G{gnum} plane selected -- only G17 "
                        f"(XY plane) is supported")
                else:
                    raise GCodeError(
                        f"line {lineno}: unsupported G-word G{gnum} (supported: "
                        f"G0 G1 G2 G3 G17 G21 G90)")
            elif letter == "M":
                mnum = int(round(val))
                if mnum not in SUPPORTED_M:
                    raise GCodeError(
                        f"line {lineno}: unsupported M-word M{mnum} "
                        f"(supported: M3 M5, optionally M2/M30)")
                if mnum == 3:
                    m3_line = lineno
                elif mnum == 5:
                    m5_line = lineno
            elif letter == "F":
                feed = val
            elif letter == "S":
                spindle = val
            elif letter in "XYZ":
                axes[letter] = val
            elif letter in "IJ":
                ijk[letter] = val
            elif letter == "N":
                pass
            else:
                raise GCodeError(
                    f"line {lineno}: unsupported word {letter}{numtxt}")

        if line_motion is not None:
            motion = line_motion
        if not axes and line_motion is None:
            continue
        if axes and motion is None:
            raise GCodeError(
                f"line {lineno}: axis words before any motion mode (G0/G1/G2/G3)")

        if motion is None:
            continue

        start = tuple(pos)
        end = [pos[0], pos[1], pos[2]]
        if "X" in axes:
            end[0] = axes["X"]
        if "Y" in axes:
            end[1] = axes["Y"]
        if "Z" in axes:
            end[2] = axes["Z"]

        mv = {
            "line": lineno,
            "kind": "rapid" if motion == 0 else "feed",
            "motion": "arc" if motion in (2, 3) else "line",
            "start": start,
            "end": tuple(end),
            "feed": feed,
            "spindle": spindle,
            "center": None,
            "radius": None,
            "a0": 0.0,
            "sweep": 0.0,
            "length": math.hypot(end[0] - start[0], end[1] - start[1]),
        }
        if motion in (2, 3):
            if "I" not in ijk and "J" not in ijk:
                raise GCodeError(
                    f"line {lineno}: arc without I/J centre offsets "
                    f"(R-form arcs are not supported)")
            cx = start[0] + ijk.get("I", 0.0)
            cy = start[1] + ijk.get("J", 0.0)
            radius = math.hypot(start[0] - cx, start[1] - cy)
            if radius <= 1e-9:
                raise GCodeError(f"line {lineno}: arc centre coincides with the start point")
            end_r = math.hypot(end[0] - cx, end[1] - cy)
            if abs(end_r - radius) > max(1e-3, 1e-3 * radius):
                raise GCodeError(
                    f"line {lineno}: arc endpoint is not on the centre's circle "
                    f"(start radius {radius:.6f}, end radius {end_r:.6f})")
            a0 = math.atan2(start[1] - cy, start[0] - cx)
            a1 = math.atan2(end[1] - cy, end[0] - cx)
            if motion == 3:                      # G3 = counter-clockwise
                sweep = (a1 - a0) % TWO_PI
                if sweep < 1e-12:
                    sweep = TWO_PI
            else:                                # G2 = clockwise
                sweep = -((a0 - a1) % TWO_PI)
                if sweep > -1e-12:
                    sweep = -TWO_PI
            mv["center"] = (cx, cy)
            mv["radius"] = radius
            mv["a0"] = a0
            mv["sweep"] = sweep
        moves.append(mv)
        pos = list(end)
        if len(moves) > MAX_MOVES:
            raise GCodeError(f"program exceeds {MAX_MOVES} moves")

    info = {
        "has_g17": has_g17, "has_g21": has_g21, "has_g90": has_g90,
        "m3_line": m3_line, "m5_line": m5_line,
        "n_moves": len(moves),
    }
    return moves, info


# ---------------------------------------------------------------------------
# path sampling
# ---------------------------------------------------------------------------

def path_points(mv, step_mm=0.25, min_points=2):
    """Sample the XY path of a move.  Returns an (N, 2) float array."""
    x0, y0 = mv["start"][0], mv["start"][1]
    x1, y1 = mv["end"][0], mv["end"][1]
    if mv["motion"] == "line":
        n = max(min_points, int(math.ceil(mv["length"] / step_mm)) + 1)
        t = np.linspace(0.0, 1.0, n)
        return np.stack([x0 + (x1 - x0) * t, y0 + (y1 - y0) * t], axis=1)
    cx, cy = mv["center"]
    sweep = mv["sweep"]
    n = max(min_points, int(math.ceil(abs(sweep) * mv["radius"] / step_mm)) + 1)
    ang = mv["a0"] + sweep * np.linspace(0.0, 1.0, n)
    return np.stack([cx + mv["radius"] * np.cos(ang),
                     cy + mv["radius"] * np.sin(ang)], axis=1)


def path_bbox(mv, pad):
    """Exact XY bounding box of a move's path, padded by `pad`."""
    xs = [mv["start"][0], mv["end"][0]]
    ys = [mv["start"][1], mv["end"][1]]
    if mv["motion"] == "arc":
        cx, cy = mv["center"]
        r = mv["radius"]
        for k in range(4):                       # cardinal extremes
            ang = mv["a0"] + mv["sweep"] * (k / 4.0)
            # test whether the cardinal angle lies within the sweep
            card = (0.0, math.pi / 2, math.pi, -math.pi / 2)[k]
            if mv["sweep"] > 0:
                inside = ((card - mv["a0"]) % TWO_PI) <= mv["sweep"]
            else:
                inside = ((mv["a0"] - card) % TWO_PI) <= -mv["sweep"]
            if inside:
                xs.append(cx + r * math.cos(card))
                ys.append(cy + r * math.sin(card))
    return (min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad)


# ---------------------------------------------------------------------------
# simulator
# ---------------------------------------------------------------------------

class Simulator:
    """Flat-endmill material removal on a heightmap grid."""

    def __init__(self, spec, domain=None):
        g = spec["grid_mm"]
        if domain is None:
            domain = ((0.0, spec["stock"]["x_mm"]),
                      (0.0, spec["stock"]["y_mm"]))
        (x0, x1), (y0, y1) = domain
        self.g = float(g)
        self.x0, self.y0 = x0, y0
        self.nx = int(round((x1 - x0) / g))
        self.ny = int(round((y1 - y0) / g))
        self.xs = (np.arange(self.nx) + 0.5) * g + x0
        self.ys = (np.arange(self.ny) + 0.5) * g + y0
        self.H = np.zeros((self.ny, self.nx), dtype=np.float64)
        self.tool_r = spec["tool"]["diameter_mm"] / 2.0
        self.safe_z = spec["machine"]["safe_z_mm"]
        self.r_eff = self.tool_r + 1e-9

    # -- footprint distances -------------------------------------------------

    def _dist_to_path(self, xb, yb, mv):
        """Distance from broadcast coordinate arrays to the move's XY path."""
        x0, y0 = mv["start"][0], mv["start"][1]
        x1, y1 = mv["end"][0], mv["end"][1]
        if mv["motion"] == "line":
            dx, dy = x1 - x0, y1 - y0
            l2 = dx * dx + dy * dy
            if l2 <= 1e-24:
                return np.hypot(xb - x0, yb - y0)
            t = ((xb - x0) * dx + (yb - y0) * dy) / l2
            np.clip(t, 0.0, 1.0, out=t)
            return np.hypot(xb - (x0 + t * dx), yb - (y0 + t * dy))
        cx, cy = mv["center"]
        vx, vy = xb - cx, yb - cy
        ang = np.arctan2(vy, vx)
        a0, sweep = mv["a0"], mv["sweep"]
        if sweep > 0:
            inside = ((ang - a0) % TWO_PI) <= sweep
        else:
            inside = ((a0 - ang) % TWO_PI) <= -sweep
        radial = np.abs(np.hypot(vx, vy) - mv["radius"])
        d_start = np.hypot(xb - x0, yb - y0)
        d_end = np.hypot(xb - x1, yb - y1)
        return np.where(inside, radial, np.minimum(d_start, d_end))

    def _slices(self, bbox):
        xmin, xmax, ymin, ymax = bbox
        i0 = max(0, int(math.ceil((xmin - self.x0) / self.g - 0.5)))
        i1 = min(self.nx, int(math.floor((xmax - self.x0) / self.g - 0.5)) + 1)
        j0 = max(0, int(math.ceil((ymin - self.y0) / self.g - 0.5)))
        j1 = min(self.ny, int(math.floor((ymax - self.y0) / self.g - 0.5)) + 1)
        if i1 <= i0 or j1 <= j0:
            return None
        return i0, i1, j0, j1

    # -- main loop -----------------------------------------------------------

    def run(self, moves):
        """Simulate every move in order; return one record per move."""
        records = []
        levels = {}                       # z level -> earlier centreline samples
        for mv in moves:
            z_end = mv["end"][2]
            sl = self._slices(path_bbox(mv, self.tool_r))
            rec = {
                "line": mv["line"], "kind": mv["kind"], "motion": mv["motion"],
                "z_end": z_end, "feed": mv["feed"], "spindle": mv["spindle"],
                "cut_cells": 0, "axial_mm": 0.0, "rapid_hit_mm": 0.0,
                "spacing_mm": None,
            }
            if sl is not None:
                i0, i1, j0, j1 = sl
                xb = self.xs[i0:i1][None, :]
                yb = self.ys[j0:j1][:, None]
                sub = self.H[j0:j1, i0:i1]
                dist = self._dist_to_path(xb, yb, mv)
                mask = dist <= self.r_eff
                above = mask & (sub > z_end)
                rec["cut_cells"] = int(above.sum())
                if above.any():
                    if mv["kind"] == "feed":
                        rec["axial_mm"] = float((sub - z_end)[above].max())
                    else:
                        rec["rapid_hit_mm"] = float((sub - z_end)[above].max())
                    sub[above] = z_end
            records.append(rec)

            # pass-spacing: distance from this pass's centreline to the
            # nearest earlier lateral feed centreline at the same Z level
            if mv["kind"] == "feed" and mv["length"] > 1e-9:
                pts = path_points(mv, step_mm=0.25)
                lvl = round(z_end, 9)
                earlier = levels.get(lvl)
                if earlier is None:
                    levels[lvl] = pts              # exempt: first pass at level
                else:
                    d2 = ((pts[:, None, 0] - earlier[None, :, 0]) ** 2
                          + (pts[:, None, 1] - earlier[None, :, 1]) ** 2)
                    rec["spacing_mm"] = float(math.sqrt(d2.min()))
                    levels[lvl] = np.vstack([earlier, pts])
        return records
