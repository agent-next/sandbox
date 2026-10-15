"""Stdlib unit tests for the judge's pure functions (no SolidCraft, no OCCT).

    python3 -m unittest discover -s cookbook/solidcraft-cad/tests
"""

from __future__ import annotations

import json
import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "judge"))
import solidcraft_judge as J  # noqa: E402


def write_stl(tris) -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".stl", delete=False)
    f.write(b"\0" * 80 + struct.pack("<I", len(tris)))
    for t in tris:
        f.write(struct.pack("<3f", 0, 0, 0) + struct.pack("<9f", *[c for p in t for c in p]) + b"\0\0")
    f.close()
    return Path(f.name)


def tetra(s: float, sign: float = 1.0):
    o, a, b, c = (0, 0, 0), (sign * s, 0, 0), (0, sign * s, 0), (0, 0, sign * s)
    tris = [(o, b, a), (o, a, c), (o, c, b), (a, b, c)]  # outward for sign = +1
    return tris if sign > 0 else [(p, r, q) for p, q, r in tris]


class FitCircle(unittest.TestCase):
    def test_short_arc_off_origin_fits_its_true_centre(self):
        # 5 points of an exact 1.25 deg arc of an R5 corner centred at (25, 20)
        # (a sliver left when SolidCraft splits a corner face)
        a = math.radians(1.25)
        pts = [(25 + 5 * math.cos(a * k / 4), 20 + 5 * math.sin(a * k / 4)) for k in range(5)] * 5
        x, y, r = J.fit_circle(pts)
        self.assertAlmostEqual(x, 25, delta=1e-6, msg="fitted centre x")
        self.assertAlmostEqual(y, 20, delta=1e-6, msg="fitted centre y")
        self.assertAlmostEqual(r, 5, delta=1e-6, msg="fitted radius")


class StlCheck(unittest.TestCase):
    def test_closed_tetrahedron_is_manifold(self):
        stl = write_stl(tetra(10))
        r = J.stl_check(stl)
        self.assertEqual(r["bad_edges"], 0)
        self.assertEqual(r.get("bad_vertices", 0), 0)
        self.assertAlmostEqual(r["volume"], 1000 / 6, places=3)
        stl.unlink()

    def test_two_tetrahedra_touching_at_one_vertex_are_not_a_manifold(self):
        stl = write_stl(tetra(10) + tetra(10, -1))
        r = J.stl_check(stl)
        stl.unlink()
        self.assertGreater(r["bad_edges"] + r.get("bad_vertices", 0), 0,
                           "a vertex shared by two closed shells passed the 2-manifold check")


SPEC = json.loads((Path(__file__).resolve().parent.parent / "spec.json").read_text())


def part(spec=SPEC, turn_deg=0.0, web=None, bulge=None):
    """A measured part as occt_measure() reports it, with a classifier for an
    ideal plate built from the same cylinders; `web` = (z0, z1) fills every
    bolt hole over that height; `bulge` = (amplitude, lobes) makes the bore
    wall r = R + a*sin(lobes*theta)^2 while its faces still read as R."""
    p, T, H = spec["plate"], spec["plate"]["thickness"], spec["boss"]["height"]
    hx, hy, r = p["length"] / 2, p["width"] / 2, p["corner_radius"]
    a = math.radians(turn_deg)
    bolts = [(x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)) for x, y in J.hole_centres(spec)]
    br, hr, Rb = spec["bore"]["diameter"] / 2, spec["bolt_holes"]["diameter"] / 2, spec["boss"]["outer_diameter"] / 2
    cyl = [{"x": 0, "y": 0, "r": br, "concave": True, "z0": 0, "z1": T + H},
           {"x": 0, "y": 0, "r": Rb, "concave": False, "z0": T, "z1": T + H}]
    cyl += [{"x": x, "y": y, "r": hr, "concave": True, "z0": 0, "z1": T} for x, y in bolts]
    cyl += [{"x": sx * (hx - r), "y": sy * (hy - r), "r": r, "concave": False, "z0": 0, "z1": T}
            for sx in (1, -1) for sy in (1, -1)]

    def material(x, y, z):
        rho = math.hypot(x, y)
        rb = br if bulge is None else br + bulge[0] * math.sin(bulge[1] * math.atan2(y, x)) ** 2
        if T < z < T + H:
            return rb < rho < Rb
        if not 0 < z < T or rho < rb:
            return False
        if any(math.hypot(x - bx, y - by) < hr for bx, by in bolts):
            return web is not None and web[0] < z < web[1]
        ax, ay = abs(x), abs(y)
        if ax > hx - r and ay > hy - r:
            return math.hypot(ax - (hx - r), ay - (hy - r)) < r
        return ax < hx and ay < hy
    def material_fraction(x, y, r0, r1, z0, z1, a0=0.0, a1=360.0, nr=3, na=180, nz=100):
        pts = [(x + (r0 + (r1 - r0) * (i + 0.5) / nr) * math.cos(math.radians(a0 + (a1 - a0) * (j + 0.5) / na)),
                y + (r0 + (r1 - r0) * (i + 0.5) / nr) * math.sin(math.radians(a0 + (a1 - a0) * (j + 0.5) / na)),
                z0 + (z1 - z0) * (k + 0.5) / nz) for i in range(nr) for j in range(na) for k in range(nz)]
        return sum(map(lambda q: material(*q), pts)) / len(pts)
    return {"cylinders": cyl, "material_fraction": material_fraction}


