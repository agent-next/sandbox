"""Hostile: fork resident children until the process table is full.

Children stay resident (they sleep instead of exiting, so they do not
turn into zombies the parent never reaps), and when the table is full the
parent backs off and keeps retrying for a while, the way a real bomb
does, before surfacing the failure. The plateau it reaches — the policy's
process cap, the host's inherited cap, or none at all — is what the
judge's process-count sampler measures while the run is in flight.
"""

import os
import time

full_for = 0.0
last = None
while full_for < 2.0:
    try:
        pid = os.fork()
    except OSError as exc:
        last = exc
        full_for += 0.1
        time.sleep(0.1)
        continue
    full_for = 0.0
    if pid == 0:
        time.sleep(300)
        os._exit(0)
raise last
