#!/usr/bin/env python3
"""Generate the known-bad artifacts the self-test uses.

Each mutant is the good firmware with exactly one line edited, so a mutant
that fails is evidence the judge can see that class of defect -- and nothing
else.  Edits are keyed by a unique substring of the target line rather than by
line number, so the generator survives reasonable edits to the good source.

Usage:
    mutants.py list                     print the mutant names
    mutants.py make <name> <dest>       write one mutant tree to <dest>
    mutants.py make-all <destdir>       write every mutant tree
"""

import os
import re
import shutil
import sys

GOOD = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    os.pardir, "examples", "good")


def edit(text, needle, replacement, required=True):
    """Replace the single occurrence of `needle` with `replacement`.

    `needle` may span several lines.  Fails loudly if it matches zero times, or
    more than once: a silently half-applied mutant is worse than no mutant.
    """
    hits = text.count(needle)
    if hits == 0:
        if required:
            raise SystemExit("mutant edit failed: no match for %r" % needle)
        return text
    if hits > 1:
        raise SystemExit("mutant edit failed: %d matches for %r"
                         % (hits, needle))
    return text.replace(needle, replacement, 1)


def edit_line(text, needle, replacement, required=True):
    """Replace the one line containing `needle`, keeping the line's indent
    for a replacement that is given without any."""
    lines = text.split("\n")
    hits = [i for i, line in enumerate(lines) if needle in line]
    if len(hits) == 0:
        if required:
            raise SystemExit("mutant edit failed: no line contains %r" % needle)
        return text
    if len(hits) > 1:
        raise SystemExit("mutant edit failed: %d lines contain %r"
                         % (len(hits), needle))
    lines[hits[0]] = replacement
    return "\n".join(lines)


def drop(text, needle):
    """Delete the single line containing `needle`."""
    lines = text.split("\n")
    hits = [i for i, line in enumerate(lines) if needle in line]
    if len(hits) != 1:
        raise SystemExit("mutant drop failed: %d lines contain %r"
                         % (len(hits), needle))
    del lines[hits[0]]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# One function per mutant.  Each takes the good source of the files it touches,
# keyed by filename, and returns the edited bytes.
# --------------------------------------------------------------------------
def m_ring_off_by_one(f):
    """Full-ring test uses > instead of >=, so a full ring never drops and
    `RB push` reports a count above the capacity."""
    s = f["ring.c"]
    return {"ring.c": edit(s, "if (r->count >= r->cap) {",
                           "    if (r->count > r->cap) {")}


def m_ring_keeps_newest(f):
    """On overflow the ring keeps the newest byte and drops the oldest from
    the wrong end, so `RB dump` reports bytes in the wrong order."""
    s = f["ring.c"]
    return {"ring.c": edit(s, "        r->head = (r->head + 1u) % r->cap;",
                           "        r->tail = (r->tail + r->cap - 1u) % r->cap;")}


def m_ring_count_off_by_two(f):
    """Count bookkeeping drifts, so `RB count` is wrong from the first push."""
    s = f["ring.c"]
    return {"ring.c": edit(s, "    r->count++;",
                           "    r->count += 2;")}


def m_crc_poly(f):
    """Wrong polynomial: every CRC value is simply wrong.

    The needle includes the old value, so the replacement is a whole
    well-formed #define -- this mutant compiles cleanly and only the
    crc_oracle gate can see it."""
    s = f["crc.c"]
    return {"crc.c": edit(s, "#define CRC32_POLY   0xEDB88320u",
                          "#define CRC32_POLY   0x82F63B78u")}


def m_crc_no_xorout(f):
    """Final XOR removed: right value, wrong answer."""
    s = f["crc.c"]
    return {"crc.c": edit(s, "    return crc ^ CRC32_XOROUT;",
                          "    return crc;")}


def m_crc_init(f):
    """Zero initial value instead of all-ones.  Compiles cleanly; the
    zlib oracle is what kills it."""
    s = f["crc.c"]
    return {"crc.c": edit(s, "#define CRC32_INIT   0xFFFFFFFFu",
                          "#define CRC32_INIT   0x00000000u")}


def m_crc_shift_dir(f):
    """Shifts the wrong way, so the register never converges to the right
    answer.  A right shift with a non-reflected poly never lands on zlib."""
    s = f["crc.c"]
    return {"crc.c": edit(s, "                crc = (crc >> 1) ^ CRC32_POLY;",
                          "                crc = (crc << 1) ^ CRC32_POLY;")}


def m_uart_no_init(f):
    """uart_init returns before touching the hardware, so nothing is ever
    transmitted and the boot banner never appears."""
    s = f["uart.c"]
    body = s.index("void uart_init(void)")
    body = s.index("{", body) + 1
    return {"uart.c": s[:body] + "\n    return;\n" + s[body:]}


def m_uart_rx_inverted(f):
    """The receive-FIFO-empty flag is tested the wrong way round, so
    rx_fill() drains bytes only when the FIFO is empty and drops real
    input.  The shell never sees a correct line.

    This replaces a mutant that cleared CTL_RXE: QEMU's pl011 model does
    not gate reception on the RXE control bit, so that mutant answered
    every command correctly -- an equivalent mutant, invisible to any
    behavioural gate."""
    s = f["uart.c"]
    return {"uart.c": edit(s, "        if (UART_FR & FR_RXFE) {",
                           "        if (!(UART_FR & FR_RXFE)) {")}


