#!/usr/bin/env python3
"""Regenerate requirements.lock (sha256 pins) for the judge venv.

Usage:  python3 judge/genlock.py

Wheel hashes are fetched live from the PyPI JSON API and, for the +cpu
torch/torchvision builds, from the PyTorch wheel index. Only wheels usable
on x86-64 Linux CPython 3.10-3.13 plus pure wheels are listed, so pip's
--require-hashes mode stays exact on the supported platforms (judge/setup.sh
refuses to run elsewhere).

Date rule from the cookbook standard: every pin predates 2026-10-01. Where
pip would resolve something newer (filelock, typer, hf-xet, wcwidth), the pin
is the newest compatible older release; every transitive package is pinned
in full so the judge never upgrades past a pin.
"""

import json
import re
import urllib.request

CUTOFF = "2026-09-30"          # date rule: no release published after this
CPS = ("cp310", "cp311", "cp312", "cp313")
PYPI = "https://pypi.org/pypi/{}/json"

# torch and torchvision are handled per-CPython from the PyTorch cpu index.
PINS = [
    ("open-clip-torch", "3.3.0"),      # CLIP ViT-B-32 judge oracle
    ("timm", "1.0.29"),
    ("huggingface-hub", "1.33.0"),
    ("safetensors", "0.8.0"),
    ("regex", "2026.9.10"),
    ("ftfy", "6.3.1"),
    ("wcwidth", "0.9.1"),              # date rule: pip would pick 0.9.2 (2026-10-05)
    ("tokenizers", "0.23.1"),          # transformers 5.17 needs >=0.23.1
    ("transformers", "5.17.0"),
    ("numpy", "2.4.3"),
    ("pillow", "11.3.0"),
    ("click", "8.5.0"),
    ("filelock", "4.0.6"),             # date rule: pip would pick 4.2.0 (2026-10-14)
    ("fsspec", "2026.9.0"),
    ("hf-xet", "1.6.0"),               # date rule: pip would pick 1.7.0 (2026-10-06)
    ("httpx", "0.28.1"),
    ("httpcore", "1.0.9"),
    ("h11", "0.16.0"),
    ("idna", "3.20"),
    ("certifi", "2026.7.22"),
    ("anyio", "4.15.1"),
    ("sniffio", "1.3.1"),
    ("packaging", "26.3"),
    ("pyyaml", "6.0.3"),
    ("tomli", "2.2.1"),                # huggingface-hub on CPython 3.10
    ("tqdm", "4.70.1"),
    ("typing-extensions", "4.16.0"),
    ("typer", "0.27.2"),               # date rule: pip would pick 0.27.3 (2026-10-06)
    ("shellingham", "1.5.4"),
    ("rich", "15.0.0"),
    ("markdown-it-py", "4.2.0"),
    ("mdurl", "0.1.2"),
    ("pygments", "2.21.0"),
    ("annotated-doc", "0.0.5"),
    ("setuptools", "84.0.0"),
    ("sympy", "1.14.0"),
    ("networkx", "3.7"),
    ("jinja2", "3.1.6"),
    ("markupsafe", "3.0.3"),           # date rule: pip would pick 3.0.4 (2026-10-02)
    ("mpmath", "1.3.0"),
]


def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read().decode()


def usable(filename):
    """x86-64 Linux wheels (cp310-cp313 or py3) and pure wheels only."""
    if "none-any" in filename:
        return True
    if "x86_64" not in filename or "aarch64" in filename:
        return False
    if "py3-none" in filename or "abi3" in filename:
        return True
    return any(cp in filename for cp in CPS) and "cp313t" not in filename \
        and "cp315" not in filename


def check_date(name, version, files):
    if not files:
        raise SystemExit(f"{name} {version}: no usable wheel found")
    dates = sorted({f["upload_time"][:10] for f in files})
    if dates[-1] > CUTOFF:
        raise SystemExit(
            f"{name} {version}: published {dates[-1]}, after the {CUTOFF} date rule")


def pypi_hashes(name, version):
    data = json.loads(get(PYPI.format(f"{name}/{version}")))
    files = [u for u in data["urls"] if usable(u["filename"])]
    if not files:
        raise SystemExit(f"{name} {version}: no usable wheel on PyPI")
    return sorted(u["digests"]["sha256"] for u in files), data["urls"]


def cpu_index_lines(pkg, version):
    """Lock lines for a +cpu build from the pytorch index, one per CPython.

    pip's --require-hashes mode refuses local-version pins resolved from an
    index (`torch==2.14.0+cpu` — it demands hashes for the bare 2.14.0 too),
    so each supported CPython gets a direct wheel URL with an environment
    marker and its own sha256. Verified to work with --require-hashes.
    """
    page = get(f"https://download.pytorch.org/whl/cpu/{pkg}/")
    lines = []
    pat = (rf'{pkg}-{version}%2Bcpu-(cp31[0-3])-cp31[0-3]-'
           r'manylinux_2_28_x86_64\.whl#sha256=([0-9a-f]{64})')
    for m in re.finditer(pat, page):
        cp, sha = m.group(1), m.group(2)
        pyver = f"{cp[2]}.{cp[3:]}"        # cp310 -> 3.10
        lines.append(
            f'{pkg} @ https://download.pytorch.org/whl/cpu/'
            f'{pkg}-{version}%2Bcpu-{cp}-{cp}-manylinux_2_28_x86_64.whl'
            f' ; python_version == "{pyver}" --hash=sha256:{sha}')
    if len(lines) != 4:
        raise SystemExit(f"{pkg} {version}+cpu: expected 4 wheels, got {len(lines)}")
    return lines


def emit(lock, packages):
    # pip ignores indented --hash continuation lines without a trailing
    # backslash; hashes must sit on the requirement's own line.
    for name, version, hashes in packages:
        line = f"{name}=={version}"
        for h in hashes:
            line += f" \\\n    --hash=sha256:{h}"
        print(line, file=lock)


def main():
    pkgs = []
    for name, version in PINS:
        hashes, all_files = pypi_hashes(name, version)
        check_date(name, version, [u for u in all_files if usable(u["filename"])])
        pkgs.append((name, version, hashes))

    here = __file__.rsplit("/", 1)[0]
    with open(f"{here}/requirements.lock", "w") as lock:
        print("## generated by judge/genlock.py -- pip install --require-hashes",
              file=lock)
        print("## torch/torchvision +cpu: one pinned wheel URL per CPython",
              file=lock)
        for pkg in ("torch", "torchvision"):
            for line in cpu_index_lines(pkg, "2.14.0" if pkg == "torch" else "0.29.0"):
                print(line, file=lock)
        emit(lock, pkgs)
    print(f"lock: {len(pkgs)} packages + torch + torchvision")


if __name__ == "__main__":
    main()
