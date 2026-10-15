#!/usr/bin/env python3
"""Generate the 555-blinker PCB (555-blinker.kicad_pcb) with pcbnew.

Run with the KiCad AppImage's bundled python, e.g.
    "$KICAD_APP/bin/python3.11" tools/gen_board.py <fp-lib-dir> <out-dir>

The board is a 40x30 mm 2-layer 555 astable LED blinker:
    J1 2-pin header (VCC/GND), U1 NE555 SOIC-8, R1/R2/C1 timing,
    C2 bypass, R3+D1 LED on the output.
All footprints are loaded from the stock KiCad footprint libraries and
embedded into the .kicad_pcb on save, so the result is self-contained.
"""

import os
import sys

import pcbnew

F_Cu = pcbnew.F_Cu
B_Cu = pcbnew.B_Cu
Edge = pcbnew.Edge_Cuts


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def add_track(board, net, layer, x1, y1, x2, y2, w=0.25):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pt(x1, y1))
    t.SetEnd(pt(x2, y2))
    t.SetWidth(mm(w))
    t.SetLayer(layer)
    t.SetNet(net)
    board.Add(t)


def add_via(board, net, x, y, dia=0.8, drill=0.4):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pt(x, y))
    v.SetWidth(mm(dia))
    v.SetDrill(mm(drill))
    v.SetLayerPair(F_Cu, B_Cu)
    v.SetNet(net)
    board.Add(v)


def add_edge(board, x1, y1, x2, y2):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(pt(x1, y1))
    s.SetEnd(pt(x2, y2))
    s.SetWidth(mm(0.05))
    s.SetLayer(Edge)
    board.Add(s)


def place(board, libdir, lib, name, ref, value, x, y, rot_deg, nets):
    fp = pcbnew.FootprintLoad(os.path.join(libdir, lib), name)
    fp.SetPosition(pt(x, y))
    if rot_deg:
        fp.SetOrientation(pcbnew.EDA_ANGLE(rot_deg, pcbnew.DEGREES_T))
    fp.Reference().SetText(ref)
    fp.SetValue(value)
    board.Add(fp)
    for pad in fp.Pads():
        pad.SetNet(nets[pad.GetNumber()])
    return fp


