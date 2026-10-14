#!/usr/bin/env python3
"""Shared $readmemh-style memory image helpers for the fpga-agent-loop judge.

Format: whitespace-separated tokens. "@<hex>" sets the word address,
any other token is a 32-bit word stored at the current word address.
Files produced by the judge always start at word 0 and are dense.
"""

MEM_WORDS = 64 * 1024 // 4  # flat 64 KiB RAM, one entry per 32-bit word


def parse_memh(text):
    """Parse memh text into a list of MEM_WORDS ints (zero-filled)."""
    words = [0] * MEM_WORDS
    addr = 0
    for tok in text.split():
        if tok.startswith("@"):
            addr = int(tok[1:], 16)
        else:
            if 0 <= addr < MEM_WORDS:
                words[addr] = int(tok, 16) & 0xFFFFFFFF
            addr += 1
    return words


def load_memh(path):
    with open(path) as f:
        return parse_memh(f.read())


def dump_memh(words, path):
    with open(path, "w") as f:
        f.write("@0\n")
        for w in words:
            f.write("%08x\n" % (w & 0xFFFFFFFF))


def words_to_memh(words):
    return "@0\n" + "\n".join("%08x" % (w & 0xFFFFFFFF) for w in words) + "\n"


def bytes_to_words(data):
    """Convert little-endian bytes to a word list (padded to /4)."""
    data = bytearray(data)
    while len(data) % 4:
        data.append(0)
    return [int.from_bytes(data[i:i + 4], "little")
            for i in range(0, len(data), 4)]


def words_to_bytes(words):
    out = bytearray()
    for w in words:
        out += (w & 0xFFFFFFFF).to_bytes(4, "little")
    return bytes(out)
