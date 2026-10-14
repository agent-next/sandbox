#!/usr/bin/env python3
"""result.png -- real UART transcript beside the 8-gate table.

Left:  the first lines of the real UART0 session in QEMU (from
       media/data/uart-good.json, captured with the judge's driver);
       elided lines are marked with an explicit count.
Right: the eight gates with the measured values read out of
       media/data/verdict-good.json, plus the flash/SRAM usage parsed
       from media/data/size-good.txt and firmware-good.map.
Bottom: the 61 real transactions as a coverage bar -- all matched.
"""

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, GATES, C_PASS, C_FAIL, C_TX, C_RX, C_BG,
                    C_DIM, load_verdict, load_uart, load_sizes,
                    flash_sram_bytes, check_no_overlap, check_inside_axes)

MONO = "DejaVu Sans Mono"

GATE_RULES = {
    "build_clean":  "gcc -Wall -Werror: exit 0, stderr empty",
    "elf_ok":       "e_machine ARM, ET_EXEC, entry in .text",
    "maps_ok":      ".text+.rodata <= 8192 B",
    "boot":         "banner <= BOOT_S (10 s), no fault, still running",
    "shell":        "every response == known-answer mask, in order",
    "crc_oracle":   "all 15 CRC-32 == zlib.crc32 (seed 20260814)",
    "no_hardfault": "0 fault strings on the wire",
    "judge_intact": "sha256(judge/) unchanged",
}


