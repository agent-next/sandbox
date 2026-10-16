#!/usr/bin/env python3
"""Record the real run for demo.mp4 into one asciicast per shot.

Every shot is a real invocation of the demo: firmware booting in QEMU, the
toolchain building it, the judge grading it, the judge killing 14 mutants.
Each mode writes its own bytes to the recording pty; the casts are then
replayed by media/term.py play to 30 fps frames.

Usage:
    record.py <phase> <cast>

`phase` is boot | build | grade | selftest.  Record under
    asciinema rec --command "record.py boot out.cast"
so the whole terminal session -- prompt, colours, cursor -- is captured.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import term  # noqa: E402


def main(argv):
    if len(argv) != 3:
        sys.stderr.write(__doc__)
        return 2
    phase, out_path = argv[1], argv[2]

    rc = 0
    if phase == "boot":
        elf = os.path.join(term.DEMO, "examples", "good", "build",
                           "firmware.elf")
        if not os.path.exists(elf):
            sys.stderr.write("record.py: %s missing; run make first\n" % elf)
            return 3
        rc = term.qemu_session(elf)
    elif phase == "build":
        rc = term.mode_build()
    elif phase == "grade":
        rc = term.mode_grade()
    elif phase == "selftest":
        rc = term.mode_selftest()
    else:
        sys.stderr.write("record.py: unknown phase %r\n" % phase)
        return 2
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
