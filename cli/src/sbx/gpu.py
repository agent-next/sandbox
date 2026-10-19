"""`sbx gpu`: GPU leases over the REST lease plane (create, list, exec, pause, resume, kill)."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from .cli import LEASE_ID, SbxError, _credentials, _positive_seconds, _say

MAX_EXEC_TIMEOUT_S = 3600
VRAM_RANGE_GIB = (0.5, 32)
DEFAULT_EXEC_TIMEOUT_S = 120

_JOB_FAILED = re.compile(r"\bjob \d+ failed:")

# status -> (label, what to do); the server message is appended when present
_HINTS = {
    401: ("the gateway rejected the API key", "check E2B_API_KEY"),
    402: ("no GPU credit left", "the GPU bucket is empty; ask the operator to refill it"),
    403: ("no GPU access", "this key has no GPU grant or tier"),
    404: ("not found", "check the lease id (killed or never created)"),
    409: ("conflict", "see the message: job failed, job already running, pause refused, or lease cap reached"),
    429: ("busy", "another tenant holds the GPU or your quota is full"),
    503: ("GPU plane at capacity", "no seat is free"),
}

_TYPED = {
    "gpu_lease_cap": ("GPU lease limit reached", "GPU lease limit reached for this key; kill a lease first"),
    "gpu_credit_exhausted": ("GPU credit exhausted", "GPU credit exhausted; ask the operator to refill it"),
}


def _base() -> str:
    _, domain = _credentials()
    return (os.environ.get("E2B_API_URL") or f"https://api.{domain}").rstrip("/")


def _lease_id(value: str) -> str:
    if not LEASE_ID.fullmatch(value):
        raise SbxError(f"invalid lease id {value!r}: GPU lease ids look like gl-1a2b3c-1")
    return value


def _body(resp: httpx.Response):
    try:
        return resp.json() if resp.content else None
    except ValueError:
        return None


class GpuHttpError(SbxError):
    def __init__(self, text: str, status: int, message: str | None):
        super().__init__(text)
        self.status, self.message = status, message


def _error(resp: httpx.Response) -> SbxError:
    status = resp.status_code
    body = _body(resp)
    body = body if isinstance(body, dict) else {}
    message = body.get("message")
    code = body.get("error")
    retry = body.get("retry_after_s") or resp.headers.get("Retry-After")
    wait = f"retry in {retry}s" if retry else "retry later"
    if code == "gpu_capacity_exhausted" or (
        isinstance(message, str) and "no GPU node has a free seat" in message
    ):
        label, hint = "GPU capacity is full", f"GPU capacity is full; {wait}"
    elif code in _TYPED:
        label, hint = _TYPED[code]
    else:
        label, hint = _HINTS.get(status, (f"HTTP {status}", "the gateway refused the request"))
        if status in (429, 503):
            hint += f"; {wait}"
    parts = [f"{label} ({status})"]
    if isinstance(message, str) and message.strip():
        parts.append(" ".join(message.split())[:300])
    return GpuHttpError(": ".join(parts) + f" -- {hint}", status, message if isinstance(message, str) else None)


_RESTART_ATTEMPTS = 3
_RESTART_MAX_WAIT_S = 30
_RESTART_MAX_TOTAL_S = 60
_RESTART_DEFAULT_WAIT_S = 5


def _restart_wait_s(resp: httpx.Response) -> float | None:
    """Seconds to wait on a 503 'restarting' reply, else None (no retry).

    The edge returns that code only when the app was not reachable, so the
    request never ran and a retry is safe for every method.
    """
    if resp.status_code != 503:
        return None
    body = _body(resp)
    if not isinstance(body, dict) or body.get("code") != "restarting":
        return None
    try:
        wait = float(body.get("retry_after_s"))
    except (TypeError, ValueError):
        wait = _RESTART_DEFAULT_WAIT_S
    return min(max(wait, _RESTART_DEFAULT_WAIT_S), _RESTART_MAX_WAIT_S)


def _call(method: str, path: str, body: dict | None = None, timeout: float = 60, ok_missing: bool = False):
    key, _ = _credentials()
    waited = 0.0
    for attempt in range(_RESTART_ATTEMPTS):
        try:
            resp = httpx.request(
                method, f"{_base()}{path}", headers={"X-API-Key": key}, json=body, timeout=timeout
            )
        except httpx.HTTPError as exc:
            raise SbxError(f"{method} {path}: gateway unreachable ({type(exc).__name__})") from exc
        wait = _restart_wait_s(resp)
        # the last attempt, an exhausted wait budget or any other status/body
        # falls through and is answered unchanged by the error mapping below
        if wait is None or attempt == _RESTART_ATTEMPTS - 1 or waited + wait > _RESTART_MAX_TOTAL_S:
            break
        _say(f"gateway restarting, retrying in {wait:g}s", err=True)
        time.sleep(wait)
        waited += wait
    if resp.status_code == 404 and ok_missing:
        return resp, None
    if resp.status_code >= 400:
        raise _error(resp)
    return resp, _body(resp)


def _emit_json(data) -> None:
    _say(json.dumps(data, allow_nan=False))


def cmd_create(args) -> int:
    accel: dict = {}
    if args.vram is not None:
        lo, hi = VRAM_RANGE_GIB
        accel["vram_gb"] = _positive_seconds(args.vram, "--vram", hi)
        if args.vram < lo:
            raise SbxError(f"--vram must be a positive number from {lo:g} to {hi:g} GiB")
    if args.template:
        accel["template"] = args.template
    if args.gpu_class:
        accel["class"] = args.gpu_class
    _, data = _call("POST", "/sandboxes", {"accel": accel})
    sid = data.get("sandboxID") if isinstance(data, dict) else None
    if not isinstance(sid, str) or not LEASE_ID.fullmatch(sid):
        raise SbxError("GPU create returned an invalid lease id; inspect your inventory")
    _emit_json(data) if args.json else _say(sid)
    return 0


def cmd_exec(args) -> int:
    sid = _lease_id(args.lease_id)
    timeout = _positive_seconds(args.timeout, "--timeout", MAX_EXEC_TIMEOUT_S)
    if args.code is not None:
        try:
            code = Path(args.code).read_text()
        except OSError as exc:
            raise SbxError(f"cannot read --code file {args.code}: {exc.strerror or exc}") from exc
    else:
        code = args.source
    try:
        _, data = _call("POST", f"/sandboxes/{sid}/exec", {"code": code, "timeout_s": timeout}, timeout + 30)
    except SbxError as exc:
        if isinstance(exc, GpuHttpError) and exc.status == 409 and _JOB_FAILED.search(exc.message or ""):
            _say(f"sbx: {exc}", err=True)
            return 1
        raise
    result = data.get("result") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        raise SbxError("GPU exec returned no result")
    if args.json:
        _emit_json(data)
    else:
        if result.get("stdout"):
            print(result["stdout"], end="")
        if result.get("stderr"):
            _say(result["stderr"].rstrip("\n"), err=True)
    if result.get("ok") is not True:
        _say("sbx: GPU job failed", err=True)
        return 1
    return 0


def _simple(verb: str, done: str):
    def run(args) -> int:
        sid = _lease_id(args.lease_id)
        _, data = _call("POST", f"/sandboxes/{sid}/{verb}")
        if args.json:
            _emit_json(data if data is not None else {"sandboxID": sid, "ok": True})
        else:
            _say(f"{done} {sid}")
        return 0

    return run


cmd_pause = _simple("pause", "paused")
cmd_resume = _simple("resume", "resumed")


def cmd_kill(args) -> int:
    sid = _lease_id(args.lease_id)
    resp, data = _call("DELETE", f"/sandboxes/{sid}", ok_missing=True)
    if resp.status_code == 404:
        _say(f"{sid}: not found (already gone)", err=True)
        return 0
    probe, state = _call("GET", f"/sandboxes/{sid}", ok_missing=True)
    if probe.status_code != 404 and not (isinstance(state, dict) and state.get("phase") == "dead"):
        raise SbxError(f"kill of {sid} not confirmed; run `sbx gpu kill {sid}` again")
    meters = data.get("meters") if isinstance(data, dict) else None
    if args.json:
        _emit_json({"sandboxID": sid, "killed": True, "meters": meters})
    else:
        _say(f"killed {sid}")
    return 0


def cmd_list(args) -> int:
    leases, rows = [], []
    path = "/sandboxes"
    cursors = set()
    while True:
        resp, data = _call("GET", path)
        items = data.get("sandboxes") if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise SbxError("GET /sandboxes returned an invalid sandbox list")
        for item in items:
            if not isinstance(item, dict):
                raise SbxError("GET /sandboxes returned an invalid sandbox entry")
            sid = item.get("sandboxID")
            if (not isinstance(sid, str) or not sid or not sid.isprintable()
                    or any(c.isspace() for c in sid)):
                raise SbxError("GET /sandboxes returned an invalid sandbox id")
            for name in ("templateID", "state", "startedAt"):
                value = item.get(name)
                if not isinstance(value, str) or not value or not value.isprintable():
                    raise SbxError(f"GET /sandboxes returned an invalid {name} column")
            if not sid.startswith("gl-") and "accel" not in item:
                continue
            _lease_id(sid)
            accel = item.get("accel")
            vram = accel.get("vram_gb") if isinstance(accel, dict) else None
            if type(vram) not in (int, float) or not VRAM_RANGE_GIB[0] <= vram <= VRAM_RANGE_GIB[1]:
                raise SbxError("GET /sandboxes returned an invalid GPU vram_gb")
            leases.append(item)
            rows.append(f"{sid}\t{item['templateID']}\t{item['state']}\t{vram:g}\t{item['startedAt']}")
        cursor = resp.headers.get("X-Next-Token")
        if not cursor:
            break
        if cursor in cursors:
            raise SbxError("GET /sandboxes returned a repeated pagination cursor")
        cursors.add(cursor)
        path = "/sandboxes?" + urlencode({"nextToken": cursor})
    # Buffer every page so neither output mode can emit a partial inventory.
    if args.json:
        _emit_json(leases)
    else:
        for row in rows:
            _say(row)
    return 0


def cmd_templates(args) -> int:
    _, data = _call("GET", "/gpu/templates")
    if args.json:
        _emit_json(data)
        return 0
    items = data.get("templates") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise SbxError("GET /gpu/templates returned an invalid list")
    for item in items:
        if isinstance(item, dict):
            name = item.get("name") or item.get("templateID") or item.get("id") or "-"
            desc = item.get("description")
            _say(f"{name}\t{desc}" if desc else str(name))
        else:
            _say(str(item))
    return 0


def cmd_info(args) -> int:
    sid = _lease_id(args.lease_id)
    _, data = _call("GET", f"/sandboxes/{sid}")
    if args.json:
        _emit_json(data)
        return 0
    if not isinstance(data, dict):
        raise SbxError("GET lease returned an invalid reply")
    _say(f"id\t{data.get('sandboxID', sid)}")
    _say(f"phase\t{data.get('phase', '-')}")
    _say(f"template\t{data.get('templateID', '-')}")
    for section in ("accel", "meters"):
        values = data.get(section)
        if isinstance(values, dict):
            for name, value in values.items():
                _say(f"{name}\t{value}")
    return 0


def register(sub, parser_class) -> None:
    """Add the `gpu` command group to the top-level subparsers."""

    def verb(gsub, name, help_, func, with_id=True):
        p = gsub.add_parser(name, help=help_)
        if with_id:
            p.add_argument("lease_id", help="GPU lease id (gl-...)")
        p.add_argument("--json", action="store_true", help="machine-readable reply")
        p.set_defaults(func=func)
        return p

    g = sub.add_parser("gpu", help="GPU leases: create, list, exec, pause, resume, kill")
    gsub = g.add_subparsers(dest="gpu_cmd", required=True, parser_class=parser_class)
    p = verb(gsub, "create", "start a GPU lease and print its id", cmd_create, with_id=False)
    p.add_argument("--vram", type=float, default=None, help="VRAM slice in GiB, 0.5-32 (default 1)")
    p.add_argument("--template", default=None, help="GPU template (see `sbx gpu templates`)")
    p.add_argument("--class", dest="gpu_class", default=None, help="GPU class, e.g. nvidia.5090")
    p = verb(gsub, "exec", "run Python source on a lease; exit 1 if the job fails", cmd_exec)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--code", metavar="FILE", help="file holding the job source")
    src.add_argument("-c", dest="source", metavar="SRC", help="job source as a string")
    p.add_argument(
        "--timeout", type=float, default=DEFAULT_EXEC_TIMEOUT_S,
        help=f"job budget in seconds, up to {MAX_EXEC_TIMEOUT_S}; overrun kills the lease (default {DEFAULT_EXEC_TIMEOUT_S})",
    )
    verb(gsub, "pause", "release the GPU, keep state (between jobs only; a lease that cannot be spilled is frozen and keeps billing)", cmd_pause)
    verb(gsub, "resume", "take a seat again and restore state", cmd_resume)
    verb(gsub, "kill", "destroy the lease and confirm it is gone", cmd_kill)
    verb(gsub, "list", "list GPU leases held by this key", cmd_list, with_id=False)
    verb(gsub, "templates", "list GPU templates on this plane", cmd_templates, with_id=False)
    verb(gsub, "info", "show phase, slice and billing meters", cmd_info)
