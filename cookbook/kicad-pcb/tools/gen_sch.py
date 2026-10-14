#!/usr/bin/env python3
"""Generate 555-blinker.kicad_sch (KiCad 9 format, version 20230121).

Run with any python3 (stdlib only):
    python3 tools/gen_sch.py <symbol-lib-dir> <out-dir>

All used symbols are embedded verbatim from the stock KiCad symbol
libraries into (lib_symbols ...), so the schematic is self-contained.

Circuit: classic 555 astable.
    VCC -> R1 -> DIS(pin7) -> R2 -> TRIG/THR(pins 2,6) -> C1 -> GND
    pin5 CONT -> C2 -> GND ; pin4 RST -> VCC ; pin3 OUT -> R3 -> LED -> GND
    J1 = 2-pin power connector (pin1 VCC, pin2 GND)

Pin->pad mapping matches 555-blinker.kicad_pcb:
    U1: 1 GND 2 TRIG 3 OUT 4 VCC 5 CTRL 6 TRIG 7 DIS 8 VCC
    R1: 1 DIS 2 VCC ; R2: 1 TRIG 2 DIS ; R3: 1 OUT 2 LED
    C1: 1 GND 2 TRIG ; C2: 1 GND 2 CTRL ; D1: 1 GND(K) 2 LED(A)
    J1: 1 VCC 2 GND

NOTE: .kicad_sym pin y offsets are inverted vs .kicad_sch coordinates:
    abs = (origin.x + dx, origin.y - dy)   for rot = 0

GRID: every coordinate below is in 50-mil grid units and converted with
mm() on emit. ERC's endpoint_off_grid check requires symbol pin tips and
wire ends to sit on the 1.27 mm grid, so all symbol origins, wire ends,
junctions and labels take integer grid arguments. Symbol pin offsets
(3.81 / 5.08 / 10.16 / 2.54 mm) are all exact grid multiples, so a pin
tip lands on grid whenever its symbol origin does.
"""

import sys
import uuid
import os


def mm(g):
    """50-mil grid units -> mm, formatted without float dust."""
    return f"{g * 1.27:.3f}".rstrip("0").rstrip(".")

SYMS = {
    "Timer.kicad_sym": ["NE555D"],
    "Device.kicad_sym": ["R", "C", "LED"],
    "Connector_Generic.kicad_sym": ["Conn_01x02"],
    "power.kicad_sym": ["VCC", "GND", "PWR_FLAG"],
}

# pin number -> (dx, dy) in .kicad_sym coordinates (connection end of pin)
PINS = {
    "Timer:NE555D": {"1": (0, -10.16), "8": (2.54, 10.16), "5": (0, 10.16),
                     "3": (10.16, 0), "4": (-10.16, 5.08), "7": (-10.16, 2.54),
                     "6": (-10.16, -2.54), "2": (-10.16, -5.08)},
    "Device:R": {"1": (0, 3.81), "2": (0, -3.81)},
    "Device:C": {"1": (0, 3.81), "2": (0, -3.81)},
    "Device:LED": {"1": (-3.81, 0), "2": (3.81, 0)},
    "Connector_Generic:Conn_01x02": {"1": (-5.08, 0), "2": (-5.08, -2.54)},
    "power:VCC": {"1": (0, 0)},
    "power:GND": {"1": (0, 0)},
    "power:PWR_FLAG": {"1": (0, 0)},
}

FPS = {
    "J1": "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    "U1": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "R1": "Resistor_SMD:R_0805_2012Metric",
    "R2": "Resistor_SMD:R_0805_2012Metric",
    "R3": "Resistor_SMD:R_0805_2012Metric",
    "C1": "Capacitor_SMD:C_0805_2012Metric",
    "C2": "Capacitor_SMD:C_0805_2012Metric",
    "D1": "LED_SMD:LED_0805_2012Metric",
}


def extract_symbol(libfile, name):
    src = open(libfile, encoding="utf-8").read()
    i = src.find(f'(symbol "{name}"')
    assert i >= 0, f"{name} not in {libfile}"
    depth = 0
    j = i
    while True:
        if src[j] == "(":
            depth += 1
        elif src[j] == ")":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
        j += 1


def rot_local(x, y, deg):
    """Rotate a (dx,dy) symbol-local offset by the instance angle."""
    if deg == 0:
        return x, y
    if deg == 180:
        return -x, -y
    if deg == 90:
        return -y, x
    if deg == 270:
        return y, -x
    raise ValueError(deg)


SCH_UUID = str(uuid.uuid4())


