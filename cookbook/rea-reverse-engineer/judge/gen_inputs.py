#!/usr/bin/env python3
"""gen_inputs.py -- deterministic pseudo-random stdin inputs per target.

    gen_inputs.py <target> <seed> <count> <outdir>

Writes <count> files in <outdir>: in-00000.bin ... Each file is the exact
byte string fed to the target binary and to reimpl.py on stdin.  Output is a
pure function of (target, seed, count).
"""
import os
import random
import sys

ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def gen_checksum(rng):
    return bytes(rng.randrange(256) for _ in range(rng.randrange(0, 301)))


def proto_frame(rng, cmd=None, length=None):
    cmd = rng.randrange(256) if cmd is None else cmd
    ln = rng.randrange(0, 65) if length is None else length
    pay = bytes(rng.randrange(256) for _ in range(ln))
    chk = (cmd * 7 + ln * 3 + sum(b * (i + 1) for i, b in enumerate(pay))) & 0xFF
    return bytes([0xAA, cmd, ln]) + pay + bytes([chk])


def gen_proto(rng):
    r = rng.random()
    if r < 0.70:  # well-formed: 1-3 frames
        return b"".join(proto_frame(rng) for _ in range(rng.randrange(1, 4)))
    if r < 0.85:  # corrupted frame
        f = bytearray(proto_frame(rng))
        kind = rng.randrange(3)
        if kind == 0:
            f[0] = rng.choice([0x00, 0x55, 0xAB, 0xFF])  # bad sync
        elif kind == 1:
            del f[rng.randrange(3, len(f)) :]            # truncate
        else:
            f[-1] ^= 0xFF                                # bad check byte
        return bytes(f)
    # garbage
    return bytes(rng.randrange(256) for _ in range(rng.randrange(0, 41)))


def gen_keycheck(rng):
    if rng.random() < 0.5:
        k = [rng.choice(ALPHA) for _ in range(15)]
        s = "".join(k[:5]) + "-" + "".join(k[5:10]) + "-" + "".join(k[10:])
        return (s + "\n").encode()
    return (bytes(rng.randrange(32, 127)
                  for _ in range(rng.randrange(0, 31))) + b"\n")


GEN = {"checksum": gen_checksum, "proto": gen_proto, "keycheck": gen_keycheck}


def main():
    target, seed, count, outdir = sys.argv[1], int(sys.argv[2]), \
        int(sys.argv[3]), sys.argv[4]
    rng = random.Random("%s:%d" % (target, seed))
    os.makedirs(outdir, exist_ok=True)
    for i in range(count):
        with open(os.path.join(outdir, "in-%05d.bin" % i), "wb") as fh:
            fh.write(GEN[target](rng))


if __name__ == "__main__":
    main()