def main():
    verdict = load_verdict("good")
    uart = load_uart("good")
    sizes, regions = load_sizes()
    flash_b, sram_b = flash_sram_bytes(sizes)
    flash_lim = regions["FLASH"]["length"]
    sram_lim = regions["SRAM"]["length"]
    text_ro = sizes[".text"]["size"] + sizes.get(".rodata", {"size": 0})["size"]
    boot_t = next(e["t"] for e in uart["events"]
                  if e["dir"] == "rx")

    fig = plt.figure(figsize=(16, 9), dpi=200, facecolor="#ffffff")
    fig.suptitle("firmware-qemu: the real QEMU UART session, judged",
                 fontsize=17, fontweight="bold", x=0.5, y=0.975)

    # ======================= left: terminal ===========================
    ax = fig.add_axes([0.025, 0.115, 0.55, 0.80])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    header1 = ax.text(0.0, 0.975, "UART0 transcript -- real capture "
            "(media/data/uart-good.json)", fontsize=10, color="#30363d",
            transform=ax.transAxes, va="top", fontweight="bold")
    ax.add_patch(FancyBboxPatch((0, 0), 1, 0.94, boxstyle="round,pad=0.008",
                                fc=C_BG, ec="#30363d", lw=1.2,
                                transform=ax.transAxes, clip_on=False))
    header2 = ax.text(0.025, 0.905, "qemu-system-arm -M lm3s6965evb -serial stdio "
            "-kernel build/firmware.elf", family=MONO, fontsize=8.5,
            color=C_DIM, transform=ax.transAxes, va="top")

    # Terminal rows: banner + first N exchanges, then an explicit elision.
    events = uart["events"]
    pairs = []
    cur_tx = None
    for e in events:
        if e["dir"] == "tx":
            cur_tx = e["line"]
        elif cur_tx is not None:
            pairs.append((cur_tx, e["line"], e["t"]))
            cur_tx = None

    shown_pairs = 12                     # 24 lines + banner + elision note
    rows = [("rx", events[0]["line"], events[0]["t"])]
    for tx, rx, t in pairs[:shown_pairs]:
        rows.append(("tx", "> " + tx, None))
        rows.append(("rx", rx, t))
    elided = len(pairs) - shown_pairs
    # Wrap the elision message to fit inside the panel
    rows.append(("dim", "... %d further exchanges elided -- "
                 "all %d scripted + %d CRC matched"
                 % (elided, uart["result"]["shell_total"],
                    uart["result"]["crc_total"]), None))
    rows.append(("dim", "    full session scrolls in demo.mp4", None))

    y = 0.858
    dy = 0.0305
    term_texts = []
    for kind, line, t in rows:
        color = {"rx": C_RX, "tx": C_TX, "dim": C_DIM}[kind]
        term_texts.append(ax.text(0.03, y, line, family=MONO, fontsize=9.2,
                                  color=color, transform=ax.transAxes,
                                  va="top"))
        y -= dy
    # session clock in the corner -- from real capture timestamps
    clock = ax.text(0.97, 0.905, "t=%.3fs" % events[-1]["t"], family=MONO,
            fontsize=8.5, color=C_DIM, transform=ax.transAxes,
            va="top", ha="right")
    footer = ax.text(0.03, 0.012,
            "tx = line the judge writes  -  rx = firmware UART0 output  "
            "-  no echo on this wire", family=MONO, fontsize=7.6,
            color=C_DIM, transform=ax.transAxes, va="bottom")

    # Panel bounds check for terminal panel
    all_term_texts = term_texts + [header1, header2, clock, footer]
    check_inside_axes(fig, ax, all_term_texts, "result.png terminal panel")

    # ==================== right: gate table ==========================
    ax2 = fig.add_axes([0.60, 0.30, 0.375, 0.62])
    ax2.set_xlim(0, 1); ax2.set_ylim(0, 1); ax2.axis("off")
    ax2.text(0.0, 0.98, "gate table -- measured values from "
             "media/data/verdict-good.json", fontsize=10,
             fontweight="bold", color="#30363d", va="top",
             transform=ax2.transAxes)

    y = 0.91
    dy = 0.112
    gate_texts = []
    for gate in GATES:
        g = verdict["gates"][gate]
        ok = g["verdict"] == "pass"
        detail = g["detail"]
        if gate == "boot":
            detail = "banner at %.3fs (BOOT_S 10s)" % boot_t
        ax2.add_patch(Rectangle((0.865, y - 0.028), 0.13, 0.062,
                               fc=C_PASS if ok else C_FAIL, ec="none",
                               transform=ax2.transAxes))
        gate_texts.append(ax2.text(0.93, y + 0.003, g["verdict"].upper(), family=MONO,
                 fontsize=9, color="white", fontweight="bold",
                 ha="center", va="center", transform=ax2.transAxes))
        gate_texts.append(ax2.text(0.0, y + 0.018, gate, family=MONO, fontsize=10.5,
                 fontweight="bold", color="#1a1a1a",
                 va="center", transform=ax2.transAxes))
        gate_texts.append(ax2.text(0.0, y - 0.022, "measured: %s" % detail, family=MONO,
                 fontsize=8.6, color="#1a1a1a", va="center",
                 transform=ax2.transAxes))
        gate_texts.append(ax2.text(0.0, y - 0.055, "rule: %s" % GATE_RULES[gate],
                 family=MONO, fontsize=7.8, color=C_DIM, va="center",
                 transform=ax2.transAxes))
        # separator BELOW the rule text with clear padding
        ax2.plot([0.0, 1.0], [y - 0.073, y - 0.073], color="#d0d7de",
                 lw=0.8, transform=ax2.transAxes)
        y -= dy

    check_no_overlap(fig, gate_texts, "result.png gate table rows")

    # ============ right-bottom: maps_ok pass-line bar + memory =========
    ax3 = fig.add_axes([0.60, 0.115, 0.375, 0.16])
    ax3.set_xlim(0, 1); ax3.set_ylim(0, 1); ax3.axis("off")
    ax3.text(0.0, 1.0, "maps_ok pass line -- size vs the 8192 B rule",
             fontsize=10, fontweight="bold", color="#30363d", va="top",
             transform=ax3.transAxes)
    # bar: used .text+.rodata against the 8192 B limit (the pass line)
    bx, bw = 0.02, 0.72
    ax3.add_patch(Rectangle((bx, 0.52), bw, 0.16, fc="#eaeef2", ec="#d0d7de",
                            transform=ax3.transAxes))
    ax3.add_patch(Rectangle((bx, 0.52), bw * text_ro / 8192.0, 0.16,
                            fc=C_PASS, ec="none", transform=ax3.transAxes))
    ax3.plot([bx + bw, bx + bw], [0.48, 0.72], color=C_FAIL, lw=2.2,
             transform=ax3.transAxes)
    ax3.text(bx + bw * text_ro / 8192.0 + 0.012, 0.60,
             ".text+.rodata = %d B" % text_ro, family=MONO, fontsize=8.6,
             color="#1a1a1a", va="center", transform=ax3.transAxes)
    ax3.text(bx + bw - 0.008, 0.42, "pass limit 8192 B", family=MONO,
             fontsize=8.2, color=C_FAIL, ha="right", va="top",
             transform=ax3.transAxes)
    ax3.text(0.0, 0.30,
             "build/firmware.map + arm-none-eabi-size:",
             family=MONO, fontsize=8.6, color=C_DIM, va="center",
             transform=ax3.transAxes)
    ax3.text(0.0, 0.17,
             "FLASH %d/%d B (%.1f%%)    SRAM %d/%d B (%.1f%%)"
             % (flash_b, flash_lim, 100.0 * flash_b / flash_lim,
                sram_b, sram_lim, 100.0 * sram_b / sram_lim),
             family=MONO, fontsize=8.8, color="#1a1a1a", va="center",
             transform=ax3.transAxes)
    ax3.text(0.0, 0.02,
             "verdict: %s -- %d/%d gates  -  seed %d  -  grade.sh elapsed %ss"
             % ("PASS" if verdict["pass"] else "FAIL",
                verdict["gates_passed"], verdict["gates_total"],
                verdict["seed"], verdict["timing"]["elapsed_s"]),
             family=MONO, fontsize=9, fontweight="bold",
             color=C_PASS if verdict["pass"] else C_FAIL, va="center",
             transform=ax3.transAxes)

    # ================= bottom: full-session coverage bar ==============
    ax4 = fig.add_axes([0.025, 0.015, 0.95, 0.065])
    ax4.set_xlim(0, len(pairs)); ax4.set_ylim(0, 1); ax4.axis("off")
    script_n = uart["result"]["shell_total"]
    fails = {f["line"] for f in uart["result"]["shell_failures"]}
    cfails = {f["expect"] for f in uart["result"]["crc_failures"]}
    for i, (tx, rx, t) in enumerate(pairs):
        bad = (tx in fails) or (rx in cfails)
        ax4.add_patch(Rectangle((i + 0.06, 0.06), 0.88, 0.55,
                                fc=C_FAIL if bad else C_PASS, ec="none"))
    ax4.text(0, 0.85,
             "all %d UART transactions (left-to-right: %d scripted shell + "
             "%d seeded CRC) -- one tick per exchange; none failed"
             % (len(pairs), script_n, uart["result"]["crc_total"]),
             fontsize=8.6, color="#30363d", transform=ax4.transAxes)

    fig.text(0.025, 0.093,
             "Caption: left column is the real wire (same QEMU argv, pty and "
             "seed as judge/drive.py; elision marked). "
             "Right column: each gate's rule from SPEC.md with the value the "
             "judge measured. The red rule line on the size bar is the "
             "maps_ok pass threshold.", fontsize=8, color="#57606a")

    check_no_overlap(fig, term_texts, "result.png terminal rows")

    out = os.path.join(os.path.dirname(DATA), "result.png")
    fig.savefig(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
