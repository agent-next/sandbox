#!/usr/bin/env python3
"""Scripted single-edit mutants of the good 555-blinker project.

Each mutant copies examples/good/555-blinker and applies ONE localised
text edit to the schematic or PCB s-expression source, so the mutation
itself is reviewable.

Usage: mutants.py <good_dir> <out_dir>
Writes out_dir/<mutant_name>/ project copies; prints one line per mutant.
"""

import os
import re
import shutil
import sys
import uuid

SCH = "555-blinker.kicad_sch"
PCB = "555-blinker.kicad_pcb"


def remove_sexpr_block(text, needle):
    """Delete the balanced-paren block that begins at `needle`."""
    i = text.index(needle)
    depth = 0
    j = i
    while True:
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return text[:i] + text[j + 1:]


def replace_once(text, old, new):
    assert text.count(old) >= 1, f"pattern not found: {old!r}"
    return text.replace(old, new, 1)


# -- mutants ---------------------------------------------------------------

def m_erc_unconnected_pin(sch, pcb):
    """Delete the R1->DIS node wire: pin_not_connected ERC error."""
    sch = remove_sexpr_block(sch, "(wire (pts (xy 85 95.81) (xy 85 97))")
    return sch, pcb


def m_erc_power_short(sch, pcb):
    """Wire J1's VCC pin straight onto its GND pin: ERC power conflict."""
    i = sch.index("(sheet_instances")
    wire = ('  (wire (pts (xy 54.92 80) (xy 54.92 82.54))\n'
            '    (stroke (width 0) (type solid))\n'
            f'    (uuid {uuid.uuid4()})\n  )\n')
    sch = sch[:i] + wire + sch[i:]
    return sch, pcb


def m_netlist_mismatch(sch, pcb):
    """Rename the TRIG net label: schematic and PCB net sets diverge."""
    sch = replace_once(sch, '(label "TRIG"', '(label "TRIGX"')
    return sch, pcb


def m_drc_unconnected(sch, pcb):
    """Delete one copper segment: DRC reports an unrouted connection."""
    pcb = remove_sexpr_block(pcb, "(segment")
    return sch, pcb


def m_drc_short(sch, pcb):
    """Extend the VCC stub so it ends inside C1's GND pad: shorting_items."""
    pcb = replace_once(
        pcb,
        "(start 128 108.5)\n\t\t(end 128 109.7)",
        "(start 128 108.5)\n\t\t(end 128 120.2)")
    return sch, pcb


def m_outline_open(sch, pcb):
    """Delete one Edge.Cuts segment: board outline no longer closed."""
    # board-level (gr_line ...) blocks in this project are the outline
    pcb = remove_sexpr_block(pcb, "(gr_line")
    return sch, pcb


def m_drill_no_tools(sch, pcb):
    """Zero every pad drill diameter: drill export has no valid tools."""
    pcb = re.sub(r"\(drill [\d.]+\)", "(drill 0)", pcb)
    return sch, pcb


MUTANTS = {
    "erc_unconnected_pin": m_erc_unconnected_pin,
    "erc_power_short": m_erc_power_short,
    "netlist_mismatch": m_netlist_mismatch,
    "drc_unconnected": m_drc_unconnected,
    "drc_short": m_drc_short,
    "outline_open": m_outline_open,
    "drill_no_tools": m_drill_no_tools,
}


def main():
    good, outdir = sys.argv[1], sys.argv[2]
    sch0 = open(os.path.join(good, SCH)).read()
    pcb0 = open(os.path.join(good, PCB)).read()
    for name, fn in MUTANTS.items():
        dst = os.path.join(outdir, name)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(good, dst)
        sch, pcb = fn(sch0, pcb0)
        open(os.path.join(dst, SCH), "w").write(sch)
        open(os.path.join(dst, PCB), "w").write(pcb)
        print(name)
    print(f"{len(MUTANTS)} mutants written to {outdir}")


if __name__ == "__main__":
    main()
