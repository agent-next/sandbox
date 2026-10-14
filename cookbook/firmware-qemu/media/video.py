#!/usr/bin/env python3
"""demo.mp4 -- the judged UART session, replayed.

Scene 1  title card
Scene 2  the real UART transcript of examples/good in QEMU
         (media/data/uart-good.json; event order and relative pacing come
         from the capture timestamps, scaled for readability)
Scene 3  the crc-poly mutant, same driver and seed: the responses that
         disagree with the zlib oracle are drawn in red against the
         expected line
Scene 4  the verdicts: good 8/8, the replayed fix sequence from
         media/data/loop.json, and the self-test kill rate
Scene 5  end card

Frames are rendered headless with matplotlib to media/frames/ and encoded
by make_media.sh (lossless master -> H.264 web encode).
"""

import json
import os
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, GATES, C_PASS, C_FAIL, C_TX, C_RX,
                    C_BG, C_DIM, load_verdict, load_uart)

MONO = "DejaVu Sans Mono"
W, H, FPS = 1920, 1080, 30
MAXROWS = 22  # every rendered line counts, annotation sub-lines included

C_ERR = "#ff7b72"      # wrong response text
C_WANT = "#ffa657"     # expected-value annotation
C_HDR = "#c9d1d9"

# Maximum characters per line in the terminal box (approx 0.88 / 0.055 * font_size_ratio)
MAX_CHARS_PER_LINE = 85


# ----------------------------------------------------------------------
# scheduling: real capture timestamps, scaled; floors keep it readable
# ----------------------------------------------------------------------
def build_schedule(events, t0, scale, min_gap, collapse=1.4):
    """Display schedule from real capture timestamps.

    Inter-event gaps come from the capture, scaled by `scale`, floored at
    `min_gap` so lines stay readable.  A quiet stretch longer than
    `collapse` seconds (display time) is replaced by an explicit
    '· · ·' marker carrying the real skipped duration -- the wire
    timing is compressed, never invented.
    """
    items = []
    prev_real = None
    cur = t0
    for e in events:
        if prev_real is None:
            start = cur
        else:
            gap = (e["t"] - prev_real) * scale
            if gap > collapse:
                items.append({"t": cur, "dir": "dim",
                              "line": "· · ·  (+%.1fs quiet on the wire)"
                                      % (e["t"] - prev_real)})
                cur += 0.62
            start = max(prev_start + gap if gap <= collapse else cur,
                        cur)
        items.append({"t": start, "dir": e["dir"], "line": e["line"]})
        prev_start = start
        prev_real = e["t"]
        cur = start + min_gap
    return items


def terminal_frame(fig, items, t, title, bad=None, clock_t0=0.0):
    """Draw a scrolling terminal. `items` are scheduled events; an rx line
    whose text is in `bad` is drawn in red with its expected value.

    Every rendered line (including sub-lines and 'quiet on the wire' markers)
    counts toward MAXROWS so nothing overflows the box.
    Long lines are wrapped or truncated with '…' to stay inside the box width.
    """
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.add_patch(Rectangle((0, 0), 1, 1, fc=C_BG, ec="none"))

    # Terminal box bounds in axes coords
    BOX_X0, BOX_X1 = 0.055, 0.965
    BOX_Y0, BOX_Y1 = 0.065, 0.92
    ax.add_patch(FancyBboxPatch((BOX_X0 - 0.02, BOX_Y0 - 0.01), 0.93, 0.86,
                                boxstyle="round,pad=0.006",
                                fc="#010409", ec="#30363d", lw=1.4))
    ax.text(0.05, 0.945, title, family=MONO, fontsize=13, color=C_HDR,
            va="center", fontweight="bold")
    ax.text(0.95, 0.945, "session t=%5.1fs" % (t - clock_t0), family=MONO,
            fontsize=11, color=C_DIM, va="center", ha="right")

    # Build visual lines - each entry becomes 1 or 2 lines (with annotation)
    vis_lines = []  # list of (text, color, is_annotation)
    for it in items:
        if it["t"] > t:
            break
        if it["dir"] == "tx":
            n = min(len(it["line"]), int((t - it["t"]) * 45))
            txt = "> " + it["line"][:n]
            if n < len(it["line"]):
                txt += "_"
            # Truncate or wrap if too long
            if len(txt) > MAX_CHARS_PER_LINE:
                txt = txt[:MAX_CHARS_PER_LINE - 1] + "…"
            vis_lines.append((txt, C_TX, False))
        elif it["dir"] == "dim":
            # Wrap the quiet marker if needed
            txt = it["line"]
            if len(txt) > MAX_CHARS_PER_LINE:
                txt = txt[:MAX_CHARS_PER_LINE - 1] + "…"
            vis_lines.append((txt, C_DIM, False))
        else:
            col = C_RX
            txt = it["line"]
            if len(txt) > MAX_CHARS_PER_LINE:
                txt = txt[:MAX_CHARS_PER_LINE - 1] + "…"
            if bad and it["line"] in bad:
                col = C_ERR
                annot = "   != want: " + bad[it["line"]]
                if len(annot) > MAX_CHARS_PER_LINE:
                    annot = annot[:MAX_CHARS_PER_LINE - 1] + "…"
                vis_lines.append((txt, col, False))
                vis_lines.append((annot, C_WANT, True))
            else:
                vis_lines.append((txt, col, False))

    # Keep only the last MAXROWS lines (counting annotations as lines)
    vis_lines = vis_lines[-MAXROWS:]

    y = BOX_Y1 - 0.02
    dy = 0.0335
    for txt, col, is_annotation in vis_lines:
        if y < BOX_Y0 + dy:
            break  # stop if we'd draw below the box
        ax.text(BOX_X0, y, txt, family=MONO, fontsize=15,
                color=col, va="top")
        y -= dy
    return ax


