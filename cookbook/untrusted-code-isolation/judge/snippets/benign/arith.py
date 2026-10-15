"""Benign: print a small computed table."""

import sys

for n in range(1, 6):
    sys.stdout.write("%d squared is %d\n" % (n, n * n))
