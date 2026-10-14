#!/usr/bin/env python3
"""Capture the real UART transcript of a firmware ELF inside QEMU.

This is the same session the judge drives: it imports judge/drive.py and
reuses its Session/pty machinery, the same QEMU command line, the same
command script (judge/spec.json) and the same seed.  The only difference
is that every command sent and every response line received is recorded
with a timestamp, so media/ can replay the wire.

Usage:
    capture.py <elf> <out.json> [--seed N] [--boot-s S] [--shell-s S]

Writes JSON: {artifact, qemu argv, seed, events:[{t,dir,line}], result}
where `result` is the same session verdict object drive.py prints.
"""

import json
import os
import pty
import random
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(DEMO, "judge"))
import drive  # noqa: E402  -- the judge's own driver

MAX_ARG_BYTES = drive.MAX_ARG_BYTES


def main():
    argv = sys.argv[1:]
    elf, out_path = argv[0], argv[1]
    seed = 20260814
    boot_s, shell_s = 10.0, 30.0
    i = 2
    while i < len(argv):
        if argv[i] == "--seed":
            seed = int(argv[i + 1]); i += 2
        elif argv[i] == "--boot-s":
            boot_s = float(argv[i + 1]); i += 2
        elif argv[i] == "--shell-s":
            shell_s = float(argv[i + 1]); i += 2
        else:
            raise SystemExit("unknown arg %r" % argv[i])

    spec_path = os.path.join(DEMO, "judge", "spec.json")
    with open(spec_path) as fh:
        spec = json.load(fh)

    qemu_argv = ["qemu-system-arm", "-M", "lm3s6965evb", "-cpu", "cortex-m3",
                 "-nographic", "-monitor", "none", "-serial", "stdio",
                 "-kernel", elf]

    mfd, sfd = pty.openpty()
    proc = subprocess.Popen(qemu_argv, stdin=sfd, stdout=sfd,
                            stderr=subprocess.DEVNULL, close_fds=True)
    os.close(sfd)
    drive.quiet(mfd)

    t0 = time.monotonic()
    events = []
    saw_fault = False
    boot_ok = False
    shell_failures = []
    crc_failures = []

    def note(direction, line):
        events.append({"t": round(time.monotonic() - t0, 3),
                       "dir": direction, "line": line})

    def check_fault(line):
        nonlocal saw_fault
        if drive.FAULT_RE.search(line.encode("utf-8", "replace")):
            saw_fault = True

    try:
        sess = drive.Session(mfd)

        # --- boot banner -------------------------------------------------
        deadline = time.monotonic() + boot_s
        while time.monotonic() < deadline:
            got = sess.line(0.5)
            if got is None:
                continue
            note("rx", got)
            check_fault(got)
            if spec["banner"] in got:
                boot_ok = True
                break

        session_end = time.monotonic() + shell_s

        def transact(line):
            remaining = session_end - time.monotonic()
            if remaining <= 0:
                return None
            note("tx", line)
            sess.drain(0.05)
            os.write(sess.fd, (line + "\r\n").encode())
            got = sess.line(remaining)
            if got is not None:
                note("rx", got)
            return got

        for entry in spec["commands"]:
            got = transact(entry["line"])
            if got is None:
                shell_failures.append({"line": entry["line"],
                                       "expect": entry["expect"],
                                       "got": "<no response>"})
                continue
            check_fault(got)
            if got != entry["expect"]:
                shell_failures.append({"line": entry["line"],
                                       "expect": entry["expect"],
                                       "got": got})

        rng = random.Random(seed)
        cases = [b"123456789", b"\x00" * MAX_ARG_BYTES, b"\xff" * MAX_ARG_BYTES]
        cases += [bytes(rng.randrange(256)
                        for _ in range(rng.randint(1, MAX_ARG_BYTES)))
                  for _ in range(12)]
        import zlib
        for data in cases:
            want = "OK 0x%08x" % zlib.crc32(data)
            got = transact("CRC " + data.hex())
            if got is None:
                crc_failures.append({"bytes": data.hex()[:48], "expect": want,
                                     "got": "<no response>"})
                continue
            check_fault(got)
            if got != want:
                crc_failures.append({"bytes": data.hex()[:48], "expect": want,
                                     "got": got})
    finally:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        os.close(mfd)

    result = {
        "boot_ok": boot_ok,
        "saw_fault": saw_fault,
        "shell_total": len(spec["commands"]),
        "shell_failed": len(shell_failures),
        "shell_ok": not shell_failures,
        "shell_failures": shell_failures,
        "crc_total": len(cases),
        "crc_failed": len(crc_failures),
        "crc_ok": not crc_failures,
        "crc_failures": crc_failures,
    }

    doc = {
        "note": ("Real UART transcript: same QEMU argv, pty discipline, "
                 "command script (judge/spec.json) and seed as the judge's "
                 "drive.py, whose Session class this script reuses. "
                 "dir=tx lines are the commands the judge sends; dir=rx "
                 "lines are the firmware's UART0 output."),
        "elf": os.path.relpath(elf),
        "qemu": qemu_argv,
        "spec": os.path.relpath(spec_path),
        "seed": seed,
        "boot_s": boot_s,
        "shell_s": shell_s,
        "events": events,
        "result": result,
    }
    with open(out_path, "w") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    print("wrote %s  events=%d  boot_ok=%s  shell %d/%d  crc %d/%d"
          % (out_path, len(events), boot_ok,
             result["shell_total"] - result["shell_failed"],
             result["shell_total"],
             result["crc_total"] - result["crc_failed"],
             result["crc_total"]))
    return 0 if (boot_ok and not shell_failures and not crc_failures) else 1


if __name__ == "__main__":
    sys.exit(main())
