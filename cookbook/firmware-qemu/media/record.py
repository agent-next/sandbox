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

After recording, the cast is *sanitised*: the host's checkout and toolchain
prefixes are rewritten to short paths, so a public repo never carries where
this particular machine happened to keep the files.  Sanitising touches
path text only -- every command, response byte and number the demo produced
is the real one, byte for byte.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import term  # noqa: E402

# The host prefixes this machine used, and what the public recording shows
# instead.  Both are real paths of this run; only the spelling changes.
PREFIXES = [
    (term.DEMO, "<demo>"),
    (os.path.join(os.path.expanduser("~"), ".firmware-qemu-tools"),
     "<tools>"),
    (os.path.expanduser("~"), "<home>"),
]


def sanitise(path):
    """Rewrite host path prefixes in the cast's recorded output events."""
    import json

    tmp = path + ".tmp"
    changed = 0
    with open(path) as src, open(tmp, "w") as dst:
        dst.write(src.readline())                       # header, verbatim
        for line in src:
            line = line.strip()
            if not line:
                continue
            t, kind, data = json.loads(line)
            if kind == "o":
                for old, new in PREFIXES:
                    if old and old != new and old in data:
                        data = data.replace(old, new)
                        changed += 1
            dst.write(json.dumps([t, kind, data]) + "\n")
    if changed:
        os.replace(tmp, path)
    else:
        os.remove(tmp)
    return changed


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
    if out_path != "-" and os.path.exists(out_path):
        n = sanitise(out_path)
        sys.stderr.write("record.py: %s sanitised (%d path prefixes)\n"
                         % (os.path.basename(out_path), n))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
