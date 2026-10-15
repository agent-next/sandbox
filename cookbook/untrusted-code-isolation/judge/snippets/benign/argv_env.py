"""Benign: report what the runner handed it, without leaking the environment.

Prints only values the judge sets deliberately, never a dump of the host
environment.
"""

import os
import sys

sys.stdout.write("cwd is a directory: %s\n" % os.path.isdir(os.getcwd()))
sys.stdout.write("marker: %s\n" % os.environ.get("UCI_MARKER", "unset"))
sys.stdout.write("stdin is a tty: %s\n" % sys.stdin.isatty())
