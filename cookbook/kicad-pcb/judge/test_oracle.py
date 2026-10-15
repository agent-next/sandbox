#!/usr/bin/env python3
"""Unit tests for judge/oracle.py — one regression test per review
finding, on in-memory fixtures.  Run by selftest.sh and directly with

    python3 -m unittest judge/test_oracle.py

The grade.sh test needs kicad-cli (judge/setup.sh); it is skipped when
the tool is not installed.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
GOOD = os.path.join(DEMO, "examples", "good", "555-blinker")
sys.path.insert(0, HERE)
import oracle                          # noqa: E402

DRC_OK = {"violations": [], "unconnected_items": []}

# Minimal valid project: U1 (NE555), R3, D1 — the assigned parts —
# with the schematic wiring pin 2 of the LED to net LED and pin 1 to
# GND, exactly what the real 555-blinker netlist says.
SCH_XML = """<?xml version="1.0"?>
<export version="E"><components>
<comp ref="U1"><libsource lib="Timer" part="NE555D"/></comp>
<comp ref="D1"><libsource lib="Device" part="LED"/></comp>
<comp ref="R3"><libsource lib="Device" part="R"/></comp>
</components><nets>
<net code="1" name="/LED"><node ref="D1" pin="2"/><node ref="R3" pin="2"/></net>
<net code="2" name="GND"><node ref="D1" pin="1"/><node ref="U1" pin="1"/></net>
</nets></export>"""

PCB_TMPL = """(kicad_pcb
 (net 0 "") (net 1 "{led}") (net 2 "GND")
 (footprint "SOIC" (property "Reference" "U1" "x")
   (pad "1" smd rect (net 2 "GND")))
 (footprint "LED_0805" (property "Reference" "D1" "x")
   (pad "{k}" smd rect (net {knet}))
   (pad "{a}" smd rect (net {anet})))
 (footprint "R_0805" (property "Reference" "R3" "x")
   (pad "2" smd rect (net 1 "{led}"))))