def card_frame(fig, title, lines, foot=None):
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.add_patch(Rectangle((0, 0), 1, 1, fc=C_BG, ec="none"))
    ax.text(0.5, 0.62, title, family=MONO, fontsize=30, color=C_HDR,
            ha="center", va="center", fontweight="bold")
    y = 0.5
    for line, col, fs in lines:
        ax.text(0.5, y, line, family=MONO, fontsize=fs, color=col,
                ha="center", va="center")
        y -= 0.055
    if foot:
        ax.text(0.5, 0.16, foot, family=MONO, fontsize=13, color=C_DIM,
                ha="center", va="center")
    return ax


def verdict_frame(fig, t, t0, good, loop_doc, verdicts):
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.add_patch(Rectangle((0, 0), 1, 1, fc=C_BG, ec="none"))
    ax.text(0.5, 0.93, "the judge's verdicts -- from the saved grade JSON",
            family=MONO, fontsize=17, color=C_HDR, ha="center",
            va="center", fontweight="bold")

    # left: the good verdict
    x = 0.07
    ax.text(x, 0.85, "examples/good -- verdict-good.json", family=MONO,
            fontsize=15, color=C_HDR, fontweight="bold")
    ax.text(x, 0.80, "PASS  %d/%d gates   seed %d"
            % (good["gates_passed"], good["gates_total"], good["seed"]),
            family=MONO, fontsize=15, color=C_PASS, fontweight="bold")
    y = 0.74
    for g in GATES:
        if t - t0 < 0.35 * (GATES.index(g) + 1):
            break
        d = good["gates"][g]
        ax.text(x, y, "%-14s %s  %s" % (g, d["verdict"].upper(),
                                      d["detail"]),
                family=MONO, fontsize=12.5, color=C_RX, va="center")
        y -= 0.047

    # right: replayed fix sequence + kill rate
    x2 = 0.55
    ax.text(x2, 0.85, "replayed fix sequence -- loop.json", family=MONO,
            fontsize=15, color=C_HDR, fontweight="bold")
    ax.text(x2, 0.805, "(real verdicts reordered; not a live agent trace)",
            family=MONO, fontsize=11.5, color=C_DIM)
    y = 0.745
    for s in loop_doc["steps"]:
        v = verdicts[s["artifact"].replace("examples/", "")]
        failed = [k for k, g in v["gates"].items()
                  if g["verdict"] != "pass"]
        col = C_PASS if v["pass"] else C_FAIL
        detail = "all gates pass" if v["pass"] else \
            "fails: " + ", ".join(failed[:3]) + \
            (" ..." if len(failed) > 3 else "")
        ax.text(x2, y, "it %d  %-24s %d/8  %s"
                % (s["iteration"], s["artifact"], v["gates_passed"],
                   detail),
                family=MONO, fontsize=12.5, color=col, va="center")
        y -= 0.05
    y -= 0.03
    ax.text(x2, y, "self-test: 14/14 mutants killed = 13 behavioural "
            "+ 1 build-only", family=MONO, fontsize=13.5, color=C_HDR,
            va="center", fontweight="bold")
    ax.text(x2, y - 0.05, "behavioural kill rate 100% (floor 90%) -- "
            "media/data/selftest.log", family=MONO, fontsize=12,
            color=C_DIM, va="center")
    return ax


