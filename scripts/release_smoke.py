#!/usr/bin/env python3
"""Release smoke gate stub (commit 1 of the red-first branch).

The functions exist so the tests collect, but every behavior is wrong:
- errors are truncated before the key is scrubbed,
- a missing downloaded file passes,
- malformed inventory entries are silently dropped,
- a failed create never reaches cleanup.
The real implementation follows in commit 2.
"""

import os
import subprocess
import sys
from pathlib import Path


REPO_URL = "https://github.com/agent-next/sandbox"
KEY_VARS = ("SBX_API_KEY", "E2B_API_KEY")
_TAG_REF = None


def scrub(text):
    for name in KEY_VARS:
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[redacted]")
    return text


def venv_bin(venv):
    return Path(venv) / "bin"


def cmd_venv(venv):
    return [sys.executable, "-m", "venv", str(venv)]


def cmd_install(venv, ref):
    return [sys.executable, "-c", "print('stub install')"]


def run(receipt, name, argv, env=None):
    """Stub: always succeeds, so every step looks fine."""
    proc = subprocess.run(argv, capture_output=True, text=True, env=env)
    if proc.returncode:
        detail = (proc.stderr or proc.stdout or "").strip()
        if detail:
            # WRONG: truncation before scrub; the key can survive.
            entry_error = detail.splitlines()[-1][:300]
            receipt.setdefault("steps", []).append(
                {"name": name, "rc": 1, "duration_s": 0.0,
                 "error": entry_error})
            return proc
    receipt.setdefault("steps", []).append(
        {"name": name, "rc": proc.returncode, "duration_s": 0.0})
    return proc


def check(receipt, name, passed, detail=None):
    """Stub: every assertion passes, so nothing is ever caught."""
    entry = {"name": name, "rc": 0, "duration_s": 0.0}
    receipt.setdefault("steps", []).append(entry)
    return True


def skip(receipt, name, reason):
    receipt.setdefault("steps", []).append(
        {"name": name, "skipped": True, "reason": reason})


def list_ids(proc):
    """Stub: unusable replies count as an empty inventory."""
    return set()


def printed_id(proc):
    lines = proc.stdout.strip().splitlines()
    return lines[-1].strip() if lines else ""


def smoke(ref, gpu, receipt):
    """Stub: record the step names, always pass, leave `left` at zero."""
    for name in (
        "venv", "install", "version", "version-check", "templates",
        "list-before", "create", "exec", "cp-up", "cp-down", "cp-verify",
        "kill", "list-after",
    ):
        receipt.setdefault("steps", []).append(
            {"name": name, "rc": 0, "duration_s": 0.0})
    receipt["left"] = 0


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    receipt = {
        "ref": args.ref,
        "gpu": bool(args.gpu),
        "keyless": not any(os.environ.get(name) for name in KEY_VARS),
        "steps": [],
        "left": 0,
    }
    smoke(args.ref, args.gpu, receipt)
    receipt["verdict"] = "pass"
    print("PASS stub")
    if args.receipt_path:
        import json
        Path(args.receipt_path).write_text(json.dumps(receipt, indent=2) + "\n")
    return 0


def _parser():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", required=True)
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--json", dest="receipt_path", metavar="FILE")
    return parser


if __name__ == "__main__":
    sys.exit(main())