class Gen:
    def __init__(self):
        self.lines = []

    def emit(self, s):
        self.lines.append(s)

    def symbol_inst(self, lib, name, ref, value, x, y, rot=0, power=False):
        libid = f"{lib}:{name}"
        pins = PINS[libid]
        bom = "no" if power else "yes"
        board = "no" if power else "yes"
        s = (f'  (symbol (lib_id "{libid}") (at {mm(x)} {mm(y)} {rot})'
             ' (unit 1)\n')
        s += f'    (in_bom {bom}) (on_board {board}) (dnp no)\n'
        s += f'    (uuid {uuid.uuid4()})\n'
        for pname, pval, hide in [("Reference", ref, False),
                                  ("Value", value, False),
                                  ("Footprint", FPS.get(ref, ""), True),
                                  ("Datasheet", "~", True)]:
            h = " (hide yes)" if hide else ""
            s += (f'    (property "{pname}" "{pval}" (at {mm(x)} {mm(y)} 0)\n'
                  f'      (effects (font (size 1.27 1.27)){h})\n    )\n')
        for pn in pins:
            s += f'    (pin "{pn}" (uuid {uuid.uuid4()}))\n'
        s += ('    (instances\n      (project "555-blinker"\n'
              f'        (path "/{SCH_UUID}"\n          (reference "{ref}")'
              ' (unit 1)\n        )\n      )\n    )\n  )\n')
        self.emit(s)
        out = {}
        for pn, (px, py) in pins.items():
            rx, ry = rot_local(px, py, rot)
            # sym y axis is inverted on the sheet; returned in mm
            out[pn] = (x * 1.27 + rx, y * 1.27 - ry)
        return out

    def wire(self, x1, y1, x2, y2):
        self.emit(f'  (wire (pts (xy {mm(x1)} {mm(y1)}) (xy {mm(x2)} {mm(y2)}))\n'
                  f'    (stroke (width 0) (type solid))\n'
                  f'    (uuid {uuid.uuid4()})\n  )\n')

    def junction(self, x, y):
        self.emit(f'  (junction (at {mm(x)} {mm(y)}) (diameter 1.016)'
                  f' (color 0 0 0 0)\n    (uuid {uuid.uuid4()})\n  )\n')

    def label(self, name, x, y):
        self.emit(f'  (label "{name}" (at {mm(x)} {mm(y)} 0)'
                  ' (fields_autoplaced)\n'
                  f'    (effects (font (size 1.27 1.27)) (justify left bottom))\n'
                  f'    (uuid {uuid.uuid4()})\n  )\n')


