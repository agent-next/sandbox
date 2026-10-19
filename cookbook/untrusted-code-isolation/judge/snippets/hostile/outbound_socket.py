"""Hostile: open outbound network connections.

Two targets. `UCI_NET_PROBE` is a host:port the judge is listening on, so
the judge itself is the oracle: it accepts or it does not. The public
address is the realistic egress attempt.
"""

import os
import socket
import sys

targets = [os.environ.get("UCI_NET_PROBE", "127.0.0.1:9"), "1.1.1.1:80"]
for target in targets:
    host, _, port = target.rpartition(":")
    try:
        conn = socket.create_connection((host, int(port)), timeout=3)
        conn.close()
        sys.stdout.write("CONNECTED %s\n" % target)
    except OSError as exc:
        sys.stdout.write("REFUSED %s (%s)\n" % (target, exc.errno))
sys.stdout.flush()