"""

# cathode on pad 1, anode on pad 2 — what the schematic says
PCB_CORRECT = PCB_TMPL.format(led="/LED", k="1", a="2",
                              knet='2 "GND"', anet='1 "/LED"')
# LED soldered backwards: pad 1 on LED, pad 2 on GND
PCB_REVERSED = PCB_TMPL.format(led="LED", k="1", a="2",
                               knet='1 "LED"', anet='2 "GND"')


def write(d, name, text):
    p = os.path.join(d, name)
    with open(p, "w") as f:
        f.write(text)
    return p


def fixture(d, pcb=PCB_CORRECT, sch=SCH_XML):
    return (write(d, "s.xml", sch), write(d, "b.kicad_pcb", pcb),
            write(d, "d.json", json.dumps(DRC_OK)))


class G3Netlist(unittest.TestCase):
    """Findings 1 & 2: G3 must compare (ref, pin) membership on
    normalized net names, not just the set of net-name strings."""

    def test_hierarchical_names_match(self):
        # sch "/LED" vs pcb "/LED" — a normal sch->PCB update result —
        # must pass; the old code compared "LED" against "/LED".
        with tempfile.TemporaryDirectory() as d:
            ok, det = oracle.gate_netlist(*fixture(d))
        self.assertTrue(ok, det)

    def test_reversed_led_fails(self):
        # Right net names, wrong pads: D1 pad1 on LED, pad2 on GND.
        with tempfile.TemporaryDirectory() as d:
            ok, det = oracle.gate_netlist(*fixture(d, pcb=PCB_REVERSED))
        self.assertFalse(ok)
        self.assertIn("LED", det.get("member_mismatch", {}))


class G4Outline(unittest.TestCase):
    """Finding 5: a gr_poly is an inherently closed shape; its first
    and last vertices are not open endpoints."""

    POLY = ('(kicad_pcb (gr_poly (pts (xy 100 100) (xy 140 100) '
            '(xy 140 130) (xy 100 130)) (layer "Edge.Cuts") '
            '(width 0.05)))')

    def test_closed_poly_passes(self):
        with tempfile.TemporaryDirectory() as d:
            ok, det = oracle.gate_outline(write(d, "b.kicad_pcb",
                                                self.POLY))
        self.assertTrue(ok, det)
        self.assertEqual(det.get("open_endpoints"), 0)


class G5Gerber(unittest.TestCase):
    """Finding 6: only D01 draws and D03 flashes are geometry; a D02
    pen-up move draws nothing."""

    def test_d02_only_is_not_geometry(self):
        g = ("%FSLAX46Y46*%\n%MOMM*%\n%ADD10C,0.1*%\nD10*\n"
             "X100000Y100000D02*\nX200000Y200000D02*\nM02*\n")
        with tempfile.TemporaryDirectory() as d:
            ap, ops = oracle.parse_gerber(write(d, "e.gm1", g))
        self.assertEqual((ap, ops), (1, 0))

    def test_modal_d01_counts(self):
        g = ("%FSLAX46Y46*%\n%MOMM*%\n%ADD10C,0.1*%\nD10*\n"
             "X100000Y100000D02*\nX200000Y200000D01*\n"
             "X300000Y200000*\nX400000Y200000*\nM02*\n")
        with tempfile.TemporaryDirectory() as d:
            ap, ops = oracle.parse_gerber(write(d, "e.gm1", g))
        # one explicit D01 draw + two modal continuations; the D02
        # pen-up move is not geometry
        self.assertEqual(ops, 3)


class G6Drill(unittest.TestCase):
    """Finding 7: a G85 canned slot cycle is a drill hit."""

    DRL = ("M48\n; slots\nMETRIC\nT1C1.0\n%\nG90\nG05\nT1\n"
           "G00X100.0Y50.0\nG85X110.0Y50.0\nM30\n")
    PCB = ('(kicad_pcb (footprint "F" (property "Reference" "U1" "x")'
           ' (pad "1" thru_hole oval (at 0 0) (size 2 1)'
           ' (drill oval 1.0 2.0) (net 1 "N"))))')

    def test_g85_slot_counts_as_hit(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "x.drl", self.DRL)
            ok, det = oracle.gate_drill(d, write(d, "b.kicad_pcb",
                                                 self.PCB))
        self.assertTrue(ok, det)
        self.assertEqual(det["drill_hits"], 1)

    def test_horizontal_slot_needs_short_axis_tool(self):
        pcb = self.PCB.replace("(drill oval 1.0 2.0)", "(drill oval 2.0 1.0)")
        with tempfile.TemporaryDirectory() as d:
            write(d, "x.drl", self.DRL)
            ok, det = oracle.gate_drill(d, write(d, "b.kicad_pcb", pcb))
        self.assertTrue(ok, det)
        self.assertEqual(det["missing_tool_mm"], [])


class G7Limits(unittest.TestCase):
    """Finding 4: the limits SPEC.md publishes are real pass rules."""

    RECT = ('(kicad_pcb (gr_line (start 100 100) (end {x} 100) '
            '(stroke (width 0.05) (type default)) (layer "Edge.Cuts"))'
            '(gr_line (start {x} 100) (end {x} 130) '
            '(stroke (width 0.05) (type default)) (layer "Edge.Cuts"))'
            '(gr_line (start {x} 130) (end 100 130) '
            '(stroke (width 0.05) (type default)) (layer "Edge.Cuts"))'
            '(gr_line (start 100 130) (end 100 100) '
            '(stroke (width 0.05) (type default)) (layer "Edge.Cuts")))')
    PRO = {"net_settings": {"classes": [
        {"name": "Default", "clearance": 0.2, "track_width": 0.25,
         "via_drill": 0.4}]}}

    def limits(self, d, pcb_text, pro):
        return oracle.gate_limits(write(d, "b.kicad_pcb", pcb_text),
                                  write(d, "p.kicad_pro",
                                        json.dumps(pro)))

    def test_within_limits_passes(self):
        with tempfile.TemporaryDirectory() as d:
            ok, det = self.limits(d, self.RECT.format(x=140), self.PRO)
        self.assertTrue(ok, det)

    def test_oversize_board_fails(self):
        with tempfile.TemporaryDirectory() as d:
            ok, det = self.limits(d, self.RECT.format(x=200), self.PRO)
        self.assertFalse(ok)
        self.assertFalse(det["board_size_ok"])

    def test_thin_track_fails(self):
        seg = (' (segment (start 110 110) (end 120 110) (width {w})'
               ' (layer "F.Cu") (net 1))')
        with tempfile.TemporaryDirectory() as d:
            ok, _ = self.limits(d, self.RECT.format(x=140)[:-1]
                                + seg.format(w=0.25) + ")", self.PRO)
            bad, det = self.limits(d, self.RECT.format(x=140)[:-1]
                                   + seg.format(w=0.10) + ")", self.PRO)
        self.assertTrue(ok)
        self.assertFalse(bad)
        self.assertFalse(det["track_width_ok"])
        self.assertEqual(det["min_track_width_mm"], 0.10)

    def test_weak_netclass_fails(self):
        pro = json.loads(json.dumps(self.PRO))
        pro["net_settings"]["classes"][0]["track_width"] = 0.1
        with tempfile.TemporaryDirectory() as d:
            ok, det = self.limits(d, self.RECT.format(x=140), pro)
        self.assertFalse(ok)
        self.assertIn("Default", det.get("netclass_violations", {}))


class PinnedRules(unittest.TestCase):
    """Finding 3: the judge, not the artifact, owns rule severities."""

    def test_pin_design_rules_resets_artifact_overrides(self):
        pro = {"board": {"design_settings": {
                   "rule_severities": {"shorting_items": "ignore",
                                       "clearance": "ignore"},
                   "drc_exclusions": [{"type": "shorting_items"}]}},
               "erc": {"rule_severities": {"pin_to_pin": "ignore"}}}
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "p.kicad_pro", json.dumps(pro))
            oracle.pin_design_rules(p)
            out = json.load(open(p))
        ds = out["board"]["design_settings"]
        self.assertEqual(ds["rule_severities"],
                         oracle.PINNED_DRC_SEVERITIES)
        self.assertEqual(ds["drc_exclusions"], [])
        self.assertNotIn("erc", out)


def kicad_cli():
    cli = (os.environ.get("KICAD_CLI") or shutil.which("kicad-cli")
           or os.path.expanduser("~/.local/kicad-pcb-demo/bin/kicad-cli"))
    if shutil.which(cli) or os.path.exists(cli):
        return cli
    return None


@unittest.skipUnless(kicad_cli() and os.path.isdir(GOOD),
                     "needs kicad-cli (judge/setup.sh) and the good "
                     "example")
class VerdictWrite(unittest.TestCase):
    """Finding 8: grade.sh must exit non-zero when the requested
    verdict JSON cannot be written."""

    def test_unwritable_verdict_fails(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "nonexistent", "v.json")
            rc = subprocess.run(
                ["bash", os.path.join(HERE, "grade.sh"), GOOD,
                 "--json", bad],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL).returncode
            self.assertNotEqual(rc, 0)
            self.assertFalse(os.path.exists(bad))


if __name__ == "__main__":
    unittest.main()
