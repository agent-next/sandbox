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
"""

import sys
import uuid
import os

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
        s = f'  (symbol (lib_id "{libid}") (at {x} {y} {rot}) (unit 1)\n'
        s += f'    (in_bom {bom}) (on_board {board}) (dnp no)\n'
        s += f'    (uuid {uuid.uuid4()})\n'
        for pname, pval, hide in [("Reference", ref, False),
                                  ("Value", value, False),
                                  ("Footprint", FPS.get(ref, ""), True),
                                  ("Datasheet", "~", True)]:
            h = " (hide yes)" if hide else ""
            s += (f'    (property "{pname}" "{pval}" (at {x} {y} 0)\n'
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
            out[pn] = (x + rx, y - ry)   # sym y axis is inverted on the sheet
        return out

    def wire(self, x1, y1, x2, y2):
        self.emit(f'  (wire (pts (xy {x1} {y1}) (xy {x2} {y2}))\n'
                  f'    (stroke (width 0) (type solid))\n'
                  f'    (uuid {uuid.uuid4()})\n  )\n')

    def junction(self, x, y):
        self.emit(f'  (junction (at {x} {y}) (diameter 1.016) (color 0 0 0 0)\n'
                  f'    (uuid {uuid.uuid4()})\n  )\n')

    def label(self, name, x, y):
        self.emit(f'  (label "{name}" (at {x} {y} 0) (fields_autoplaced)\n'
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
    # J1 pin1 (top) = VCC, pin2 (bottom) = GND
    P["J1"] = g.symbol_inst("Connector_Generic", "Conn_01x02", "J1",
                            "Conn_01x02", 60, 80)     # p1 (54.92,80) p2 (54.92,82.54)
    g.wire(54.92, 80, 50.8, 80)
    g.symbol_inst("power", "VCC", "#PWR01", "VCC", 50.8, 80, power=True)
    g.wire(50.8, 80, 46.5, 80)
    g.symbol_inst("power", "PWR_FLAG", "#FLG01", "PWR_FLAG", 46.5, 80, power=True)
    g.wire(54.92, 82.54, 50.8, 82.54)
    g.symbol_inst("power", "GND", "#PWR02", "GND", 50.8, 82.54, power=True)
    g.wire(50.8, 82.54, 46.5, 82.54)
    g.symbol_inst("power", "PWR_FLAG", "#FLG02", "PWR_FLAG", 46.5, 82.54, power=True)

    # ---- U1 (NE555D at 110,80) ----------------------------------------------
    # p1 GND (110,90.16) bot | p8 VCC (112.54,69.84) top | p5 CONT (110,69.84) top
    # p3 OUT (120.16,80) | left col: p4 RST 74.92, p7 DIS 77.46, p6 THR 82.54,
    #                                  p2 TRG 85.08 (all x=99.84)
    P["U1"] = g.symbol_inst("Timer", "NE555D", "U1", "NE555", 110, 80)
    g.wire(110, 90.16, 110, 93.98)                      # GND
    g.symbol_inst("power", "GND", "#PWR03", "GND", 110, 93.98, power=True)
    g.wire(112.54, 69.84, 112.54, 66.04)                # VCC
    g.symbol_inst("power", "VCC", "#PWR04", "VCC", 112.54, 66.04, power=True)
    g.wire(99.84, 74.92, 95, 74.92)                     # RST
    g.wire(95, 74.92, 95, 71)
    g.symbol_inst("power", "VCC", "#PWR05", "VCC", 95, 71, power=True)
    # CONT -> C2.2 -> GND    (C2 at 110,63: pin2 bot (110,66.81), pin1 top (110,59.19))
    P["C2"] = g.symbol_inst("Device", "C", "C2", "10n", 110, 63)
    g.wire(110, 69.84, 110, 66.81)
    g.label("CTRL", 110, 68)
    g.wire(110, 59.19, 110, 56)
    g.symbol_inst("power", "GND", "#PWR06", "GND", 110, 56, power=True)

    # ---- timing chain: VCC -> R1 -> DIS -> R2 -> TRIG -> C1 -> GND ----------
    # R1 rot180 (85,92): p2 top (85,88.19)=VCC, p1 bot (85,95.81)=DIS
    P["R1"] = g.symbol_inst("Device", "R", "R1", "68k", 85, 92, rot=180)
    # R2 rot180 (85,102): p2 top (85,98.19)=DIS, p1 bot (85,105.81)=TRIG
    P["R2"] = g.symbol_inst("Device", "R", "R2", "68k", 85, 102, rot=180)
    # C1 rot180 (85,112): p2 top (85,108.19)=TRIG, p1 bot (85,115.81)=GND
    P["C1"] = g.symbol_inst("Device", "C", "C1", "100n", 85, 112, rot=180)

    g.wire(85, 88.19, 85, 84)                           # R1.2 -> VCC
    g.symbol_inst("power", "VCC", "#PWR07", "VCC", 85, 84, power=True)

    # A wire with a pin tip at BOTH ends connects only one pin in KiCad's
    # connectivity engine; split pin-to-pin links at a junction instead.
    g.wire(85, 95.81, 85, 97)                           # R1.1 -> node
    g.junction(85, 97)
    g.wire(85, 97, 85, 98.19)                           # node -> R2.2 (DIS)
    g.wire(85, 97, 92, 97)
    g.wire(92, 97, 92, 77.46)
    g.wire(92, 77.46, 99.84, 77.46)                     # -> U1.7 DIS
    g.label("DIS", 89, 97)

    g.wire(85, 105.81, 85, 107)                         # R2.1 -> node
    g.junction(85, 107)
    g.wire(85, 107, 85, 108.19)                         # node -> C1.2 (TRIG)
    g.wire(85, 107, 96, 107)
    # every net vertex gets a junction and every wire runs node-to-node;
    # a junction mid-segment breaks connectivity of downstream pins
    g.wire(96, 107, 96, 87)
    g.junction(96, 87)
    g.wire(96, 87, 96, 82.54)
    g.wire(96, 82.54, 99.84, 82.54)                     # -> U1.6 THR
    g.wire(96, 87, 97, 87)
    g.wire(97, 87, 97, 85.08)
    g.wire(97, 85.08, 99.84, 85.08)                     # -> U1.2 TRG
    g.label("TRIG", 96, 100)

    g.wire(85, 115.81, 85, 119)
    g.symbol_inst("power", "GND", "#PWR08", "GND", 85, 119, power=True)

    # ---- output: U1.3 OUT -> R3 -> LED -> GND --------------------------------
    # R3 rot0 (130,84): p1 top (130,80.19)=OUT, p2 bot (130,87.81)=LED
    P["R3"] = g.symbol_inst("Device", "R", "R3", "470", 130, 84)
    g.wire(120.16, 80, 130, 80)
    g.wire(130, 80, 130, 80.19)
    g.label("OUT", 125, 80)

    # D1 rot180 (136,96): p2 A left (132.19,96)=LED, p1 K right (139.81,96)=GND
    P["D1"] = g.symbol_inst("Device", "LED", "D1", "LED", 136, 96, rot=180)
    g.wire(130, 87.81, 130, 96)
    g.wire(130, 96, 132.19, 96)
    g.label("LED", 131, 96)
    g.wire(139.81, 96, 143, 96)
    g.wire(143, 96, 143, 103)
    g.symbol_inst("power", "GND", "#PWR09", "GND", 143, 103, power=True)

    g.emit('  (sheet_instances\n    (path "/" (page "1"))\n  )\n')
    g.emit(')\n')

    open(out, "w").write("".join(g.lines))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
