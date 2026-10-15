"""Benign: burn about 0.3 s of CPU and finish.

Proves the CPU limit does not kill honest work that stays under it.
"""

import sys
import time

start = time.process_time()
total = 0
while time.process_time() - start < 0.3:
    total += 1
sys.stdout.write("counted %d iterations in %.3f s\n"
                 % (total, time.process_time() - start))