def m_shell_unknown_ok(f):
    """Unknown commands report success instead of `ERR unknown`, so the
    known-answer mask disagrees with the firmware."""
    s = f["shell.c"]
    # the final `else` is the catch-all for anything unrecognised
    tail = s.rindex('    } else {\n        p = out_str(p, end, "ERR unknown");\n    }')
    return {"shell.c": s[:tail] + s[tail:].replace(
        '"ERR unknown"', '"OK unknown"', 1)}


def m_shell_bad_hex_accepted(f):
    """Bad hex arguments are accepted, so `CRC abc` returns a bogus value."""
    s = f["shell.c"]
    return {"shell.c": edit(s, "        if (hi < 0 || lo < 0) {\n"
                           "            return -1;\n        }",
                           "        if (hi < 0 || lo < 0) {\n"
                           "            hi = 0;\n            lo = 0;\n        }")}


def m_startup_no_reset(f):
    """The reset vector points at Default_Handler, so the CPU lands in an
    empty loop and the banner is never printed.

    This replaces a `.bss`-not-zeroed mutant: QEMU zeroes the emulated
    SRAM at reset, so skipping the clear loop produced a firmware that
    behaved identically -- an equivalent mutant."""
    s = f["startup.c"]
    return {"startup.c": edit(s, "    Reset_Handler,            /*  1 reset */",
                              "    Default_Handler,          /*  1 reset */")}


def m_startup_bad_sp(f):
    """The initial stack pointer in vector slot 0 is zero, so the first
    stack use faults and the boot banner never appears.

    This replaces a `.data`-not-copied mutant: the reference firmware has
    an empty `.data` section, so skipping the copy loop changed nothing
    observable -- an equivalent mutant."""
    s = f["startup.c"]
    return {"startup.c": edit(s, "    (vector_fn)&_estack,      /*  0 initial stack pointer */",
                              "    (vector_fn)0,             /*  0 initial stack pointer */")}


def m_build_broken(f):
    """A syntax error: the build gate must reject it and report exit code."""
    s = f["main.c"]
    return {"main.c": edit(s, "void kernel_main(void)",
                           "void kernel_main(void)\n#if 0")}


# name -> (mutator, which gates it is meant to break, one-line description)
MUTANTS = {
    "ring-off-by-one": (m_ring_off_by_one, "shell",
                        "full-ring test uses > instead of >="),
    "ring-drop-newest": (m_ring_keeps_newest, "shell",
                         "overflow drops from the wrong end of the ring"),
    "ring-count-drift": (m_ring_count_off_by_two, "shell",
                         "ring count advances by two on every push"),
    "crc-poly": (m_crc_poly, "crc_oracle", "wrong CRC polynomial"),
    "crc-no-xorout": (m_crc_no_xorout, "crc_oracle",
                      "final CRC XOR-out removed"),
    "crc-init": (m_crc_init, "crc_oracle", "CRC initial value is zero"),
    "crc-shift-dir": (m_crc_shift_dir, "crc_oracle",
                      "CRC register shifts the wrong way"),
    "uart-no-init": (m_uart_no_init, "boot",
                     "uart_init returns before enabling the UART"),
    "uart-rx-inverted": (m_uart_rx_inverted, "shell",
                         "FIFO-empty flag tested the wrong way"),
    "shell-unknown-ok": (m_shell_unknown_ok, "shell",
                         "unknown commands answer OK instead of ERR"),
    "shell-bad-hex-accepted": (m_shell_bad_hex_accepted, "shell",
                               "bad hex arguments accepted"),
    "startup-no-reset": (m_startup_no_reset, "boot",
                         "reset vector points at Default_Handler"),
    "startup-bad-sp": (m_startup_bad_sp, "boot",
                       "initial stack pointer is zero"),
    "build-broken": (m_build_broken, "build_clean",
                     "syntax error: will not compile"),
}


def make(name, dest):
    """Write the mutant `name` as a full artifact tree at `dest`."""
    if name not in MUTANTS:
        raise SystemExit("no mutant named %r (have: %s)"
                         % (name, ", ".join(sorted(MUTANTS))))
    mutator, _gates, _why = MUTANTS[name]

    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(GOOD, dest)
    # a mutant must never be graded by a judge it brought with it
    shutil.rmtree(os.path.join(dest, "build"), ignore_errors=True)

    names = sorted(n for n in os.listdir(GOOD)
                   if n.endswith((".c", ".h", ".ld")))
    sources = {}
    for n in names:
        with open(os.path.join(GOOD, n)) as fh:
            sources[n] = fh.read()

    edited = mutator(sources)
    for n, text in edited.items():
        with open(os.path.join(dest, n), "w") as fh:
            fh.write(text)
    return dest


def main(argv):
    if len(argv) < 2 or argv[1] not in ("list", "make", "make-all"):
        print(__doc__.strip())
        return 2

    if argv[1] == "list":
        for name in sorted(MUTANTS):
            print("%-24s %s" % (name, MUTANTS[name][2]))
        return 0

    if argv[1] == "make":
        if len(argv) != 4:
            print("usage: mutants.py make <name> <dest>")
            return 2
        print(make(argv[2], argv[3]))
        return 0

    dest_root = argv[2] if len(argv) > 2 else "/tmp/fq-mutants"
    made = []
    for name in sorted(MUTANTS):
        made.append(make(name, os.path.join(dest_root, name)))
    print("\n".join(made))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
