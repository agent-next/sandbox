"""Hostile: allocate a gigabyte of resident memory."""

import sys

blob = bytearray(1024 * 1024 * 1024)
for i in range(0, len(blob), 4096):
    blob[i] = 1
sys.stdout.write("allocated %d bytes\n" % len(blob))
