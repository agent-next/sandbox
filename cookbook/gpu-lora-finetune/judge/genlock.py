#!/usr/bin/env python3
"""Regenerate judge/requirements-cpu.lock (sha256 pins).

Usage:  python3 judge/genlock.py

The lock is the exact pip freeze of the judge venv built by setup.sh, with
the two platform markers made explicit:

* torch 2.14.0+cpu is resolved from the PyTorch CPU wheel index as one
  pinned direct URL per CPython (pip's --require-hashes mode refuses a
  local-version pin resolved from an index);
* the remaining packages are pure or x86-64-linux wheels pinned with
  sha256 from the PyPI JSON API, each checked against the date rule from
  the cookbook standard (no release published after CUTOFF).

Only wheels usable on x86-64 Linux CPython 3.10-3.13 are listed, so
`pip --require-hashes` stays exact on every platform setup.sh supports.
"""

import json
import re
import sys
import urllib.request

CUTOFF = "2026-09-30"          # date rule: no release published after this
CPS = ("cp310", "cp311", "cp312", "cp313")
PYPI = "https://pypi.org/pypi/{}/json"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu/torch/"

# Every package the judge venv installs, at the pinned version.
PINS = [
    ("torch", "2.14.0"),      # resolved from the CPU index, not PyPI
    ("transformers", "5.15.1"),
    ("tokenizers", "0.22.2"),
    ("peft", "0.21.1"),
    ("safetensors", "0.8.0"),
    ("accelerate", "1.15.0"),
    ("numpy", "2.4.3"),
    ("huggingface-hub", "1.33.0"),
    ("hf-xet", "1.7.0"),
    ("regex", "2026.9.29"),
    ("pyyaml", "6.0.3"),
    ("packaging", "26.3"),
    ("filelock", "4.0.6"),      # date rule: pip would pick 4.1.1 (2026-10-11)
    ("typing-extensions", "4.16.0"),
    ("tqdm", "4.70.1"),
    ("psutil", "7.2.2"),
    ("fsspec", "2026.9.0"),
    ("jinja2", "3.1.6"),
    ("markupsafe", "3.0.3"),    # date rule: pip would pick 3.0.4 (2026-10-02)
    ("networkx", "3.7"),
    ("sympy", "1.14.0"),
    ("mpmath", "1.3.0"),
    ("click", "8.5.0"),
    ("typer", "0.27.3"),
    ("shellingham", "1.5.4"),
    ("annotated-doc", "0.0.5"),
    ("rich", "15.0.0"),
    ("pygments", "2.21.0"),
    ("markdown-it-py", "4.2.0"),
    ("mdurl", "0.1.2"),
    ("httpcore", "1.0.9"),
    ("httpx", "0.28.1"),
    ("anyio", "4.15.1"),
    ("h11", "0.16.0"),
    ("certifi", "2026.7.22"),
    ("idna", "3.20"),
    ("setuptools", "84.0.0"),
    ("pip", "25.0.1"),
]

# The PyPI wheels these packages must be taken from (abi3/pure wheels make
# one hash serve every CPython; none of them pins an ABI of its own).
WHEEL_HINTS = {
    "pip": "py3-none-any",
}


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
    dates = sorted({f["upload_time"][:10] for f in files})
    if dates[-1] > CUTOFF:
        raise SystemExit(
            f"{name} {version}: published {dates[-1]}, after the {CUTOFF} "
            "date rule")


def pypi_hashes(name, version, wanted=None):
    data = json.loads(get(PYPI.format(f"{name}/{version}")))
    files = [u for u in data["urls"] if u["packagetype"] == "bdist_wheel"
             and usable(u["filename"])
             and (wanted is None or wanted in u["filename"])]
    if not files:
        raise SystemExit(f"{name} {version}: no usable wheel on PyPI")
    check_date(name, version, files)
    return sorted(u["digests"]["sha256"] for u in files)


def torch_cpu_lines():
    """Lock lines for torch 2.14.0+cpu from the pytorch index.

    pip's --require-hashes mode refuses local-version pins resolved from an
    index (`torch==2.14.0+cpu` — it demands hashes for the bare 2.14.0 too),
    so each supported CPython gets a direct wheel URL with an environment
    marker and its own sha256.
    """
    page = get(TORCH_CPU_INDEX)
    lines = []
    for m in re.finditer(
            r'torch-2\.14\.0%2Bcpu-(cp31[0-3])-cp31[0-3]-manylinux_2_28_x86_64'
            r'\.whl#sha256=([0-9a-f]{64})', page):
        cp, sha = m.group(1), m.group(2)
        pyver = f"{cp[2]}.{cp[3:]}"        # cp310 -> 3.10
        lines.append(
            f'torch @ https://download.pytorch.org/whl/cpu/'
            f'torch-2.14.0%2Bcpu-{cp}-{cp}-manylinux_2_28_x86_64.whl'
            f' ; python_version == "{pyver}" --hash=sha256:{sha}')
    return lines


def emit(lock, packages):
    for name, version, hashes in packages:
        line = f"{name}=={version}"
        for h in hashes:
            line += f" \\\n    --hash=sha256:{h}"
        print(line, file=lock)


def main():
    torch_lines = torch_cpu_lines()
    if len(torch_lines) != 4:
        raise SystemExit(
            f"torch 2.14.0+cpu: expected 4 cp310-cp313 wheels, got "
            f"{len(torch_lines)}")
    with open(__file__.rsplit("/", 1)[0] + "/requirements-cpu.lock", "w") as lock:
        print("## generated by judge/genlock.py -- pip install "
              "--require-hashes", file=lock)
        print("## torch 2.14.0+cpu: one pinned wheel URL per CPython",
              file=lock)
        for line in torch_lines:
            print(line, file=lock)
        emit(lock, [(name, version, pypi_hashes(name, version,
                                                WHEEL_HINTS.get(name)))
                    for name, version in PINS if name != "torch"])
    print(f"cpu lock: {len(PINS)} packages")


if __name__ == "__main__":
    sys.exit(main())
