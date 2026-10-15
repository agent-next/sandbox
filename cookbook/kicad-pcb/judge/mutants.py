#!/usr/bin/env python3
"""Scripted single-edit mutants of the good 555-blinker project.

Each mutant copies examples/good/555-blinker and applies ONE localised
edit to the schematic, board, or project file, so the mutation itself
is reviewable.

Usage: mutants.py <good_dir> <out_dir>
Writes out_dir/<mutant_name>/ project copies; prints one line per mutant.
"""

import json
import os
import re
import shutil
import sys
import uuid

SCH = "555-blinker.kicad_sch"
PCB = "555-blinker.kicad_pcb"
PRO = "555-blinker.kicad_pro"


def sexpr_block_range(text, needle):
    """(start, end) offsets of the balanced-paren block at `needle`."""
    i = text.index(needle)
    depth = 0
    j = i
    while True:
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return i, j + 1
        j += 1


def remove_sexpr_block(text, needle):
    """Delete the balanced-paren block that begins at `needle`."""
    i, j = sexpr_block_range(text, needle)
    return text[:i] + text[j:]


def replace_once(text, old, new):
    assert text.count(old) >= 1, f"pattern not found: {old!r}"
    return text.replace(old, new, 1)


# -- mutants ---------------------------------------------------------------

def m_erc_unconnected_pin(sch, pcb, pro):
    """Delete the R1->DIS node wire: pin_not_connected ERC error."""
    sch = remove_sexpr_block(sch, "(wire (pts (xy 85.09 96.52) (xy 85.09 97.79))")
    return sch, pcb, pro


def m_erc_power_short(sch, pcb, pro):
    """Wire J1's VCC pin straight onto its GND pin: ERC power conflict."""
    i = sch.index("(sheet_instances")
    wire = ('  (wire (pts (xy 54.61 80.01) (xy 54.61 82.55))\n'
            '    (stroke (width 0) (type solid))\n'
            f'    (uuid {uuid.uuid4()})\n  )\n')
    sch = sch[:i] + wire + sch[i:]
    return sch, pcb, pro


def m_erc_off_grid(sch, pcb, pro):
    """Move a shared wire vertex 0.05 mm off the 50-mil grid: the two wire
    ends still touch (connectivity kept, no error) but ERC reports
    endpoint_off_grid warnings — a type outside G1's allow-list."""
    assert sch.count("(xy 97.79 86.36)") == 2
    sch = sch.replace("(xy 97.79 86.36)", "(xy 97.79 86.41)")
    return sch, pcb, pro


def m_netlist_mismatch(sch, pcb, pro):
    """Rename the TRIG net label: schematic and PCB net sets diverge."""
    sch = replace_once(sch, '(label "TRIG"', '(label "TRIGX"')
    return sch, pcb, pro


def m_led_reversed(sch, pcb, pro):
    """Swap D1's pad nets — cathode pad onto LED, anode pad onto GND.
    Every net name and footprint reference is unchanged, so only a
    (ref, pin) net-membership check can see the LED is backwards."""
    i, j = sexpr_block_range(pcb, '(footprint "LED_0805_2012Metric"')
    blk = pcb[i:j]
    a, b = '(net 2 "GND")', '(net 7 "LED")'
    assert blk.count(a) == 1 and blk.count(b) == 1, blk
    blk = blk.replace(a, "\0").replace(b, a).replace("\0", b)
    pcb = pcb[:i] + blk + pcb[j:]
    return sch, pcb, pro


def m_drc_unconnected(sch, pcb, pro):
    """Delete one copper segment: DRC reports an unrouted connection."""
    pcb = remove_sexpr_block(pcb, "(segment")
    return sch, pcb, pro


def m_drc_short(sch, pcb, pro):
    """Extend the VCC stub so it ends inside C1's GND pad: shorting_items."""
    pcb = replace_once(
        pcb,
        "(start 128 108.5)\n\t\t(end 128 109.7)",
        "(start 128 108.5)\n\t\t(end 128 120.2)")
    return sch, pcb, pro


def m_drc_rules_off(sch, pcb, pro):
    """The drc_short short-circuit PLUS a .kicad_pro that suppresses it:
    every violation type the short produces is set to "ignore" in the
    artifact's own rule_severities.  Grading uses the judge's pinned
    rules, so the short is still caught by G2."""
    sch, pcb, pro = m_drc_short(sch, pcb, pro)
    d = json.loads(pro)
    sev = d["board"]["design_settings"]["rule_severities"]
    for k in ("shorting_items", "tracks_crossing", "solder_mask_bridge",
              "clearance"):
        sev[k] = "ignore"
    return sch, pcb, json.dumps(d, indent=2)


def m_outline_open(sch, pcb, pro):
    """Delete one Edge.Cuts segment: board outline no longer closed."""
    # board-level (gr_line ...) blocks in this project are the outline
    pcb = remove_sexpr_block(pcb, "(gr_line")
    return sch, pcb, pro


def m_board_oversize(sch, pcb, pro):
    """Stretch the outline to 100 mm wide — over the published 50 mm
    limit — while staying a closed loop that the Gerber extents still
    match, so only the limits gate can see it."""
    for a, b in [("(end 140 100)", "(end 200 100)"),
                 ("(start 140 100)", "(start 200 100)"),
                 ("(end 140 130)", "(end 200 130)"),
                 ("(start 140 130)", "(start 200 130)")]:
        pcb = replace_once(pcb, a, b)
    return sch, pcb, pro


def m_drill_no_tools(sch, pcb, pro):
    """Zero every pad/via drill diameter: holes have nothing to drill
    them with (G6 counts pads+vias missing a drill)."""
    pcb = re.sub(r"\(drill [\d.]+\)", "(drill 0)", pcb)
    return sch, pcb, pro


MUTANTS = {
    "erc_unconnected_pin": m_erc_unconnected_pin,
    "erc_power_short": m_erc_power_short,
    "erc_off_grid": m_erc_off_grid,
    "netlist_mismatch": m_netlist_mismatch,
    "led_reversed": m_led_reversed,
    "drc_unconnected": m_drc_unconnected,
    "drc_short": m_drc_short,
    "drc_rules_off": m_drc_rules_off,
    "outline_open": m_outline_open,
    "board_oversize": m_board_oversize,
    "drill_no_tools": m_drill_no_tools,
}


def main():
    good, outdir = sys.argv[1], sys.argv[2]
    sch0 = open(os.path.join(good, SCH)).read()
    pcb0 = open(os.path.join(good, PCB)).read()
    pro0 = open(os.path.join(good, PRO)).read()
    for name, fn in MUTANTS.items():
        dst = os.path.join(outdir, name)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(good, dst)
        sch, pcb, pro = fn(sch0, pcb0, pro0)
        open(os.path.join(dst, SCH), "w").write(sch)
        open(os.path.join(dst, PCB), "w").write(pcb)
        open(os.path.join(dst, PRO), "w").write(pro)
        print(name)
    print(f"{len(MUTANTS)} mutants written to {outdir}")


if __name__ == "__main__":
    main()
