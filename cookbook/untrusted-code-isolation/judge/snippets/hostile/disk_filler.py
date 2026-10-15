"""Hostile: fill the disk with 512 MiB of junk."""

import sys

chunk = b"j" * (1024 * 1024)
with open("filler.bin", "wb") as fh:
    for _ in range(512):
        fh.write(chunk)
        fh.flush()
sys.stdout.write("wrote 512 MiB\n")