class Features(unittest.TestCase):
    def test_ideal_part_passes(self):
        ok, info = J.features(part(), SPEC)
        self.assertTrue(ok, info["problems"])
        self.assertEqual(info["wall_checks_failed"], 0)
        self.assertEqual(info["wall_checks"], 20)

    def test_whole_bolt_pattern_turned_10_deg_fails(self):
        ok, info = J.features(part(turn_deg=10), SPEC)
        self.assertFalse(ok, "a bolt pattern turned off its nominal 45 deg phase passed")
        self.assertIn("nominal positions", " ".join(info["problems"]))

    def test_web_inside_the_bolt_holes_fails(self):
        ok, info = J.features(part(web=(3, 3.5)), SPEC)
        self.assertFalse(ok, "bolt holes blocked by a 0.5 mm web passed")
        self.assertIn("bolt hole", " ".join(info["problems"]))


    def test_thin_web_between_probe_levels_fails(self):
        for t in (6, 8):
            spec = json.loads(json.dumps(SPEC))
            spec["plate"]["thickness"] = t
            ok, _ = J.features(part(spec, web=(3.1, 3.2)), spec)
            self.assertFalse(ok, f"bolt holes blocked by a 0.1 mm web at z 3.1..3.2 passed (T={t})")

    def test_bore_bulging_between_samples_fails(self):
        ok, _ = J.features(part(bulge=(0.05, 36)), SPEC)
        self.assertFalse(ok, "a bore reaching 22.1 mm between the sampled angles passed")


class CheckCommands(unittest.TestCase):
    def text(self, font):
        return {"commands": [{"command": "sketch.create", "params": {"plane": "XY"}},
                             {"command": "sketch.text", "params": {"text": "X", "at": [0, 0], "font": font}},
                             {"command": "sketch.finish", "params": {}}]}

    def test_font_file_outside_the_work_dir_is_refused(self):
        for font in ("/tmp/outside.ttf", "~/fonts/a.otf", "%APPDATA%\\a.ttf", "../a.ttf"):
            self.assertIsNotNone(J.check_commands(self.text(font)), f"font file {font!r} accepted")

    def test_installed_font_family_is_allowed(self):
        self.assertIsNone(J.check_commands(self.text("DejaVu Sans")))

    def test_nested_command_is_checked_too(self):
        d = {"commands": [{"command": "timeline.redefine", "params": {
            "feature": "Extrude1", "commands": [{"command": "file.export", "params": {"path": "/tmp/x.step"}}]}}]}
        self.assertIsNotNone(J.check_commands(d), "a file command nested in timeline params was accepted")

    def nested(self, depth):
        d = {"command": "solid.box", "params": {}}
        for _ in range(depth):
            d = {"command": "timeline.redefine", "params": {"commands": [d]}}
        return {"commands": [d]}

    def test_nested_commands_are_walked_once(self):
        import time
        t0 = time.monotonic()
        J.check_commands(self.nested(24))
        self.assertLess(time.monotonic() - t0, 0.5, "nested commands are re-walked at every level")

    def test_deep_nesting_is_a_rejection_not_a_crash(self):
        try:
            err = J.check_commands(self.nested(300))
        except RecursionError:
            self.fail("deeply nested params crashed the command check")
        self.assertIsNotNone(err, "300 nested commands accepted")


if __name__ == "__main__":
    unittest.main()
