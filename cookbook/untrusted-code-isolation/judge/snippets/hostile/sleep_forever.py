"""Hostile: sleep for ten minutes, holding the slot."""

import sys
import time

sys.stdout.write("sleeping\n")
sys.stdout.flush()
time.sleep(600)
sys.stdout.write("woke up\n")
