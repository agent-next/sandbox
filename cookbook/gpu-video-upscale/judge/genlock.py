#!/usr/bin/env python3
"""Write the pinned, hash-checked pip locks the judge installs.

One lock per supported CPython, because both numpy and markupsafe publish
one platform wheel per interpreter tag:

    judge/requirements-cp311.lock     CPython 3.11
    judge/requirements-cp312.lock     CPython 3.12
    judge/requirements-cp313.lock     CPython 3.13

Each lock pins the exact wheel (torch from the PyTorch CPU index, the rest
from PyPI) with --hash=sha256:, so
`pip install --require-hashes -r requirements-cpXXX.lock` cannot install
anything else. setup.sh picks the lock matching the interpreter it runs
under. Run from anywhere:  python3 genlock.py
"""

import json
import re
import urllib.request

CPU_INDEX = "https://download.pytorch.org/whl/cpu"
PYPI_JSON = "https://pypi.org/pypi"

TORCH_VERSION = "2.14.1"
TORCH_PLUS = "2.14.1+cpu"
NUMPY_VERSION = "2.4.3"

# Supported interpreters. numpy has no cp310 wheel for 2.4.x, so 3.10 is
# not a supported judge interpreter.
INTERPRETERS = ("cp311", "cp312", "cp313")

# torch's transitive closure on this platform, exact versions.
DEPS = {
    "filelock": "3.20.1", "fsspec": "2025.12.0", "jinja2": "3.1.6",
    "networkx": "3.5", "sympy": "1.14.0", "typing_extensions": "4.16.0",
    "MarkupSafe": "3.0.3", "mpmath": "1.3.0", "setuptools": "80.9.0",
}


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "pip/25.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def pypi_wheel(pkg, ver, filename):
    """(filename, sha256) for exactly this file of exactly this release."""
    data = get_json(f"{PYPI_JSON}/{pkg}/{ver}/json")
    for entry in data["urls"]:
        if entry["filename"] == filename:
            digest = entry["digests"]["sha256"]
            if len(digest) != 64:
                raise SystemExit(f"{filename}: digest is not sha256")
            return filename, digest
    raise SystemExit(f"{pkg} {ver}: no file named {filename}")


def pytorch_wheel(filename):
    """(filename, sha256) from the PyTorch CPU index's PEP 503 page.

    The index keeps the filename in its href exactly as published (the
    '+' of the local version still percent-encoded), so match the encoded
    name and report the plain one.
    """
    plain = filename.replace("%2B", "+")
    req = urllib.request.Request(f"{CPU_INDEX}/torch/",
                                 headers={"User-Agent": "pip/25.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode()
    for href in re.findall(r'href="([^"]+)"', html):
        url, _, frag = href.partition("#sha256=")
        if not frag or url.rsplit("/", 1)[-1] != filename:
            continue
        if not re.fullmatch(r"[0-9a-f]{64}", frag):
            raise SystemExit(f"{plain}: advertised digest is not sha256")
        return plain, frag
    raise SystemExit(f"PyTorch CPU index has no wheel {plain}")


def wheels_for(tag):
    """The exact (name, version, filename, sha256) rows for one interpreter."""
    rows = [("torch", TORCH_PLUS, pytorch_wheel(
        f"torch-{TORCH_VERSION}%2Bcpu-{tag}-{tag}-manylinux_2_28_x86_64.whl"))]
    rows.append(("numpy", NUMPY_VERSION, pypi_wheel(
        "numpy", NUMPY_VERSION,
        f"numpy-{NUMPY_VERSION}-{tag}-{tag}-manylinux_2_27_x86_64."
        f"manylinux_2_28_x86_64.whl")))
    for pkg, ver in sorted(DEPS.items()):
        tagstem = tag if pkg == "MarkupSafe" else None
        if tagstem:
            fn = (f"{pkg}-{ver}-{tag}-{tag}-manylinux2014_x86_64."
                  f"manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl")
        else:
            fn = f"{pkg}-{ver}-py3-none-any.whl"
        rows.append((pkg, ver, pypi_wheel(pkg, ver, fn)))
    return rows


HEADER = [
    "# pinned by judge/genlock.py -- install with pip --require-hashes.",
    "# One exact wheel per line: torch (CPU index) and numpy plus torch's",
    "# transitive closure (PyPI). Do not edit by hand.",
]


def main():
    for tag in INTERPRETERS:
        lines = list(HEADER)
        for pkg, ver, (fn, digest) in wheels_for(tag):
            lines += [f"# {fn}", f"{pkg}=={ver} \\",
                      f"    --hash=sha256:{digest}"]
        path = f"requirements-{tag}.lock"
        with open(path, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