def main():
    libdir, outdir = sys.argv[1], sys.argv[2]
    out = os.path.join(outdir, "555-blinker.kicad_sch")

    g = Gen()
    g.emit('(kicad_sch (version 20230121) (generator eeschema)\n')
    g.emit(f'  (uuid {SCH_UUID})\n')
    g.emit('  (paper "A4")\n')

    g.emit('  (lib_symbols\n')
    for lib, names in SYMS.items():
        libname = lib.removesuffix(".kicad_sym")
        for name in names:
            body = extract_symbol(os.path.join(libdir, lib), name)
            body = body.replace(f'(symbol "{name}"',
                                f'(symbol "{libname}:{name}"', 1)
            g.emit('    ' + body + '\n')
    g.emit('  )\n')

    P = {}

    # ---- connector + power flags -------------------------------------------
    # J1 pin1 (top) = VCC, pin2 (bottom) = GND; all coords in grid units.
    P["J1"] = g.symbol_inst("Connector_Generic", "Conn_01x02", "J1",
                            "Conn_01x02", 47, 63)     # p1 (43,63) p2 (43,65)
    g.wire(43, 63, 40, 63)
    g.symbol_inst("power", "VCC", "#PWR01", "VCC", 40, 63, power=True)
    g.wire(40, 63, 37, 63)
    g.symbol_inst("power", "PWR_FLAG", "#FLG01", "PWR_FLAG", 37, 63, power=True)
    g.wire(43, 65, 40, 65)
    g.symbol_inst("power", "GND", "#PWR02", "GND", 40, 65, power=True)
    g.wire(40, 65, 37, 65)
    g.symbol_inst("power", "PWR_FLAG", "#FLG02", "PWR_FLAG", 37, 65, power=True)

    # ---- U1 (NE555D at grid 87,63) ------------------------------------------
    # p1 GND (87,71) bot | p8 VCC (89,55) top | p5 CONT (87,55) top
    # p3 OUT (95,63) | left col: p4 RST (79,59), p7 DIS (79,61),
    #                            p6 THR (79,65), p2 TRG (79,67)
    P["U1"] = g.symbol_inst("Timer", "NE555D", "U1", "NE555", 87, 63)
    g.wire(87, 71, 87, 74)                              # GND
    g.symbol_inst("power", "GND", "#PWR03", "GND", 87, 74, power=True)
    g.wire(89, 55, 89, 52)                              # VCC
    g.symbol_inst("power", "VCC", "#PWR04", "VCC", 89, 52, power=True)
    g.wire(79, 59, 75, 59)                              # RST
    g.wire(75, 59, 75, 56)
    g.symbol_inst("power", "VCC", "#PWR05", "VCC", 75, 56, power=True)
    # CONT -> C2.2 -> GND   (C2 at grid (87,50): p2 bot (87,53), p1 top (87,47))
    P["C2"] = g.symbol_inst("Device", "C", "C2", "10n", 87, 50)
    g.wire(87, 55, 87, 53)
    g.label("CTRL", 87, 54)
    g.wire(87, 47, 87, 44)
    g.symbol_inst("power", "GND", "#PWR06", "GND", 87, 44, power=True)

    # ---- timing chain: VCC -> R1 -> DIS -> R2 -> TRIG -> C1 -> GND ----------
    # R1 rot180 (67,73): p2 top (67,70)=VCC, p1 bot (67,76)=DIS
    P["R1"] = g.symbol_inst("Device", "R", "R1", "68k", 67, 73, rot=180)
    # R2 rot180 (67,81): p2 top (67,78)=DIS, p1 bot (67,84)=TRIG
    P["R2"] = g.symbol_inst("Device", "R", "R2", "68k", 67, 81, rot=180)
    # C1 rot180 (67,89): p2 top (67,86)=TRIG, p1 bot (67,92)=GND
    P["C1"] = g.symbol_inst("Device", "C", "C1", "100n", 67, 89, rot=180)

    g.wire(67, 70, 67, 66)                              # R1.2 -> VCC
    g.symbol_inst("power", "VCC", "#PWR07", "VCC", 67, 66, power=True)

    # A wire with a pin tip at BOTH ends connects only one pin in KiCad's
    # connectivity engine; split pin-to-pin links at a junction instead.
    g.wire(67, 76, 67, 77)                              # R1.1 -> node
    g.junction(67, 77)
    g.wire(67, 77, 67, 78)                              # node -> R2.2 (DIS)
    g.wire(67, 77, 73, 77)
    g.wire(73, 77, 73, 61)
    g.wire(73, 61, 79, 61)                              # -> U1.7 DIS
    g.label("DIS", 70, 77)

    g.wire(67, 84, 67, 85)                              # R2.1 -> node
    g.junction(67, 85)
    g.wire(67, 85, 67, 86)                              # node -> C1.2 (TRIG)
    g.wire(67, 85, 76, 85)
    # every net vertex gets a junction and every wire runs node-to-node;
    # a junction mid-segment breaks connectivity of downstream pins
    g.wire(76, 85, 76, 68)
    g.junction(76, 68)
    g.wire(76, 68, 76, 65)
    g.wire(76, 65, 79, 65)                              # -> U1.6 THR
    g.wire(76, 68, 77, 68)
    g.wire(77, 68, 77, 67)
    g.wire(77, 67, 79, 67)                              # -> U1.2 TRG
    g.label("TRIG", 72, 85)

    g.wire(67, 92, 67, 94)
    g.symbol_inst("power", "GND", "#PWR08", "GND", 67, 94, power=True)

    # ---- output: U1.3 OUT -> R3 -> LED -> GND --------------------------------
    # R3 rot0 (102,66): p1 top (102,63)=OUT, p2 bot (102,69)=LED
    P["R3"] = g.symbol_inst("Device", "R", "R3", "470", 102, 66)
    g.wire(95, 63, 102, 63)
    g.label("OUT", 98, 63)

    # D1 rot180 (107,75): p2 A left (104,75)=LED, p1 K right (110,75)=GND
    P["D1"] = g.symbol_inst("Device", "LED", "D1", "LED", 107, 75, rot=180)
    g.wire(102, 69, 102, 75)
    g.wire(102, 75, 104, 75)
    g.label("LED", 103, 75)
    g.wire(110, 75, 113, 75)
    g.wire(113, 75, 113, 81)
    g.symbol_inst("power", "GND", "#PWR09", "GND", 113, 81, power=True)

    g.emit('  (sheet_instances\n    (path "/" (page "1"))\n  )\n')
    g.emit(')\n')

    open(out, "w").write("".join(g.lines))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
