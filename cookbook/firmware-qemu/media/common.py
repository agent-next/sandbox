#!/usr/bin/env python3
"""Shared helpers for the firmware-qemu media figures.

Every number drawn by the figures is loaded here from a file the judge
(or a real tool invoked on a real build) wrote -- nothing is invented.
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DEMO = os.path.dirname(HERE)

GATES = ["build_clean", "elf_ok", "maps_ok", "boot", "shell",
         "crc_oracle", "no_hardfault", "judge_intact"]

MUTANTS = ["build-broken", "crc-init", "crc-no-xorout", "crc-poly",
           "crc-shift-dir", "ring-count-drift", "ring-drop-newest",
           "ring-off-by-one", "shell-bad-hex-accepted", "shell-unknown-ok",
           "startup-bad-sp", "startup-no-reset", "uart-no-init",
           "uart-rx-inverted"]

# Colour-blind-safe (Okabe-Ito).
C_PASS = "#009E73"
C_FAIL = "#D55E00"
C_BUILD = "#E69F00"   # build-only kill: visually distinct from behavioural
C_TX = "#56B4E9"
C_RX = "#7FDB8A"
C_BG = "#0d1117"
C_PANEL = "#161b22"
C_FG = "#e6edf3"
C_DIM = "#8b949e"


def load_verdict(name):
    path = os.path.join(DATA, "verdict-%s.json" % name)
    with open(path) as fh:
        return json.load(fh)


def load_uart(name):
    with open(os.path.join(DATA, "uart-%s.json" % name)) as fh:
        return json.load(fh)


def load_sizes():
    """Parse media/data/size-good.txt (real `arm-none-eabi-size -A` output)
    and media/data/firmware-good.map (real linker map)."""
    sizes = {}
    with open(os.path.join(DATA, "size-good.txt")) as fh:
        for line in fh:
            m = re.match(r"^(\.\S+)\s+(\d+)\s+(\d+)\s*$", line.strip())
            if m:
                sizes[m.group(1)] = {"size": int(m.group(2)),
                                     "addr": int(m.group(3))}
    regions = {}
    with open(os.path.join(DATA, "firmware-good.map")) as fh:
        in_cfg = False
        for line in fh:
            if line.startswith("Memory Configuration"):
                in_cfg = True
                continue
            if in_cfg:
                if line.startswith("Linker script"):
                    break
                m = re.match(r"^(\w+)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)",
                             line)
                if m:
                    regions[m.group(1)] = {"origin": int(m.group(2), 16),
                                           "length": int(m.group(3), 16)}
    return sizes, regions


def flash_sram_bytes(sizes):
    """Bytes the ELF occupies in each region: flash = alloc sections below
    0x20000000, sram = alloc sections at/above it.  Only loadable sizes."""
    flash = sum(v["size"] for k, v in sizes.items()
                if v["addr"] < 0x20000000 and v["size"] > 0
                and not k.startswith(".debug") and k not in
                (".ARM.attributes", ".comment"))
    sram = sum(v["size"] for k, v in sizes.items()
               if v["addr"] >= 0x20000000 and v["size"] > 0)
    return flash, sram


def cell_short(detail):
    """Compress a gate detail string to fit a matrix cell."""
    m = re.match(r"(\d+) of (\d+) responses wrong", detail)
    if m:
        return "%s/%s wrong" % (m.group(1), m.group(2))
    m = re.match(r"(\d+)/(\d+) exact responses", detail)
    if m:
        return "%s/%s exact" % (m.group(1), m.group(2))
    m = re.match(r"(\d+)/(\d+) match zlib", detail)
    if m:
        return "%s/%s = zlib" % (m.group(1), m.group(2))
    m = re.match(r"\.text\+\.rodata=(\d+)B <= (\d+)B", detail)
    if m:
        return "%s<=%sB" % (m.group(1), m.group(2))
    short = {"CRC disagrees with zlib": "!= zlib",
             "no ELF": "no ELF",
             "no ELF to size": "no ELF",
             "make exited 2": "make exit 2",
             "build/firmware.elf missing": "no ELF",
             "skipped": "skipped",
             "no diagnostics": "clean",
             "judge checksum unchanged": "unchanged",
             "no fault strings in UART output": "0 faults"}
    if detail in short:
        return short[detail]
    m = re.match(r"banner within (\d+)s", detail)
    if m:
        return "banner<=%ss" % m.group(1)
    m = re.match(r"no banner within (\d+)s", detail)
    if m:
        return "no banner %ss" % m.group(1)
    return detail[:14]


def check_no_overlap(fig, items, what):
    """Assert no two drawn elements' window-extent bboxes intersect.

    `items` is a list of matplotlib artists (Text or Rectangle) that must
    not overlap.  Raises RuntimeError -- make_media.sh treats any failure
    as fatal, so an overlapping figure can never be committed silently.
    """
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    boxes = []
    for art in items:
        bb = art.get_window_extent(renderer=rend)
        boxes.append(bb)
    fb = fig.bbox
    for i, bb in enumerate(boxes):
        if bb.x0 < fb.x0 - 1 or bb.x1 > fb.x1 + 1 or \
           bb.y0 < fb.y0 - 1 or bb.y1 > fb.y1 + 1:
            raise RuntimeError("%s: element %d escapes the figure" % (what, i))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes[i].overlaps(boxes[j]):
                raise RuntimeError(
                    "%s: elements %d and %d overlap" % (what, i, j))


def check_inside_panel(fig, items, what):
    """Assert every artist's window extent lies within the figure bounds.

    `items` is a list of matplotlib artists (Text, Rectangle, etc.) that must
    be fully inside the figure. Raises RuntimeError on any escape.
    """
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    fb = fig.bbox
    for i, art in enumerate(items):
        bb = art.get_window_extent(renderer=rend)
        if bb.x0 < fb.x0 - 1 or bb.x1 > fb.x1 + 1 or \
           bb.y0 < fb.y0 - 1 or bb.y1 > fb.y1 + 1:
            raise RuntimeError(
                "%s: element %d (%s) escapes figure bounds "
                "(bb: x0=%.1f x1=%.1f y0=%.1f y1=%.1f vs fb: x0=%.1f x1=%.1f y0=%.1f y1=%.1f)"
                % (what, i, type(art).__name__, bb.x0, bb.x1, bb.y0, bb.y1,
                   fb.x0, fb.x1, fb.y0, fb.y1))


def check_inside_axes(fig, axes, items, what):
    """Assert every artist's window extent lies within its axes panel.

    `axes` is the matplotlib Axes defining the panel bounds.
    `items` is a list of matplotlib artists that must be inside that axes.
    """
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    # Get axes bounds in figure pixels
    ax_bb = axes.get_window_extent(renderer=rend)
    for i, art in enumerate(items):
        bb = art.get_window_extent(renderer=rend)
        if bb.x0 < ax_bb.x0 - 1 or bb.x1 > ax_bb.x1 + 1 or \
           bb.y0 < ax_bb.y0 - 1 or bb.y1 > ax_bb.y1 + 1:
            raise RuntimeError(
                "%s: element %d (%s) escapes its panel "
                "(bb: x0=%.1f x1=%.1f y0=%.1f y1=%.1f vs ax: x0=%.1f x1=%.1f y0=%.1f y1=%.1f)"
                % (what, i, type(art).__name__, bb.x0, bb.x1, bb.y0, bb.y1,
                   ax_bb.x0, ax_bb.x1, ax_bb.y0, ax_bb.y1))