def main():
    good_uart = load_uart("good")
    mut_uart = load_uart("crc-poly")
    good = load_verdict("good")
    with open(os.path.join(DATA, "loop.json")) as fh:
        loop_doc = json.load(fh)
    verdicts = {"good": good}
    for s in loop_doc["steps"]:
        name = s["artifact"].replace("examples/", "")
        verdicts.setdefault(name, load_verdict(name))

    # mutant responses that disagree with the oracle: got -> expected
    bad = {}
    for f in mut_uart["result"]["shell_failures"]:
        bad[f["got"]] = f["expect"]
    for f in mut_uart["result"]["crc_failures"]:
        bad[f["got"]] = f["expect"]

    # ---- scene timings -------------------------------------------------
    T_TITLE0, T_TITLE1 = 0.0, 2.6
    good_sched = build_schedule(good_uart["events"], T_TITLE1 + 0.4,
                                scale=3.4, min_gap=0.13)
    T_GOOD1 = good_sched[-1]["t"] + 1.0

    # mutant scene: banner + HELP/VER/ID, then the first 8 exchanges
    # whose response disagrees with the oracle (each with its command)
    mut_events = mut_uart["events"]
    sel = list(mut_events[:7])
    for i, e in enumerate(mut_events):
        if e["dir"] == "rx" and e["line"] in bad:
            if i > 0 and mut_events[i - 1]["dir"] == "tx":
                sel.append(mut_events[i - 1])
            sel.append(e)
            if len([s for s in sel if s["dir"] == "rx"
                    and s["line"] in bad]) >= 8:
                break
    mut_sched = build_schedule(sel, T_GOOD1 + 1.6, scale=3.4, min_gap=0.40)
    T_MUT0, T_MUT1 = T_GOOD1 + 0.2, mut_sched[-1]["t"] + 1.3

    T_VERD0 = T_MUT1 + 0.3
    T_VERD1 = T_VERD0 + 6.8
    T_END = T_VERD1 + 2.0

    nframes = int(T_END * FPS)
    outdir = os.path.join(os.path.dirname(DATA), "frames")
    os.makedirs(outdir, exist_ok=True)

    mut_title = ("mutant crc-poly (0xEDB88320->0x82F63B78) -- real "
                 "capture, same driver+seed")
    good_title = ("qemu-system-arm -M lm3s6965evb -serial stdio -kernel "
                  "firmware.elf   [examples/good]")

    fig = plt.figure(figsize=(W / 100.0, H / 100.0), dpi=100)
    for f in range(nframes):
        t = f / float(FPS)
        fig.clf()
        fig.patch.set_facecolor(C_BG)
        if t < T_TITLE1:
            card_frame(fig, "firmware-qemu",
                       [("bare-metal C -> Cortex-M3 ELF -> QEMU "
                         "lm3s6965evb -> UART shell -> 8-gate judge",
                         C_HDR, 15),
                        ("everything below is a real captured session "
                          "or a saved verdict -- no illustrative data",
                          C_DIM, 13)],
                       foot="cookbook/firmware-qemu")
        elif t < T_MUT0:
            terminal_frame(fig, good_sched, t, good_title,
                           clock_t0=T_TITLE1 + 0.4)
        elif t < T_VERD0:
            terminal_frame(fig, mut_sched, t, mut_title, bad=bad,
                           clock_t0=T_GOOD1 + 1.6)
            if t < T_GOOD1 + 1.6:
                ax = fig.axes[0]
                ax.text(0.05, 0.875,
                        "same firmware, one line changed: the CRC-32 "
                        "polynomial", family=MONO, fontsize=14,
                        color=C_WANT, va="top")
        elif t < T_VERD1:
            verdict_frame(fig, t, T_VERD0, good, loop_doc, verdicts)
        else:
            card_frame(fig, "firmware-qemu",
                       [("judge: bash cookbook/firmware-qemu/judge/"
                         "selftest.sh", C_HDR, 14),
                        ("media:  bash cookbook/firmware-qemu/media/"
                         "make_media.sh", C_HDR, 14)],
                       foot="agent-next/sandbox cookbook demo")
        fig.savefig(os.path.join(outdir, "%05d.png" % f),
                    facecolor=C_BG)
        if f % 150 == 0:
            print("frame %d/%d" % (f, nframes), flush=True)
    print("wrote %d frames to %s (%.1fs @ %dfps)"
          % (nframes, outdir, T_END, FPS))


if __name__ == "__main__":
    main()
