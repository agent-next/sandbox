"""Benign: burn about 0.3 s of CPU and finish, printing a fixed line.

Proves the CPU limit does not kill honest work that stays under it. The
output is a constant: the number of iterations depends on the machine, so
printing it would make the judge's exact-output oracle meaningless.
"""

import sys
import time

start = time.process_time()
total = 0
while time.process_time() - start < 0.3:
    total += 1
sys.stdout.write("bounded cpu work finished\n")
