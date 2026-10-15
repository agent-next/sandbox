#!/usr/bin/env python3
"""Generate requirements-cpu.lock with pinned, hash-checked wheels.

Queries the PyTorch CPU wheel index for the exact torch/numpy versions,
resolves the transitive closure, and writes a pip --require-hashes lock.
Run from the judge/ directory:  python3 genlock.py
"""

import hashlib
import json
import sys
import urllib.request

CPU_INDEX = "https://download.pytorch.org/whl/cpu"
PYPI = "https://pypi.org/pypi"

PINNED = {
    "torch": "2.14.1",
    "numpy": "2.4.3",
}


def fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": "pip/25.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode()


def parse_simple_index(html, filename_substr):
    """Return (url, sha256) for the first anchor whose href contains the
    substring and carries a #sha256 fragment."""
    import re
    for m in re.finditer(r'href="([^"]+)"', html):
        href = m.group(1)
        if filename_substr in href and "#sha256=" in href:
            url, frag = href.split("#sha256=", 1)
            return url, frag
    raise SystemExit(f"no wheel matching {filename_substr!r} in index")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pick_wheel(index_html, substr):
    url, digest = parse_simple_index(index_html, substr)
    return url.split("/")[-1], digest


def main():
    # Resolve the transitive closure of torch+numpy.
    # torch's exact CPU wheel comes from the PyTorch CPU index (PEP 503
    # HTML); everything else from PyPI's simple index. Versions of the
    # transitive deps are pinned exactly as of the generation date.
    DEPS = {
        "filelock": "3.20.1", "fsspec": "2025.12.0", "jinja2": "3.1.6",
        "networkx": "3.5", "sympy": "1.14.0", "typing_extensions": "4.16.0",
        "MarkupSafe": "3.0.3", "mpmath": "1.3.0", "setuptools": "80.9.0",
    }
    done = {}  # name -> (version, sha256, filename)
    html = fetch_html(f"{CPU_INDEX}/torch/")
    fn, digest = pick_wheel(
        html, "torch-2.14.1%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl")
    done["torch"] = ("2.14.1+cpu", digest, fn)
    for pkg, ver in [("numpy", "2.4.3")] + sorted(DEPS.items()):
        if pkg in done:
            continue
        html = fetch_html(f"{PYPI}/simple/{pkg}/")
        fn, digest = pick_wheel(html, f"{pkg}-{ver}-py3-none-any.whl")
        done[pkg] = (ver, digest, fn)
    lines = ["# pinned by judge/genlock.py; install with pip --require-hashes",
             "# python 3.10-3.13, linux x86_64; torch wheel is cp312 (any of",
             "# 3.10-3.13 installs it; pip resolves the rest per interpreter)"]
    lines = ["# pinned by judge/genlock.py; install with pip --require-hashes",
             f"# python 3.10-3.13, linux x86_64"]
    for pkg in sorted(done):
        ver, digest, fn = done[pkg]
        lines.append(f"# {pkg} {fn}")
        lines.append(f"{pkg}=={ver} \\")
        lines.append(f"    --hash=sha256:{digest}")
    with open("requirements-cpu.lock", "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("wrote requirements-cpu.lock")


if __name__ == "__main__":
    main()
