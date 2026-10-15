#!/usr/bin/env python3
"""Regenerate judge/requirements.txt (sha256-pinned) from the PyPI index.

Run once when a pin changes:
    python3 judge/genlock.py
The lock resolves the demo's direct pins plus every transitive dependency
pip would pull in, so `pip install --require-hashes` is exact and cannot
silently upgrade.  Wheels are listed for cp311 (the interpreter
judge/VERSIONS.txt records) and for pure-python wheels by their only file;
`pip --require-hashes` verifies against exactly one line per package.

The date rule from the cookbook standard applies: no pin published in the
two weeks before the demo was written (cutoff 2026-09-30).
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request

CUTOFF = "2026-09-30"
CP = "cp312"
PLATFORM_OK = ("manylinux", "manylinux_2_17", "manylinux_2_28", "linux")
PYPI = "https://pypi.org/pypi/{}/{}/json"

# (name, version) -- direct pins, in install order
DIRECT = [
    ("numpy", "2.5.4"),
    ("scipy", "1.18.1"),
    ("scikit-learn", "1.9.1"),
    ("pandas", "3.0.6"),
    ("matplotlib", "3.11.2"),
    ("nbclient", "0.11.0"),
    ("nbformat", "5.11.1"),
    ("nbconvert", "7.17.2"),
    ("ipykernel", "7.4.0"),
    ("jupyter_client", "8.10.0"),
    ("traitlets", "5.16.1"),
]


def fetch(name: str, version: str) -> dict:
    with urllib.request.urlopen(PYPI.format(name, version)) as fh:
        return json.load(fh)


def hashes(name: str, version: str) -> list[str]:
    data = fetch(name, version)
    rp = data["info"]["requires_python"] or ""
    if "3.12" not in rp and ">=3.10" not in rp:
        raise SystemExit(f"{name} {version}: requires_python {rp!r} "
                         f"excludes the pinned 3.12")
    for f in data["urls"]:
        if (f.get("upload_time_iso_8601") or "")[:10] > CUTOFF:
            raise SystemExit(f"{name} {version}: file {f['filename']} "
                             f"published after {CUTOFF}")
    out = []
    for f in data["urls"]:
        fn = f["filename"]
        if fn.endswith(".whl"):
            if fn.endswith("-any.whl") or fn.endswith("py3-none-any.whl"):
                out.append(f["digests"]["sha256"])
            elif f"{CP}-" in fn and "x86_64" in fn and any(
                    p in fn for p in PLATFORM_OK):
                out.append(f["digests"]["sha256"])
        elif fn.endswith(".tar.gz"):
            out.append(f["digests"]["sha256"])
    if not out:
        raise SystemExit(f"{name} {version}: no usable wheel found")
    return list(dict.fromkeys(f"sha256:{h}" for h in out))


def main() -> int:
    lines = []
    for name, version in DIRECT:
        hs = hashes(name, version)
        lines.append(f"{name}=={version} " +
                     " ".join(f"\\\n    --hash={h}" for h in hs))
        lines.append("")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
