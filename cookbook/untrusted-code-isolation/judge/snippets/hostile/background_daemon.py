"""Hostile: daemonize and outlive the job.

Forks, detaches from the controlling terminal with setsid, records its pid
and sleeps for five minutes. A runner that only waits for its direct child
leaves this process behind.
"""

import os
import sys
import time

pid = os.fork()
if pid == 0:
    os.setsid()
    with open("daemon.pid", "w") as fh:
        fh.write("%d\n" % os.getpid())
    time.sleep(300)
    os._exit(0)
sys.stdout.write("daemon child %d\n" % pid)
sys.stdout.flush()
time.sleep(1.0)
