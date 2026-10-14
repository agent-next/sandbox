#!/usr/bin/env python3
"""2.5D CAM for the cnc-gcode job: rectangular pocket with a round island.

Reads the job spec (spec.json) and writes an RS274/NGC program (part.nc) that
machines the pocket with a flat end mill.  Standard library only.

Strategy, per Z level (stepdown taken from the spec limits):
  1. raster clearing, boustrophedon, each line clipped to the allowed
     tool-centre region (pocket inset by the tool radius, corner radius
     reduced by the tool radius, and kept 2 tool radii clear of the island so
     the island contour pass that follows finishes that band);
  2. the island contour: two half-circles at island radius + tool radius;
  3. the wall contour: the inset rounded rectangle (4 lines + 4 corner arcs),
     which finishes the walls and the corner fillets.

The tool-radius offset is applied here (no G41/G42 cutter compensation);
rapid moves only ever happen at the safe Z, entries plunge at plunge feed.
"""
import argparse
import json
import math

# --- process parameters (this script's own choices, within the spec limits) --
TOOL_OFFSET_SCALE = 1.0     # cutter-radius offset applied to the toolpath
STEPDOWN_MM = 2.0           # axial engagement per pass  (spec limit: 2.0 mm)
STEPOVER_MM = 2.5           # pass spacing               (spec limit: 3.0 mm)
CUT_FEED_MM_MIN = 1600.0    # 0.100 mm/tooth at 8000 rpm, 2 flutes
PLUNGE_FEED_MM_MIN = 400.0  # 0.025 mm/tooth
FEED_SCALE = 1.0
UNITS_WORD = "G21"          # millimetres
PLUNGE_WORD = "G1"          # plunges cut at plunge feed, never rapid
ISLAND_ARC_A = "G3"         # first half-circle of the island contour
ISLAND_ARC_B = "G3"         # second half-circle: same direction as the first


def _seg_point_dist(x0, y0, x1, y1, px, py):
    """Distance from point (px, py) to the segment (x0,y0)-(x1,y1)."""
    dx, dy = x1 - x0, y1 - y0
    l2 = dx * dx + dy * dy
    if l2 <= 1e-24:
        return math.hypot(px - x0, py - y0)
    t = ((px - x0) * dx + (py - y0) * dy) / l2
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))


