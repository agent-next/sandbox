#!/usr/bin/env python3
"""Generate single-edit known-bad mutants of examples/good/.

Each mutant copies examples/good/ into a fresh directory and makes exactly
one edit.  Profile edits change one setting; G-code edits change one class of
movement.  G-code mutants diverge from what the profile slices, so they also
fail `artifact_matches_profile`; the self-test additionally requires each to
fail the behavioural gate named below.

Usage: mutants.py <outdir>
"""

import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
GOOD = os.path.join(DEMO, "examples", "good")

# name -> (kind, edit description, gates that must fail)
MUTANTS = [
    ("filament-diameter-2.85", "profile", "filament_diameter = 2.85",
     ["volume_matches_model"]),
    ("petg-temps", "profile", "nozzle_temperature = 240", ["pla_temperatures"]),
    ("layer-height-0.35", "profile", "layer_height = 0.35", ["layer_z_sequence"]),
    ("scale-off-bed", "gcode", "X moves shifted +150",
     ["moves_inside_bed", "moves_near_part"]),
    ("first-layer-z-zero", "gcode", "first layer extrudes at Z0",
     ["layer_z_sequence"]),
    ("relative-e-mixup", "gcode", "M83 inserted mid-print",
     ["volume_matches_model"]),
    ("infill-100", "profile", "sparse_infill_density = 100",
     ["volume_matches_model", "profile_contract"]),
    ("nozzle-cold", "gcode", "first M109 S170", ["pla_temperatures"]),
    ("bed-heats-late", "gcode", "bed heat commands moved after first extrusion",
     ["pla_temperatures"]),
    ("travel-cuts-part", "gcode", "extruding move 60 mm outside footprint+brim",
     ["moves_near_part"]),
]


def read_profile():
    with open(os.path.join(GOOD, "profile.ini")) as fh:
        return fh.read()


def edit_profile(old, newline):
    """Insert/replace `key` line; fail loudly if the key is already there."""
    key = newline.split("=")[0].strip()
    out, n = re.subn(r"(?m)^%s\s*=.*$" % re.escape(key), newline.strip(), old)
    if n == 0:
        return old + newline + "\n"
    return out


def read_gcode():
    with open(os.path.join(GOOD, "part.gcode")) as fh:
        return fh.read()


def edit_gcode(name, text):
    lines = text.splitlines()
    out = list(lines)
    if name == "scale-off-bed":
        for i, ln in enumerate(lines):
            if re.match(r"^G[01]\s", ln) and "X" in ln and "E" in ln:
                out[i] = re.sub(r"X([-\d.]+)",
                                lambda m: "X%.3f" % (float(m.group(1)) + 200.0),
                                ln)
    elif name == "first-layer-z-zero":
        # The first layer's Z is set by a bare move (G1 Z.2) right before
        # extrusion starts; force THAT move to Z0 so the nozzle is buried
        # in the bed on layer 1.  (Skip E-negatives: those are retracts.)
        for i, ln in enumerate(lines):
            if re.match(r"^G[01]\s", ln) and re.search(r"\bE[\d.]", ln) \
                    and not re.search(r"\bE-", ln):
                for j in range(i - 1, -1, -1):
                    if re.match(r"^G[01]\s", lines[j]) and \
                            re.search(r"\bZ[-\d.]", lines[j]):
                        out[j] = re.sub(r"Z[-\d.]+", "Z0.000", lines[j],
                                        count=1)
                        break
                break
    elif name == "relative-e-mixup":
        # insert M83 right after the first G1 ... E move begins a new extrusion
        for i, ln in enumerate(lines):
            if re.match(r"^G[01]\s", ln) and re.search(r"\bE\d", ln):
                out.insert(i + 1, "M83")
                break
    elif name == "nozzle-cold":
        for i, ln in enumerate(lines):
            if re.match(r"^M109\b", ln):
                out[i] = re.sub(r"S[\d.]+", "S170", ln)
                break
    elif name == "bed-heats-late":
        # move all M140/M190 lines to after the first extruding move
        bed = [ln for ln in lines if re.match(r"^M(140|190)\b", ln)]
        rest = [ln for ln in lines if not re.match(r"^M(140|190)\b", ln)]
        for i, ln in enumerate(rest):
            if re.match(r"^G[01]\s.*E[+\-\d.]", ln):
                out = rest[:i] + bed + rest[i:]
                break
    elif name == "travel-cuts-part":
        # append a 60mm-outside-brim extruding move right before end G-code
        tail = "; HEADER_BLOCK_END"
        for i, ln in enumerate(lines):
            if ln.startswith("M84"):
                out.insert(i, "G1 X200 Y200 E10 F1800")
                break
    else:
        raise SystemExit("unknown gcode mutant: %s" % name)
    return "\n".join(out) + "\n"


def main():
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    prof = read_profile()
    gc = read_gcode()
    manifest = {}
    for name, kind, _desc, gates in MUTANTS:
        d = os.path.join(outdir, name)
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)
        if kind == "profile":
            with open(os.path.join(d, "profile.ini"), "w") as fh:
                fh.write(edit_profile(prof, _desc))
            shutil.copy(os.path.join(GOOD, "part.gcode"),
                        os.path.join(d, "part.gcode"))
        else:
            shutil.copy(os.path.join(GOOD, "profile.ini"),
                        os.path.join(d, "profile.ini"))
            with open(os.path.join(d, "part.gcode"), "w") as fh:
                fh.write(edit_gcode(name, gc))
        manifest[name] = gates
        print("wrote %s" % d)
    # manifest: selftest.sh checks each declared target gate actually fires
    import json
    with open(os.path.join(outdir, "mutants.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)


if __name__ == "__main__":
    main()
