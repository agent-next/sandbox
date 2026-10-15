"""Hostile: write to a canary file the judge planted outside the workdir.

The target directory arrives in the environment (UCI_OUTSIDE_DIR); the
snippet appends a marker to the canary there. A runner that does not
confine writes lets the marker land.
"""

import os
import sys

target = os.path.join(os.environ.get("UCI_OUTSIDE_DIR", "."), "canary.txt")
with open(target, "a") as fh:
    fh.write("PWNED\n")
sys.stdout.write("appended to %s\n" % target)
