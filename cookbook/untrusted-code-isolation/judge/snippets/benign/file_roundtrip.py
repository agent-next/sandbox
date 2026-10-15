"""Benign: write a file inside the workdir and read it back."""

import os
import sys

with open("roundtrip.txt", "w") as fh:
    fh.write("payload-42\n")
with open("roundtrip.txt", "r") as fh:
    data = fh.read().strip()
sys.stdout.write("roundtrip %s size %d\n" % (data, os.path.getsize("roundtrip.txt")))
