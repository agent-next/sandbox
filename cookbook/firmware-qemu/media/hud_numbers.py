#!/usr/bin/env python3
"""Write media/video/numbers.json from THIS run's judge output.

The video composition reads every number it shows from this file
(hyperframes render --variables-file), so nothing on screen is typed by
hand: the gate counts come from the verdict JSON, the memory figures from
the build's linker map, the mutant kill rate from the self-test log.

Usage:
    hud_numbers.py [--out PATH]

Refuses to write a file with a placeholder value: a number it cannot
measure is a number the video must not show.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
DATA = os.path.join(HERE, "data")
CLIPS = os.path.join(HERE, "clips")


def die(msg):
    sys.exit("numbers.py: %s" % msg)


def load_verdict(path):
    with open(path) as fh:
        v = json.load(fh)
    return {
        "gates": v["gates_total"],
        "gatesPassed": v["gates_passed"],
        "seed": v["seed"],
        "rows": [
            # (gate, measured detail from the verdict JSON, pass)
            (name, g["detail"], g["verdict"] == "pass")
            for name, g in sorted(v["gates"].items())
        ],
    }


def load_build_memory(cast):
    """FLASH/SRAM *used* bytes from the real `make` output in build.cast.

    `make` prints its `-Wl,--print-memory-usage` block:

        Memory region         Used Size  Region Size  %age Used
                 FLASH:        2744 B       256 KB      1.05%
                  SRAM:        4456 B        64 KB      6.80%

    Parsing the recording rather than a data file means the number on
    screen is the one the toolchain printed in this run.
    """
    import json
    used = {}
    plain = []
    with open(cast) as fh:
        fh.readline()
        for line in fh:
            line = line.strip()
            if not line:
                continue
            _t, kind, data = json.loads(line)
            if kind == "o":
                plain.append(data)
    text = "".join(plain)
    for m in re.finditer(r"^\s*(FLASH|SRAM):\s+(\d+) B\s+(\d+) KB",
                         text, re.M):
        used[m.group(1)] = {"used": int(m.group(2)),
                            "total": int(m.group(3)) * 1024}
    return used


def load_text_rodata(verdict):
    """.text + .rodata bytes, the maps_ok gate's own measured number.

    The verdict's maps_ok detail is the authoritative string for it
    (".text+.rodata=2224B <= 8192B"); parsing it keeps the HUD number the
    one the judge checked, not a second reading of the map.
    """
    used = None
    for _, detail, _ in verdict["rows"]:
        m = re.match(r"^\.text\+\.rodata=(\d+)B", detail)
        if m:
            used = int(m.group(1))
    return used


def load_selftest(path):
    """The mutant table and the kill rate from the recorded self-test."""
    killed = total = 0
    rate = None
    for line in open(path):
        m = re.match(r"^mutants killed\s*:\s*(\d+)/(\d+)", line)
        if m:
            killed, total = int(m.group(1)), int(m.group(2))
        m = re.match(r"^kill rate\s*:\s*(\d+) %", line)
        if m:
            rate = int(m.group(1))
    return {"killed": killed, "total": total, "rate": rate}


def load_shell_counts(verdict):
    """The shell/CRC counts parsed out of the verdict's own detail strings."""
    shell = crc = None
    for _, detail, _ in verdict["rows"]:
        m = re.match(r"(\d+)/(\d+) exact responses", detail)
        if m:
            shell = (int(m.group(1)), int(m.group(2)))
        m = re.match(r"(\d+)/(\d+) match zlib\.crc32", detail)
        if m:
            crc = (int(m.group(1)), int(m.group(2)))
    return shell, crc


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=os.path.join(DATA, "..", "video",
                                                  "numbers.json"))
    args = ap.parse_args()

    verdict = load_verdict(os.path.join(DATA, "verdict-good.json"))
    # The memory numbers come from the build the footage shows: the
    # `make` output recorded in media/clips/build.cast.
    mem = load_build_memory(os.path.join(CLIPS, "build.cast"))
    selftest = load_selftest(os.path.join(DATA, "selftest.log"))
    shell, crc = load_shell_counts(verdict)
    text_rodata = load_text_rodata(verdict)

    if not mem.get("FLASH") or not mem.get("SRAM"):
        die("no FLASH/SRAM memory-usage block in %s/build.cast" % CLIPS)
    if not shell or not crc:
        die("could not parse shell/CRC counts from the verdict")
    if not selftest["total"] or selftest["rate"] is None:
        die("no kill rate in %s/selftest.log" % DATA)
    if text_rodata is None:
        die("no .text+.rodata size in the verdict's maps_ok detail")

    numbers = {
        "seed": verdict["seed"],
        "gates": verdict["gates"],
        "gatesPassed": verdict["gatesPassed"],
        "shellPassed": shell[0], "shellTotal": shell[1],
        "crcPassed": crc[0], "crcTotal": crc[1],
        "flash": mem["FLASH"]["used"], "flashTotal": mem["FLASH"]["total"],
        "sram": mem["SRAM"]["used"], "sramTotal": mem["SRAM"]["total"],
        "mutantsKilled": selftest["killed"],
        "mutantsTotal": selftest["total"],
        "killRate": selftest["rate"],
        "textRodata": text_rodata,
        "gateRows": [{"name": n, "detail": d, "pass": p}
                     for n, d, p in verdict["rows"]],
    }
    out = os.path.abspath(args.out)
    with open(out, "w") as fh:
        json.dump(numbers, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("hud_numbers.py: wrote %s" % out)
    print("  gates      %d/%d" % (numbers["gatesPassed"], numbers["gates"]))
    print("  shell      %d/%d" % (numbers["shellPassed"], numbers["shellTotal"]))
    print("  crc        %d/%d" % (numbers["crcPassed"], numbers["crcTotal"]))
    print("  flash/sram %d/%d  %d/%d"
          % (numbers["flash"], numbers["flashTotal"],
             numbers["sram"], numbers["sramTotal"]))
    print("  mutants    %d/%d  %d%%"
          % (numbers["mutantsKilled"], numbers["mutantsTotal"],
             numbers["killRate"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
