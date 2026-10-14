#!/usr/bin/env python3
"""Regenerate requirements-cpu.lock / requirements-cuda.lock (sha256 pins).

Usage:  python3 judge/genlock.py

Wheel hashes are fetched live from the PyPI JSON API and, for the +cpu torch
builds, from the PyTorch wheel index. Only wheels usable on x86-64 Linux
CPython 3.10-3.13 plus pure wheels are listed, so `pip --require-hashes`
stays exact on the supported platforms (the judge's setup.sh refuses to run
elsewhere).

The date rule from the cookbook standard applies: every pin predates
2026-09-30 (nothing published in the two weeks before this demo was built).
Where pip would resolve something newer (filelock, MarkupSafe,
cuda-pathfinder), the pin below is the newest compatible older release; the
judge never upgrades past the pin because every transitive package is
pinned in full.
"""

import json
import re
import sys
import urllib.request

CUTOFF = "2026-09-30"          # date rule: no release published after this
CPS = ("cp310", "cp311", "cp312", "cp313")
PYPI = "https://pypi.org/pypi/{}/json"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu/torch/"

# name -> (version, cpu?)   cpu? marks packages needed only by the CUDA lock
PINS = [
    ("torch", "2.14.0", None),          # 2.14.0 on PyPI / 2.14.0+cpu on the pytorch index
    ("triton", "3.8.0", "both"),
    ("numpy", "2.4.3", "both"),
    ("filelock", "4.0.6", "both"),      # date rule: pip would pick 4.1.1 (2026-10-11)
    ("typing-extensions", "4.16.0", "both"),
    ("setuptools", "84.0.0", "both"),
    ("sympy", "1.14.0", "both"),
    ("networkx", "3.7", "both"),
    ("jinja2", "3.1.6", "both"),
    ("markupsafe", "3.0.3", "both"),    # date rule: pip would pick 3.0.4 (2026-10-02)
    ("mpmath", "1.3.0", "both"),
    ("fsspec", "2026.9.0", "both"),
    ("cuda-toolkit", "13.0.3.0", "cuda"),
    ("cuda-bindings", "13.4.3", "cuda"),
    ("cuda-pathfinder", "1.8.2", "cuda"),  # date rule: pip would pick 1.8.3 (2026-10-02)
    ("nvidia-cublas", "13.1.1.3", "cuda"),
    ("nvidia-cuda-cupti", "13.0.85", "cuda"),
    ("nvidia-cuda-nvrtc", "13.0.88", "cuda"),
    ("nvidia-cuda-runtime", "13.0.96", "cuda"),
    ("nvidia-cudnn-cu13", "9.24.0.43", "cuda"),
    ("nvidia-cufft", "12.0.0.61", "cuda"),
    ("nvidia-cufile", "1.15.1.6", "cuda"),
    ("nvidia-curand", "10.4.0.35", "cuda"),
    ("nvidia-cusolver", "12.0.4.66", "cuda"),
    ("nvidia-cusparse", "12.6.3.3", "cuda"),
    ("nvidia-cusparselt-cu13", "0.8.1", "cuda"),
    ("nvidia-nccl-cu13", "2.30.7", "cuda"),
    ("nvidia-nvjitlink", "13.4.92", "cuda"),
    ("nvidia-nvshmem-cu13", "3.4.5", "cuda"),
    ("nvidia-nvtx", "13.0.85", "cuda"),
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
    if "py3-none" in filename:
        return True
    return any(cp in filename for cp in CPS) and "cp313t" not in filename \
        and "cp315" not in filename


def check_date(name, version, files):
    if not files:
        raise SystemExit(f"{name} {version}: no usable wheel found")
    # upload dates are per distribution, not per wheel; PyPI JSON has them
    # on each file entry
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


def torch_cpu_lines():
    """Lock lines for torch 2.14.0+cpu from the pytorch index.

    pip's --require-hashes mode refuses local-version pins resolved from an
    index (`torch==2.14.0+cpu` — it demands hashes for the bare 2.14.0
    too), so each supported CPython gets a direct wheel URL with an
    environment marker and its own sha256. Verified to work with pip's
    --require-hashes mode.
    """
    page = get(TORCH_CPU_INDEX)
    lines = []
    for m in re.finditer(
            r'torch-2\.14\.0%2Bcpu-(cp31[0-3])-cp31[0-3]-manylinux_2_28_x86_64\.whl'
            r'#sha256=([0-9a-f]{64})', page):
        cp, sha = m.group(1), m.group(2)
        pyver = f"{cp[2]}.{cp[3:]}"        # cp310 -> 3.10
        lines.append(
            f'torch @ https://download.pytorch.org/whl/cpu/'
            f'torch-2.14.0%2Bcpu-{cp}-{cp}-manylinux_2_28_x86_64.whl'
            f' ; python_version == "{pyver}" --hash=sha256:{sha}')
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
    cpu_pkgs, cuda_pkgs = [], []
    for name, version, where in PINS:
        if name == "torch":
            continue                # handled per-lock below
        hashes, all_files = pypi_hashes(name, version)
        check_date(name, version,
                   [u for u in all_files if usable(u["filename"])])
        if where in ("both", "cuda"):
            cuda_pkgs.append((name, version, hashes))
        if where == "both":
            cpu_pkgs.append((name, version, hashes))

    torch_lines = torch_cpu_lines()
    if len(torch_lines) != 4:
        raise SystemExit(f"torch 2.14.0+cpu: expected 4 cp310-cp313 wheels, got {len(torch_lines)}")
    cuda_pkgs.insert(0, ("torch", "2.14.0",
                        pypi_hashes("torch", "2.14.0")[0]))

    here = __file__.rsplit("/", 1)[0]
    with open(f"{here}/requirements-cpu.lock", "w") as lock:
        print("## generated by judge/genlock.py -- pip install --require-hashes",
              file=lock)
        print("## torch 2.14.0+cpu: one pinned wheel URL per CPython", file=lock)
        for line in torch_lines:
            print(line, file=lock)
        emit(lock, cpu_pkgs)
    with open(f"{here}/requirements-cuda.lock", "w") as lock:
        print("## generated by judge/genlock.py -- pip install --require-hashes",
              "--index-url https://pypi.org/simple", file=lock)
        emit(lock, cuda_pkgs)
    print(f"cpu lock:  {len(cpu_pkgs)} packages")
    print(f"cuda lock: {len(cuda_pkgs)} packages")


if __name__ == "__main__":
    main()
