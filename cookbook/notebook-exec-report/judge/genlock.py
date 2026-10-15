#!/usr/bin/env python3
"""Regenerate judge/requirements.txt (sha256-pinned) from the PyPI index.

Run once when a pin changes:
    python3 judge/genlock.py
The lock lists every package pip would install for the demo's direct pins
(the transitive closure pip freeze reports for them) so that
`pip install --require-hashes` is exact and cannot silently upgrade.
Wheels are listed for cp312 (the interpreter judge/VERSIONS.txt records)
and for pure-python wheels by their only file; `pip --require-hashes`
verifies against exactly one line per package.

The date rule from the cookbook standard applies: no pin published in the
two weeks before the demo was written (cutoff 2026-09-30).
"""

from __future__ import annotations

import json
import sys
import urllib.request

CUTOFF = "2026-09-30"
CP = "cp312"
PLATFORM_OK = ("manylinux", "manylinux_2_17", "manylinux_2_28", "linux")
PYPI = "https://pypi.org/pypi/{}/{}/json"

# (name, version) -- the transitive closure pip resolves for the demo's
# direct pins (numpy, scipy, scikit-learn, pandas, matplotlib, nbclient,
# nbformat, nbconvert, ipykernel, jupyter_client, traitlets), each the
# newest release published before the CUTOFF above.
PINNED = [
    ("asttokens", "3.0.2"),
    ("attrs", "26.1.0"),
    ("beautifulsoup4", "4.15.0"),
    ("bleach", "6.4.0"),
    ("cloudpickle", "3.1.2"),
    ("comm", "0.2.3"),
    ("contourpy", "1.4.0"),
    ("cycler", "0.12.1"),
    ("debugpy", "1.8.22"),
    ("defusedxml", "0.7.1"),
    ("executing", "2.2.1"),
    ("fastjsonschema", "2.22.2"),
    ("fonttools", "4.66.1"),
    ("ipykernel", "7.4.0"),
    ("ipython", "9.17.1"),
    ("ipython_pygments_lexers", "1.1.1"),
    ("jedi", "0.20.0"),
    ("Jinja2", "3.1.6"),
    ("joblib", "1.6.0"),
    ("jsonschema", "4.26.0"),
    ("jsonschema-specifications", "2025.9.1"),
    ("jupyter_client", "8.10.0"),
    ("jupyter_core", "5.9.1"),
    ("jupyterlab_pygments", "0.3.0"),
    ("kiwisolver", "1.5.1"),
    ("MarkupSafe", "3.0.3"),
    ("matplotlib", "3.11.2"),
    ("matplotlib-inline", "0.2.2"),
    ("mistune", "3.3.4"),
    ("narwhals", "2.26.0"),
    ("nbclient", "0.11.0"),
    ("nbconvert", "7.17.1"),
    ("nbformat", "5.11.1"),
    ("nest-asyncio2", "1.7.3"),
    ("numpy", "2.5.3"),
    ("packaging", "26.3"),
    ("pandas", "3.0.6"),
    ("pandocfilters", "1.5.1"),
    ("parso", "0.8.7"),
    ("pexpect", "4.9.0"),
    ("pillow", "12.3.0"),
    ("platformdirs", "4.12.2"),
    ("prompt_toolkit", "3.0.53"),
    ("psutil", "7.2.2"),
    ("ptyprocess", "0.7.0"),
    ("pure_eval", "0.2.4"),
    ("Pygments", "2.21.0"),
    ("pyparsing", "3.3.3"),
    ("python-dateutil", "2.9.0.post0"),
    ("pyzmq", "27.2.0"),
    ("referencing", "0.37.0"),
    ("rpds-py", "2026.6.3"),
    ("scikit-learn", "1.9.1"),
    ("scipy", "1.18.1"),
    ("six", "1.17.0"),
    ("soupsieve", "2.10"),
    ("stack-data", "0.6.3"),
    ("threadpoolctl", "3.7.0"),
    ("tinycss2", "1.5.1"),
    ("tornado", "6.5.10"),
    ("traitlets", "5.16.1"),
    ("typing_extensions", "4.16.0"),
    ("wcwidth", "0.9.1"),
    ("webencodings", "0.6.1"),
]


def fetch(name: str, version: str) -> dict:
    with urllib.request.urlopen(PYPI.format(name, version)) as fh:
        return json.load(fh)


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split(".") if p.isdigit()) or (0,)


def supports(requires_python: str, py: str = "3.12") -> bool:
    """True iff `py` satisfies a `requires_python` marker string such as
    '>=3.9' or '>=3.10,<4' (stdlib; no packaging dependency)."""
    want = _version_tuple(py)
    for clause in requires_python.split(","):
        clause = clause.strip()
        if not clause:
            continue
        for op in (">=", "<=", "==", "!=", ">", "<", "~="):
            if clause.startswith(op):
                have = _version_tuple(clause[len(op):])
                ok = {
                    ">=": want >= have, "<=": want <= have,
                    "==": want[:len(have)] == have,
                    "!=": want[:len(have)] != have,
                    ">": want > have, "<": want < have,
                    "~=": want[:len(have) - 1] == have[:len(have) - 1],
                }[op]
                if not ok:
                    return False
                break
        else:
            return False  # unparseable clause: fail closed
    return True


def hashes(name: str, version: str) -> list[str]:
    data = fetch(name, version)
    rp = data["info"]["requires_python"] or ""
    if rp and not supports(rp, "3.12"):
        raise SystemExit(f"{name} {version}: requires_python {rp!r} "
                         f"excludes the pinned 3.12")
    for f in data["urls"]:
        if (f.get("upload_time_iso_8601") or "")[:10] > CUTOFF:
            raise SystemExit(f"{name} {version}: file {f['filename']} "
                             f"published after {CUTOFF}")
    out = []
    for f in data["urls"]:
        fn = f["filename"]
        if not fn.endswith(".whl"):
            continue
        if fn.endswith("-any.whl") or fn.endswith("py3-none-any.whl"):
            out.append(f["digests"]["sha256"])  # pure python
        elif "x86_64" not in fn or not any(p in fn for p in PLATFORM_OK):
            continue
        elif f"-{CP}-{CP}-" in fn or f"-{CP}t-{CP}t-" in fn:
            out.append(f["digests"]["sha256"])  # cp312 wheel
        elif "-abi3-" in fn:
            tag = fn.split("-")[2]  # e.g. cp36-abi3, cp311-abi3
            if len(tag) > 3 and tag.startswith("cp") and tag[2:].isdigit():
                minor = int(tag[3:])  # cp36 -> 6, cp312 -> 12
                if 0 < minor <= 12:
                    out.append(f["digests"]["sha256"])  # abi3 wheel for <=3.12
    if not out:
        raise SystemExit(f"{name} {version}: no usable wheel found")
    return list(dict.fromkeys(f"sha256:{h}" for h in out))


def main() -> int:
    lines = [
        "# notebook-exec-report judge venv pins (installed by judge/setup.sh",
        "# with --require-hashes; wheel set resolved for CPython 3.12 /",
        "# manylinux x86_64, the interpreter judge/VERSIONS.txt records).",
        "# Direct pins: numpy, scipy, scikit-learn, pandas, matplotlib,",
        "# nbclient, nbformat, nbconvert, ipykernel, jupyter_client, traitlets.",
        "",
    ]
    seen = set()
    for name, version in PINNED:
        key = (name.lower(), version)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"{name}=={version} " +
                     " ".join(f"\\\n    --hash={h}" for h in hashes(name, version)))
        lines.append("")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
