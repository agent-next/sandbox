#!/usr/bin/env python3
"""Run a tiny CUDA job in a 1 GiB slice, then destroy the owned lease."""

import json
import os
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = "https://api.sbx.agent-next.com"
JOB = """
import torch
assert torch.cuda.is_available(), 'CUDA unavailable'
x = torch.arange(1024, device='cuda', dtype=torch.float32)
actual = int(x.sum().item())
assert actual == 523776, actual
report.update(device=torch.cuda.get_device_name(0), sum=actual,
              allocated_bytes=torch.cuda.memory_allocated())
"""


def request(key, method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = Request(API + path, data=data, method=method, headers={
        "X-API-Key": key, "Content-Type": "application/json",
    })
    try:
        with urlopen(req, timeout=120) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        # Do not echo a server body that could contain credentials.
        return exc.code, None


def main():
    key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
    if not key:
        raise RuntimeError("export SBX_API_KEY (a key with GPU access)")
    status, created = request(key, "POST", "/sandboxes", {
        "accel": {"vram_gb": 1, "reserve": "exec"},
    })
    if status != 201:
        raise RuntimeError(f"GPU create: HTTP {status}; check GPU access, credit and capacity")
    sid = created["sandboxID"]
    # Only gateway-generated GPU ids may be interpolated into request paths.
    if not isinstance(sid, str) or not sid.startswith("gl-") or not all(
        c.isascii() and (c.isalnum() or c == "-") for c in sid
    ):
        raise RuntimeError("GPU create returned an invalid lease id; inspect your inventory")
    print(f"created {sid} (1 GiB VRAM slice)", flush=True)
    try:
        status, executed = request(key, "POST", f"/sandboxes/{sid}/exec", {
            "code": JOB, "timeout_s": 60,
        })
        if status != 200 or not isinstance(executed, dict):
            raise RuntimeError(f"GPU exec: HTTP {status}")
        result = executed.get("result") or {}
        report = result.get("report") or {}
        if result.get("ok") is not True or report.get("sum") != 523776:
            raise RuntimeError("GPU job did not return the expected CUDA result")
        print(json.dumps({"sandbox_id": sid, "report": report}, indent=2))
    finally:
        status, _ = request(key, "DELETE", f"/sandboxes/{sid}")
        if status not in (200, 204, 404):
            raise RuntimeError(f"cleanup {sid}: HTTP {status}; run sandbox_kill for this id")
        status, remaining = request(key, "GET", f"/sandboxes/{sid}")
        if status != 404 and not (
            status == 200 and isinstance(remaining, dict) and remaining.get("phase") == "dead"
        ):
            raise RuntimeError(f"cleanup unconfirmed for {sid}: HTTP {status}; inspect your inventory")
        print(f"destroyed {sid}; verified absent or dead", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        message = str(exc)
        for name in ("SBX_API_KEY", "E2B_API_KEY"):
            if os.environ.get(name):
                message = message.replace(os.environ[name], "[redacted]")
        print(f"small-gpu: {message}", file=sys.stderr)
        sys.exit(1)