def main():
    libdir, outdir = sys.argv[1], sys.argv[2]
    out = os.path.join(outdir, "555-blinker.kicad_pcb")

    board = pcbnew.NewBoard(out)

    ds = board.GetDesignSettings()
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetClearance(mm(0.2))
    nc.SetTrackWidth(mm(0.25))
    nc.SetViaDiameter(mm(0.8))
    nc.SetViaDrill(mm(0.4))
    nc.SetuViaDiameter(mm(0.3))
    nc.SetuViaDrill(mm(0.1))
    nc.SetDiffPairWidth(mm(0.25))
    nc.SetDiffPairGap(mm(0.25))

    # board outline: 40 x 30 mm
    add_edge(board, 100, 100, 140, 100)
    add_edge(board, 140, 100, 140, 130)
    add_edge(board, 140, 130, 100, 130)
    add_edge(board, 100, 130, 100, 100)

    # nets
    NETS = ["VCC", "GND", "DIS", "TRIG", "CTRL", "OUT", "LED"]
    netinfo = {}
    for n in NETS:
        ni = pcbnew.NETINFO_ITEM(board, n)
        board.Add(ni)
        netinfo[n] = ni
    netcode = {n: ni.GetNetCode() for n, ni in netinfo.items()}

    VCC, GND, DIS, TRIG, CTRL, OUT, LED = (netinfo[n] for n in NETS)

    SOIC = "Package_SO.pretty"
    R0805 = "Resistor_SMD.pretty"
    C0805 = "Capacitor_SMD.pretty"
    LED0805 = "LED_SMD.pretty"
    CONN = "Connector_PinHeader_2.54mm.pretty"

    # footprints --------------------------------------------------------------
    # J1: pin 1 = VCC, pin 2 = GND
    place(board, libdir, CONN, "PinHeader_1x02_P2.54mm_Vertical",
          "J1", "Conn_01x02", 103, 106, 0, {"1": VCC, "2": GND})

    # U1 NE555 SOIC-8: 1 GND 2 TRIG 3 OUT 4 VCC(RESET) 5 CTRL 6 TRIG(THR)
    #                  7 DIS 8 VCC
    place(board, libdir, SOIC, "SOIC-8_3.9x4.9mm_P1.27mm",
          "U1", "NE555", 120, 113, 0,
          {"1": GND, "2": TRIG, "3": OUT, "4": VCC,
           "5": CTRL, "6": TRIG, "7": DIS, "8": VCC})

    # NOTE: rot=90 puts pad 1 at the bottom (+y), pad 2 at the top
    place(board, libdir, R0805, "R_0805_2012Metric",
          "R1", "68k", 128, 111, 90, {"1": DIS, "2": VCC})
    place(board, libdir, R0805, "R_0805_2012Metric",
          "R2", "68k", 128, 114.5, 90, {"1": TRIG, "2": DIS})
    place(board, libdir, C0805, "C_0805_2012Metric",
          "C1", "100n", 128, 119, 90, {"1": GND, "2": TRIG})
    place(board, libdir, C0805, "C_0805_2012Metric",
          "C2", "10n", 133, 116, 90, {"1": GND, "2": CTRL})
    place(board, libdir, R0805, "R_0805_2012Metric",
          "R3", "470", 111, 116, 0, {"1": OUT, "2": LED})
    # LED_SMD pad 1 = cathode, pad 2 = anode; the schematic drives
    # pin 2 (A) from R3 and ties pin 1 (K) to GND — match that here.
    place(board, libdir, LED0805, "LED_0805_2012Metric",
          "D1", "LED", 107, 119, 0, {"1": GND, "2": LED})

    # VCC: B.Cu bus along the top, F.Cu stubs into SMD pads through vias
    add_track(board, VCC, B_Cu, 103, 106, 128, 106)
    add_via(board, VCC, 124.5, 109)
    add_track(board, VCC, B_Cu, 124.5, 106, 124.5, 109)
    add_track(board, VCC, F_Cu, 124.5, 109, 122.475, 109)
    add_track(board, VCC, F_Cu, 122.475, 109, 122.475, 110.9)  # -> U1.8
    add_via(board, VCC, 117.525, 116.5)
    add_track(board, VCC, B_Cu, 117.525, 106, 117.525, 116.5)
    add_track(board, VCC, F_Cu, 117.525, 116.5, 117.525, 115.3)  # -> U1.4
    add_via(board, VCC, 128, 108.5)
    add_track(board, VCC, B_Cu, 128, 106, 128, 108.5)
    add_track(board, VCC, F_Cu, 128, 108.5, 128, 109.7)        # -> R1.1

    # GND: B.Cu bus along the bottom fed from J1.2
    add_track(board, GND, B_Cu, 103, 108.54, 103, 124)
    add_track(board, GND, B_Cu, 103, 124, 133, 124)
    add_via(board, GND, 113, 111.095)
    add_track(board, GND, B_Cu, 113, 111.095, 113, 124)
    add_track(board, GND, F_Cu, 113, 111.095, 116.7, 111.095)  # -> U1.1
    add_via(board, GND, 128, 122)
    add_track(board, GND, B_Cu, 128, 122, 128, 124)
    add_track(board, GND, F_Cu, 128, 122, 128, 120.2)          # -> C1.2
    add_via(board, GND, 133, 119.5)
    add_track(board, GND, B_Cu, 133, 119.5, 133, 124)
    add_track(board, GND, F_Cu, 133, 119.5, 133, 117.2)        # -> C2.2
    add_via(board, GND, 106.0625, 121.7)
    add_track(board, GND, B_Cu, 106.0625, 121.7, 106.0625, 124)
    add_track(board, GND, F_Cu, 106.0625, 121.7, 106.0625, 119.5)  # -> D1.1

    # DIS: U1.7 -> R1.2 and R2.1
    add_track(board, DIS, F_Cu, 123.45, 112.365, 128, 112.365)
    add_track(board, DIS, F_Cu, 128, 112.365, 128, 113.4)

    # TRIG: U1.2, U1.6, R2.2, C1.1 ; U1.2 leg hops over OUT on B.Cu
    add_track(board, TRIG, F_Cu, 123.45, 113.635, 126, 113.635)
    add_track(board, TRIG, F_Cu, 126, 113.635, 126, 115.412)
    add_track(board, TRIG, F_Cu, 126, 115.412, 127.9, 115.412)  # -> R2.2
    add_track(board, TRIG, F_Cu, 128, 115.7, 128, 117.8)        # R2.2 -> C1.1
    add_via(board, TRIG, 114, 112.365)
    add_track(board, TRIG, F_Cu, 114, 112.365, 116.7, 112.365)  # -> U1.2
    add_track(board, TRIG, B_Cu, 114, 112.365, 114, 118.05)
    add_via(board, TRIG, 126.5, 118.05)
    add_track(board, TRIG, F_Cu, 126.5, 118.05, 127.8, 118.05)  # -> C1.1
    add_track(board, TRIG, B_Cu, 114, 118.05, 126.5, 118.05)

    # CTRL: U1.5 -> C2.1
    add_track(board, CTRL, F_Cu, 122.475, 115.0, 122.475, 118.9)
    add_track(board, CTRL, F_Cu, 122.475, 118.9, 130.5, 118.9)
    add_track(board, CTRL, F_Cu, 130.5, 118.9, 130.5, 115.2)
    add_track(board, CTRL, F_Cu, 130.5, 115.2, 132.6, 115.2)

    # OUT: U1.3 -> R3.1 (enter pad 1 from the top)
    add_track(board, OUT, F_Cu, 116.55, 113.635, 111, 113.635)
    add_track(board, OUT, F_Cu, 111, 113.635, 111, 114.8)
    add_track(board, OUT, F_Cu, 111, 114.8, 110.088, 114.8)
    add_track(board, OUT, F_Cu, 110.088, 114.8, 110.088, 115.6)

    # LED: R3.2 -> D1.2 (anode; pad 1 is the grounded cathode)
    add_track(board, LED, F_Cu, 111.912, 116.6, 111.912, 117.5)
    add_track(board, LED, F_Cu, 111.912, 117.5, 107.9375, 117.5)
    add_track(board, LED, F_Cu, 107.9375, 117.5, 107.9375, 118.9)

    # back-silk label so B.Silkscreen carries real content
    t = pcbnew.PCB_TEXT(board)
    t.SetText("555 blinker")
    t.SetPosition(pt(120, 103))
    t.SetLayer(pcbnew.B_SilkS)
    t.SetMirrored(True)
    board.Add(t)

    pcbnew.SaveBoard(out, board)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
