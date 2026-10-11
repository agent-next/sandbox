"""sbx: create, use and kill agent-next cloud sandboxes from the shell."""

from __future__ import annotations

import argparse
import math
import os
import shlex
import sys

import httpx

DEFAULT_DOMAIN = "sbx.agent-next.com"
DEFAULT_TIMEOUT_MIN = 5
MAX_TIMEOUT_MIN = 1440


class SbxError(Exception):
    pass


def _credentials() -> tuple[str, str]:
    key = os.environ.get("E2B_API_KEY") or os.environ.get("SBX_API_KEY")
    if not key:
        raise SbxError(
            "no API key: export E2B_API_KEY (or SBX_API_KEY). "
            "Get one at https://sbx.agent-next.com/console"
        )
    domain = os.environ.get("E2B_DOMAIN", DEFAULT_DOMAIN)
    # the SDK reads these from the environment
    os.environ["E2B_API_KEY"] = key
    os.environ["E2B_DOMAIN"] = domain
    return key, domain


def _scrub(text: str) -> str:
    """Remove any configured API key value from text bound for the terminal."""
    for name in ("E2B_API_KEY", "SBX_API_KEY"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[redacted]")
    return text


def _positive_seconds(value: float, what: str, maximum: float | None = None) -> float:
    if not math.isfinite(value) or value <= 0 or (maximum and value > maximum):
        limit = f" up to {maximum:g}" if maximum else ""
        raise SbxError(f"{what} must be a positive number{limit}")
    return value


def _sandbox_cls():
    from e2b import Sandbox

    return Sandbox


def cmd_create(args: argparse.Namespace) -> int:
    _positive_seconds(args.timeout_min, "--timeout-min", MAX_TIMEOUT_MIN)
    _credentials()
    sbx = _sandbox_cls().create(
        args.template, timeout=max(1, round(args.timeout_min * 60))
    )
    print(sbx.sandbox_id)
    return 0


def cmd_exec(args: argparse.Namespace) -> int:
    from e2b import CommandExitException

    _positive_seconds(args.timeout, "--timeout")
    _credentials()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SbxError("exec: no command given")
    line = command[0] if len(command) == 1 else shlex.join(command)
    sbx = _sandbox_cls().connect(args.sandbox_id)
    try:
        result = sbx.commands.run(line, timeout=args.timeout)
    except CommandExitException as exc:
        result = exc
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.exit_code


def cmd_list(args: argparse.Namespace) -> int:
    key, domain = _credentials()
    base = os.environ.get("E2B_API_URL") or f"https://api.{domain}"
    resp = httpx.get(
        f"{base.rstrip('/')}/sandboxes",
        headers={"X-API-Key": key},
        timeout=30,
    )
    if resp.status_code == 401:
        raise SbxError("the gateway rejected the API key (401)")
    if resp.status_code != 200:
        raise SbxError(f"GET /sandboxes failed with HTTP {resp.status_code}")
    data = resp.json()
    items = data if isinstance(data, list) else data.get("sandboxes", [])
    for item in items:
        sid = item.get("sandboxID") or item.get("sandbox_id") or "?"
        template = item.get("alias") or item.get("templateID") or "-"
        started = item.get("startedAt") or "-"
        print(f"{sid}\t{template}\t{started}")
    return 0


def cmd_kill(args: argparse.Namespace) -> int:
    _credentials()
    killed = _sandbox_cls().kill(args.sandbox_id)
    if killed:
        print(f"killed {args.sandbox_id}")
    else:
        print(f"{args.sandbox_id}: not found (already gone)", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="sbx",
        description="Create, use and kill agent-next cloud sandboxes.",
    )
    ap.add_argument("--version", action="version", version=_version())
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create", help="start a sandbox and print its id")
    p.add_argument("--template", default=None, help="template name (default: the default template)")
    p.add_argument(
        "--timeout-min",
        type=float,
        default=DEFAULT_TIMEOUT_MIN,
        help=f"hard lifetime in minutes (default {DEFAULT_TIMEOUT_MIN})",
    )
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("exec", help="run a command in a sandbox; exit code is the command's")
    p.add_argument("sandbox_id")
    p.add_argument("--timeout", type=float, default=60, help="command timeout in seconds (default 60)")
    p.add_argument(
        "command",
        nargs="+",
        help="command: one string is run as a shell line; use -- before a command that starts with a dash",
    )
    p.set_defaults(func=cmd_exec)

    p = sub.add_parser("list", help="list live sandboxes held by this key")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("kill", help="kill a sandbox")
    p.add_argument("sandbox_id")
    p.set_defaults(func=cmd_kill)
    return ap


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("agent-next-sandbox")
    except PackageNotFoundError:
        return "0+unknown"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SbxError as exc:
        print(f"sbx: {_scrub(str(exc))}", file=sys.stderr)
        return 2
    except Exception as exc:  # SDK errors carry the gateway's message
        print(f"sbx: {type(exc).__name__}: {_scrub(str(exc))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
