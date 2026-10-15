#!/usr/bin/env python3
"""reimpl.py -- Python re-implementation of the stripped `proto` binary.

Recovered frame format: 0xAA <cmd> <len> <payload[len]> <chk>, len <= 64,
chk = (cmd*7 + len*3 + sum(payload[i]*(i+1))) & 0xFF.  Prints one line per
frame and a final DONE count; stops at the first bad frame.
"""
import sys

p = sys.stdin.buffer.read(1 << 20)
n = len(p)
off = 0
ok = 0
out = sys.stdout
while off < n:
    if p[off] != 0xAA:
        out.write("ERR %d sync\n" % off)
        break
    if off + 3 > n:
        out.write("ERR %d trunc\n" % off)
        break
    cmd = p[off + 1]
    ln = p[off + 2]
    if ln > 64 or off + 3 + ln + 1 > n:
        out.write("ERR %d trunc\n" % off)
        break
    chk = (cmd * 7 + ln * 3) & 0xFF
    for i in range(ln):
        chk = (chk + p[off + 3 + i] * (i + 1)) & 0xFF
    if p[off + 3 + ln] != chk:
        out.write("ERR %d chk\n" % off)
        break
    out.write("OK cmd=%02x len=%d chk=%02x\n" % (cmd, ln, chk))
    ok += 1
    off += 3 + ln + 1
out.write("DONE %d\n" % ok)