class Cam:
    def __init__(self, spec):
        pocket = spec["pocket"]
        self.px, self.py = pocket["center_xy_mm"]
        self.hx, self.hy = (v / 2.0 for v in pocket["size_xy_mm"])
        self.depth = pocket["depth_mm"]
        self.corner_r = pocket["corner_radius_mm"]
        self.icx, self.icy = spec["island"]["center_xy_mm"]
        self.ir = spec["island"]["diameter_mm"] / 2.0
        self.rpm = spec["limits"]["spindle_rpm"]
        self.safe_z = spec["machine"]["safe_z_mm"]
        # the radius this script offsets its paths by (the tool radius)
        self.r = spec["tool"]["diameter_mm"] / 2.0 * TOOL_OFFSET_SCALE
        self.rc = max(self.corner_r - self.r, 0.0)      # inset corner radius
        self.lines = []
        self.x = self.y = None
        self.z = self.safe_z

    # -- emission ---------------------------------------------------------

    def emit(self, text):
        self.lines.append(text)

    def rapid_to(self, x, y):
        if self.z < self.safe_z - 1e-9:
            self.emit(f"G0 Z{self.safe_z:.3f}")
            self.z = self.safe_z
        self.emit(f"G0 X{x:.3f} Y{y:.3f}")
        self.x, self.y = x, y

    def plunge_to(self, z):
        self.emit(f"{PLUNGE_WORD} Z{z:.3f} F{PLUNGE_FEED_MM_MIN * FEED_SCALE:.0f}")
        self.z = z

    def cut_to(self, x, y):
        self.emit(f"G1 X{x:.3f} Y{y:.3f} F{CUT_FEED_MM_MIN * FEED_SCALE:.0f}")
        self.x, self.y = x, y

    def arc_to(self, word, x, y, cx, cy):
        self.emit(f"{word} X{x:.3f} Y{y:.3f} I{cx - self.x:.3f} "
                  f"J{cy - self.y:.3f} F{CUT_FEED_MM_MIN * FEED_SCALE:.0f}")
        self.x, self.y = x, y

    def link_ok(self, x0, y0, x1, y1):
        """Is a straight cutting link between two pass endpoints safe?

        The inset rounded rectangle is convex and both endpoints lie inside
        it, so the link cannot leave the pocket; only the island needs an
        explicit clearance test.
        """
        return _seg_point_dist(x0, y0, x1, y1, self.icx, self.icy) \
            >= self.ir + self.r - 1e-6

    def begin_pass(self, x, y, z):
        """Get to (x, y, z) ready to cut: direct link, or retract-rapid-plunge."""
        if (self.x is not None and abs(self.z - z) < 1e-9
                and math.hypot(self.x - x, self.y - y) < 1e-9):
            return
        if (self.x is not None and abs(self.z - z) < 1e-9
                and self.link_ok(self.x, self.y, x, y)):
            self.cut_to(x, y)
        else:
            self.rapid_to(x, y)
            self.plunge_to(z)

    # -- toolpath regions ---------------------------------------------------

    def rr_halfwidth(self, y):
        """Half-width of the inset rounded rectangle's cross-section at y."""
        core_hx = self.hx - self.r - self.rc
        core_hy = self.hy - self.r - self.rc
        beyond = abs(y - self.py) - core_hy
        if beyond <= 0.0:
            return self.hx - self.r
        return core_hx + math.sqrt(max(0.0, self.rc * self.rc - beyond * beyond))

    def raster_passes(self):
        """Boustrophedon raster segments clipped to the allowed-centre region."""
        clip_k = self.ir + 2.0 * self.r        # stay out of the island band
        y_lo = self.py - (self.hy - self.r)
        y_hi = self.py + (self.hy - self.r)
        ys = []
        k = 0
        while y_lo + k * STEPOVER_MM <= y_hi + 1e-9:
            ys.append(y_lo + k * STEPOVER_MM)
            k += 1
        if ys[-1] < y_hi - 1e-9:
            ys.append(y_hi)
        segments = []
        flip = False
        for y in ys:
            hw = self.rr_halfwidth(y)
            spans = [(self.px - hw, self.px + hw)]
            dy = abs(y - self.icy)
            if dy < clip_k - 1e-9:
                gap = math.sqrt(clip_k * clip_k - dy * dy)
                spans = [(self.px - hw, self.icx - gap),
                         (self.icx + gap, self.px + hw)]
            spans = [(a, b) for a, b in spans if b - a > 1e-6]
            if flip:
                spans = spans[::-1]
            for a, b in spans:
                if flip:
                    a, b = b, a
                segments.append(((a, y), (b, y)))
            flip = not flip
        return segments

    def wall_contour(self):
        """The inset rounded rectangle as a CCW sequence of lines and arcs."""
        x0 = self.px - (self.hx - self.r)
        x1 = self.px + (self.hx - self.r)
        y0 = self.py - (self.hy - self.r)
        y1 = self.py + (self.hy - self.r)
        rc = self.rc
        corners = [(x0 + rc, y0 + rc), (x1 - rc, y0 + rc),
                   (x1 - rc, y1 - rc), (x0 + rc, y1 - rc)]
        if rc <= 1e-9:
            return [("line", p) for p in
                    [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, self.py)]]
        return [
            ("line", (x0, y0 + rc)),
            ("arc", ((x0 + rc, y0), corners[0])),
            ("line", (x1 - rc, y0)),
            ("arc", ((x1, y0 + rc), corners[1])),
            ("line", (x1, y1 - rc)),
            ("arc", ((x1 - rc, y1), corners[2])),
            ("line", (x0 + rc, y1)),
            ("arc", ((x0, y1 - rc), corners[3])),
            ("line", (x0, self.py)),
        ]

    # -- levels --------------------------------------------------------------

    def levels(self):
        out = []
        k = 1
        while k * STEPDOWN_MM < self.depth - 1e-9:
            out.append(-k * STEPDOWN_MM)
            k += 1
        out.append(-self.depth)
        return out

    def cut_level(self, z):
        for (a, b) in self.raster_passes():
            self.begin_pass(a[0], a[1], z)
            self.cut_to(b[0], b[1])

        # island contour: two half-circles, both the same direction
        R = self.ir + self.r
        west = (self.icx - R, self.icy)
        east = (self.icx + R, self.icy)
        self.begin_pass(west[0], west[1], z)
        self.arc_to(ISLAND_ARC_A, east[0], east[1], self.icx, self.icy)
        self.arc_to(ISLAND_ARC_B, west[0], west[1], self.icx, self.icy)

        # wall contour: starts at the west mid-point of the inset rectangle
        x0 = self.px - (self.hx - self.r)
        self.begin_pass(x0, self.py, z)
        for move in self.wall_contour():
            if move[0] == "line":
                x, y = move[1]
                self.cut_to(x, y)
            else:
                (x, y), (cx, cy) = move[1]
                self.arc_to("G3", x, y, cx, cy)

    # -- program ---------------------------------------------------------------

    def program(self, spec):
        self.emit(f"(part: pocket {spec['pocket']['size_xy_mm'][0]:.0f}x"
                  f"{spec['pocket']['size_xy_mm'][1]:.0f}x"
                  f"{spec['pocket']['depth_mm']:.0f} mm with round island, "
                  f"{spec['material']})")
        self.emit(f"(tool: D{spec['tool']['diameter_mm']:.1f} mm "
                  f"{spec['tool']['flutes']}-flute {spec['tool']['type']}, "
                  f"stepdown {STEPDOWN_MM:.1f} mm, stepover {STEPOVER_MM:.1f} mm)")
        self.emit(f"G17 {UNITS_WORD} G90")
        self.emit(f"S{self.rpm:.0f} M3")
        for z in self.levels():
            self.emit(f"(level Z{z:.3f})")
            self.cut_level(z)
        self.emit(f"G0 Z{self.safe_z:.3f}")
        self.emit("G0 X0 Y0")
        self.emit("M5")
        return "\n".join(self.lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", default="spec.json")
    ap.add_argument("--out", default="part.nc")
    args = ap.parse_args()
    with open(args.spec, "r", encoding="utf-8") as fh:
        spec = json.load(fh)
    cam = Cam(spec)
    text = cam.program(spec)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"cam: wrote {args.out} ({len(cam.lines)} lines, "
          f"{len(cam.levels())} levels)")


if __name__ == "__main__":
    main()
