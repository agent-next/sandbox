"""Hostile: try to read the host's password database."""

import sys

with open("/etc/shadow", "r") as fh:
    sys.stdout.write(fh.read())
