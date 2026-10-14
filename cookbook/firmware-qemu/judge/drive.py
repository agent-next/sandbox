#!/usr/bin/env python3
"""Drive the firmware's UART inside QEMU and grade the transcript.

Usage: drive.py spec.json <elf> <machine> <boot_s> <shell_s> <seed>

Prints one line, `@@@RESULT@@@{...}`, carrying the session verdict.

The judge reads and writes a real pty whose slave end is QEMU's stdio, so the
bytes on the wire are exactly the firmware's UART0 traffic.  Responses are
consumed one line at a time from a running buffer, which keeps a slow reply
from being mistaken for the reply to the previous command.
"""

import json
import os
import pty
import random
import re
import select
import subprocess
import sys
import termios
import time
import zlib

FAULT_RE = re.compile(rb"HardFault|UsageFault|BusFault|MemManage")

# A command line is LINE_MAX bytes on the firmware side; keep every generated
# argument comfortably inside that, or the firmware will truncate it.
MAX_ARG_BYTES = 64


def quiet(mfd):
    """Stop the terminal from echoing, translating or post-processing bytes.

    The firmware echoes its own input; a line discipline that echoed too would
    put every keystroke back on the wire and corrupt the transcript.  Output
    translation is disabled so `\\n` stays `\\n` instead of becoming `\\r\\n`.
    """
    attrs = termios.tcgetattr(mfd)
    attrs[0] &= ~(termios.ICRNL | termios.INLCR | termios.IGNCR)
    attrs[3] &= ~(termios.ECHO | termios.ECHONL)
    attrs[1] &= ~termios.OPOST
    termios.tcsetattr(mfd, termios.TCSANOW, attrs)


class Session:
    """A pty reader with a running buffer and line-at-a-time semantics."""

    def __init__(self, mfd):
        self.fd = mfd
        self.buf = b""

    def _pump(self, seconds):
        """Read whatever is available for up to `seconds` into the buffer."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            ready, _, _ = select.select([self.fd], [], [], 0.05)
            if not ready:
                continue
            try:
                chunk = os.read(self.fd, 65536)
            except OSError:
                return False
            if not chunk:
                return False
            self.buf += chunk
            deadline = min(deadline, time.time() + 0.05)
        return True

    def line(self, timeout):
        """Return the next complete line, or None if `timeout` expires."""
        deadline = time.time() + timeout
        while True:
            idx = self.buf.find(b"\n")
            if idx >= 0:
                raw = self.buf[:idx]
                self.buf = self.buf[idx + 1:]
                return raw.rstrip(b"\r").decode("utf-8", "replace")
            if time.time() >= deadline:
                return None
            if not self._pump(0.1):
                return None

    def drain(self, seconds):
        """Discard anything already buffered, then wait out `seconds`."""
        self.buf = b""
        self._pump(seconds)

    def ask(self, command, expect, timeout):
        """Send `command`, return the first response line that arrives."""
        self.drain(0.05)
        os.write(self.fd, (command + "\r\n").encode())
        return self.line(timeout)


def main():
    spec_path, elf, machine = sys.argv[1:4]
    boot_s, shell_s, seed = float(sys.argv[4]), float(sys.argv[5]), int(sys.argv[6])

    with open(spec_path) as fh:
        spec = json.load(fh)

    mfd, sfd = pty.openpty()
    proc = subprocess.Popen(
        ["qemu-system-arm", "-M", machine, "-cpu", "cortex-m3",
         "-nographic", "-monitor", "none", "-serial", "stdio",
         "-kernel", elf],
        stdin=sfd, stdout=sfd, stderr=subprocess.DEVNULL, close_fds=True,
    )
    os.close(sfd)
    quiet(mfd)

    transcript = []
    saw_fault = False
    boot_ok = False
    shell_failures = []
    crc_failures = []

    try:
        sess = Session(mfd)

        # --- boot banner ---------------------------------------------------
        deadline = time.time() + boot_s
        while time.time() < deadline:
            got = sess.line(0.5)
            if got is None:
                continue
            transcript.append(got)
            if FAULT_RE.search(got.encode("utf-8", "replace")):
                saw_fault = True
            if spec["banner"] in got:
                boot_ok = True
                break

        # --- scripted command session -------------------------------------
        # SHELL_S budgets the whole session (scripted commands and the CRC
        # cases below share one deadline), not each line: a dead UART costs
        # one timeout total, not one timeout per command.
        session_end = time.time() + shell_s

        def transact(line, expect):
            remaining = session_end - time.time()
            if remaining <= 0:
                return None
            return sess.ask(line, expect, remaining)

        for entry in spec["commands"]:
            got = transact(entry["line"], entry["expect"])
            if got is None:
                # a command that gets no reply at all is a failure too
                shell_failures.append({
                    "line": entry["line"],
                    "expect": entry["expect"],
                    "got": "<no response>",
                })
                continue
            transcript.append(got)
            if FAULT_RE.search(got.encode("utf-8", "replace")):
                saw_fault = True
            if got != entry["expect"]:
                shell_failures.append({
                    "line": entry["line"],
                    "expect": entry["expect"],
                    "got": got,
                })

        # --- random CRC oracle, against Python's zlib ---------------------
        rng = random.Random(seed)
        cases = [b"123456789", b"\x00" * MAX_ARG_BYTES, b"\xff" * MAX_ARG_BYTES]
        cases += [bytes(rng.randrange(256)
                        for _ in range(rng.randint(1, MAX_ARG_BYTES)))
                  for _ in range(12)]
        for data in cases:
            want = "OK 0x%08x" % zlib.crc32(data)
            got = transact("CRC " + data.hex(), want)
            if got is None:
                crc_failures.append({"bytes": data.hex()[:48], "expect": want,
                                     "got": "<no response>"})
                continue
            transcript.append(got)
            if FAULT_RE.search(got.encode("utf-8", "replace")):
                saw_fault = True
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
        "shell_failures": shell_failures[:25],
        "crc_total": len(cases),
        "crc_failed": len(crc_failures),
        "crc_ok": not crc_failures,
        "crc_failures": crc_failures[:25],
        "transcript_head": " | ".join(transcript[:14]),
    }
    print("@@@RESULT@@@" + json.dumps(result))


if __name__ == "__main__":
    main()
