#!/usr/bin/env python3
"""Record the reference GPU lease stack to judge/version-table.json.

Called by setup.sh --record only. Leases a fresh 4 GiB slice, queries its
tool versions with one exec, pins the result under judge/, and destroys the
lease (confirming with GET -> 404). Never accepts a truncated answer.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _grade import GpuLease  # noqa: E402

JOB = """
import json, sys, platform
import numpy as np
import mujoco
import importlib.metadata as md
mj_cv = tuple(int(x) for x in mujoco.__version__.split('.') if x.isdigit())
report['versions'] = {
    'name': 'gpu-lease',
    'accel': 'RTX 5090 VRAM slice',
    'os': platform.platform(),
    'python': sys.version.split()[0],
    'mujoco': mujoco.__version__,
    'mujoco_warp': md.version('mujoco-warp'),
    'warp': md.version('warp-lang'),
    'numpy': np.__version__,
    'mujoco_cv': list(mj_cv),
    'custom_fields': {},
}
"""


def main():
    key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
    if not key:
        print("record_lease.py: export SBX_API_KEY first", file=sys.stderr)
        sys.exit(2)
    lease = GpuLease(key)
    try:
        lease.create()
        print(f"record_lease.py: leased {lease.id}", flush=True)
        rep = lease.exec(JOB)
        versions = rep["versions"]
    finally:
        lease.close()
        print(f"record_lease.py: lease {lease.id or '(unknown)'} destroyed and confirmed", flush=True)
    table = {"gpu": versions}
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version-table.json")
    with open(out, "w") as fh:
        json.dump(table, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"record_lease.py: wrote {out}")
    print(json.dumps(versions, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
