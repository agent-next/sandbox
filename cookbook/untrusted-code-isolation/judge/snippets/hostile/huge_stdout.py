"""Hostile: flood stdout with 256 MiB."""

import sys

chunk = b"A" * (1024 * 1024)
for _ in range(256):
    sys.stdout.buffer.write(chunk)
    sys.stdout.buffer.flush()
sys.stdout.write("done\n")
