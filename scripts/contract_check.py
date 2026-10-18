#!/usr/bin/env python3
"""Contract checks: the kit's docs against the live service.

Three checks; each prints PASS, FAIL or SKIP with its details, and the
process exits 1 if any check failed:

- links  every http(s) URL in README.md, cli/README.md,
         plugins/sandbox/README.md, plugins/sandbox/skills/sandbox/SKILL.md
         and docs/**/*.md must answer with a status below 400. Checked with
         HEAD, falling back to GET when HEAD is refused, and retried once on
         transport errors. localhost, example.com and URLs with placeholders
         (`<port>`, `{id}`, `$id`) are skipped.
- mcp    the tool names listed in plugins/sandbox/README.md must equal the
         server's tool list. Source of truth: the MCP endpoint (no server
         code ships in this repo). Needs a key; otherwise SKIP.
- gpu    every GPU template the docs present as live must be in the catalog
         the GPU template endpoint returns. Needs a key; otherwise SKIP.

The key comes from --api-key or SBX_API_KEY. A SKIP always prints why; it is
never a silent pass. Run from anywhere: `python3 scripts/contract_check.py`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_README = "plugins/sandbox/README.md"
PLUGIN_SKILL = "plugins/sandbox/skills/sandbox/SKILL.md"

MCP_URL = "https://api.sbx.agent-next.com/mcp/v1"
GPU_URL = "https://api.sbx.agent-next.com/gpu/templates"

# A status the links check treats as alive even though it is >= 400: the
# server answered and named the route's method set, which is what "the link
# resolves" means for an API endpoint that only accepts POST.
ALIVE_REFUSED = frozenset({405})

# URLs that never resolve for anyone and say nothing about the docs.
SKIP_URL_PARTS = ("localhost", "127.0.0.1", "example.com", "example.org")
# `<port>`, `{id}`, `$id`: placeholders, not links.
PLACEHOLDER_RE = re.compile(r"[<{$]")
URL_RE = re.compile(r"https?://[^\s<>\"'`)\]}]+")

# plugins/sandbox/README.md lists the tools on one "Tools: `a`, `b`, ..."
# entry that wraps over lines and ends right before "Server URL:".
TOOL_LIST_RE = re.compile(r"Tools:(?P<body>(?:\s*`[^`\n]+`\s*,?)+?)\s*\.\s*Server URL:")
TOOL_NAME_RE = re.compile(r"`([^`\n]+)`")
# plugins/sandbox/skills/sandbox/SKILL.md names the live GPU catalog in one
# sentence; the list ends at the parenthesis that says where it is listed.
# The sentence may wrap over lines, so every word gap admits whitespace.
CATALOG_RE = re.compile(
    r"The\s+catalog\s+on\s+the\s+live\s+service\s+today\s+is\s+(?P<body>[^.;()]+)")
CATALOG_NAME_RE = re.compile(r"`([^`]+)`")

REQUEST_TIMEOUT_S = 20
RETRIES = 1
USER_AGENT = "agent-next-contract-check"


class Skip(Exception):
    """A check that cannot run here; the reason is printed, never hidden."""


@dataclass
class Check:
    name: str
    ok: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    skip_reason: str | None = None

    def report(self) -> bool:
        if self.skip_reason is not None:
            print(f"SKIP {self.name}: {self.skip_reason}")
            for line in self.notes:
                print(f"  {line}")
            return True
        if self.failed:
            print(f"FAIL {self.name} ({len(self.failed)} problem(s))")
        else:
            print(f"PASS {self.name} ({len(self.ok)} ok)")
        for line in self.notes + self.ok + self.failed:
            print(f"  {line}")
        return not self.failed


# --- HTTP ---------------------------------------------------------------

def _open(url: str, method: str, headers: dict | None = None,
          payload: bytes | None = None) -> tuple[int, str]:
    """One request; HTTP statuses answer for themselves, transport errors raise."""
    req = urllib.request.Request(url, method=method, headers=headers or {}, data=payload)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            return resp.status, resp.reason
    except urllib.error.HTTPError as exc:
        return exc.code, exc.reason or ""
    except Exception as exc:  # refused, reset, timed out, bad TLS
        raise Skip(f"{method} {url}: {type(exc).__name__}: {exc}") from exc


def _request(url: str, method: str, headers: dict | None = None,
             payload: bytes | None = None) -> tuple[int, str]:
    """One request, retried once on a transport error."""
    last: Skip | None = None
    for _ in range(RETRIES + 1):
        try:
            return _open(url, method, headers, payload)
        except Skip as exc:
            last = exc
    assert last is not None
    raise last


def link_status(url: str) -> int:
    """The status a doc link answers with: HEAD, then GET if HEAD is refused."""
    try:
        status, _ = _request(url, "HEAD", headers={"User-Agent": USER_AGENT})
    except Skip:
        return _request(url, "GET", headers={"User-Agent": USER_AGENT})[0]
    if status in (400, 403, 405, 501):
        # A server that refuses HEAD but serves GET is not a dead link.
        status, _ = _request(url, "GET", headers={"User-Agent": USER_AGENT})
    return status


def fetch_json(url: str, api_key: str, method: str = "GET",
               payload: dict | None = None) -> object:
    """A JSON call to the service; bad status, transport or body raises Skip."""
    headers = {"User-Agent": USER_AGENT, "X-API-Key": api_key,
               "Accept": "application/json"}
    if "/mcp/" in url:
        # The MCP server refuses requests that do not accept its stream type.
        headers["Accept"] = "application/json, text/event-stream"
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    status, reason = _request(url, method, headers, body)
    if status >= 400:
        raise Skip(f"{method} {url} answered HTTP {status} {reason}".rstrip())
    req = urllib.request.Request(url, method=method, headers=headers, data=body)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        raise Skip(f"{method} {url}: body is not valid JSON "
                   f"({type(exc).__name__}: {exc})") from exc


def api_key() -> str:
    key = os.environ.get("SBX_API_KEY", "")
    if not key:
        raise Skip("SBX_API_KEY is not set, and the server code is not in this "
                   "repo, so the live answer cannot be read")
    return key


# --- the docs -----------------------------------------------------------

def doc_files(root: Path) -> list[Path]:
    """The files the contract covers."""
    named = [root / rel for rel in
             ("README.md", "cli/README.md", PLUGIN_README, PLUGIN_SKILL)]
    found = [path for path in named if path.is_file()]
    docs = root / "docs"
    if docs.is_dir():
        found += sorted(docs.rglob("*.md"))
    return found


def doc_urls(path: Path) -> list[tuple[int, str]]:
    """Every checkable http(s) URL in the file, as (line, url).

    URLs inside fenced code blocks are install commands and examples, not
    claims about the live service, and are not checked.
    """
    found: list[tuple[int, str]] = []
    fenced = False
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        for match in URL_RE.finditer(line):
            url = match.group(0).rstrip(".,;:!?)")
            if PLACEHOLDER_RE.search(url) or any(part in url for part in SKIP_URL_PARTS):
                continue
            found.append((lineno, url))
    return found


def documented_tool_names(text: str) -> list[str]:
    """The tool list in the plugin README, in the order it is written."""
    match = TOOL_LIST_RE.search(text)
    return TOOL_NAME_RE.findall(match.group("body")) if match else []


def documented_gpu_templates(text: str) -> list[str]:
    """The GPU templates the skill's live-catalog sentence presents."""
    match = CATALOG_RE.search(text)
    return CATALOG_NAME_RE.findall(match.group("body")) if match else []


def tool_names_from_payload(payload: object) -> list[str]:
    """`tools/list`'s reply: JSON-RPC result.tools, or a bare list."""
    if isinstance(payload, dict):
        payload = payload.get("result", payload)
    if isinstance(payload, dict):
        payload = payload.get("tools")
    if not isinstance(payload, list):
        raise Skip(f"tools/list returned {type(payload).__name__}, not a tool list")
    names = []
    for tool in payload:
        name = tool.get("name") if isinstance(tool, dict) else tool
        if not isinstance(name, str) or not name:
            raise Skip("tools/list returned an entry without a name")
        names.append(name)
    return names


def gpu_templates_from_payload(payload: object) -> list[str]:
    """The template endpoint's reply: {"templates": [...]}, or a bare list."""
    items = payload.get("templates") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise Skip(f"the GPU template list is {type(payload).__name__}, not a list")
    names = []
    for item in items:
        name = item.get("name") or item.get("templateID") or item.get("id") \
            if isinstance(item, dict) else item
        if not isinstance(name, str) or not name:
            raise Skip("the GPU template list has an entry without a name")
        names.append(name)
    return names


# --- the three checks ---------------------------------------------------

def check_links(root: Path) -> Check:
    check = Check("links")
    targets: dict[str, list[str]] = {}
    for path in doc_files(root):
        rel = path.relative_to(root).as_posix()
        for lineno, url in doc_urls(path):
            targets.setdefault(url, []).append(f"{rel}:{lineno}")
    if not targets:
        check.ok("no checkable http(s) URLs in the docs")
        return check
    for url in sorted(targets):
        where = ", ".join(sorted(targets[url]))
        try:
            status = link_status(url)
        except Skip as exc:
            check.failed.append(f"{url} ({where}): {exc}")
            continue
        if status < 400:
            check.ok.append(f"{url} ({where}) HTTP {status}")
        elif status in ALIVE_REFUSED:
            check.ok.append(f"{url} ({where}) HTTP {status} (alive; refuses GET/HEAD)")
        else:
            check.failed.append(f"{url} ({where}) HTTP {status}")
    return check


def check_mcp(root: Path, api_key_value: str, url: str = MCP_URL) -> Check:
    check = Check("mcp")
    documented = documented_tool_names((root / PLUGIN_README).read_text(encoding="utf-8"))
    if not documented:
        check.failed.append(f"{PLUGIN_README} states no tool list")
        return check
    try:
        live = tool_names_from_payload(fetch_json(
            url, api_key_value, method="POST",
            payload={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}))
    except Skip as exc:
        check.skip_reason = str(exc)
        return check
    missing = [name for name in live if name not in documented]
    extra = [name for name in documented if name not in live]
    check.notes.append(f"documented ({len(documented)}): {', '.join(documented)}")
    check.notes.append(f"live ({len(live)}): {', '.join(live)}")
    if missing:
        check.failed.append(f"{PLUGIN_README} does not document tool(s) the server "
                            f"exposes: {', '.join(missing)}")
    if extra:
        check.failed.append(f"{PLUGIN_README} documents tool(s) the server does not "
                            f"expose: {', '.join(extra)}")
    if not missing and not extra:
        check.ok.append("documented tool list equals the server's")
    return check


def check_gpu(root: Path, api_key_value: str, url: str = GPU_URL) -> Check:
    check = Check("gpu")
    documented = documented_gpu_templates((root / PLUGIN_SKILL).read_text(encoding="utf-8"))
    if not documented:
        check.failed.append(f"{PLUGIN_SKILL} states no live GPU catalog")
        return check
    try:
        live = gpu_templates_from_payload(fetch_json(url, api_key_value))
    except Skip as exc:
        check.skip_reason = str(exc)
        return check
    missing = [name for name in documented if name not in live]
    check.notes.append(f"documented ({len(documented)}): {', '.join(documented)}")
    check.notes.append(f"live ({len(live)}): {', '.join(live)}")
    if missing:
        check.failed.append(f"{PLUGIN_SKILL} presents GPU template(s) the live "
                            f"catalog lacks: {', '.join(missing)}")
    else:
        check.ok.append(f"every documented GPU template is live ({len(live)} in catalog)")
    return check


# --- entry point --------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="repo root holding the docs (default: this repo)")
    parser.add_argument("--offline", action="store_true",
                        help="skip the link check; no network is touched")
    parser.add_argument("--api-key", default=None,
                        help="service API key (default: SBX_API_KEY in the environment)")
    parser.add_argument("--mcp-url", default=MCP_URL,
                        help="MCP endpoint the tool list is read from")
    parser.add_argument("--gpu-url", default=GPU_URL,
                        help="endpoint the GPU template catalog is read from")
    args = parser.parse_args(argv)
    root = args.root.resolve()

    checks: list[Check] = []
    if args.offline:
        checks.append(Check("links", skip_reason="--offline: no network is touched"))
    else:
        checks.append(check_links(root))
    try:
        key = args.api_key if args.api_key is not None else api_key()
        skip_reason = None
    except Skip as exc:
        key, skip_reason = "", str(exc)
    for name, run in (("mcp", lambda: check_mcp(root, key, args.mcp_url)),
                      ("gpu", lambda: check_gpu(root, key, args.gpu_url))):
        if skip_reason is not None:
            checks.append(Check(name, skip_reason=skip_reason))
            continue
        try:
            checks.append(run())
        except Skip as exc:
            checks.append(Check(name, skip_reason=str(exc)))

    print(f"contract check: {root}")
    passed = [check.report() for check in checks]
    skipped = sum(1 for check in checks if check.skip_reason is not None)
    failed = passed.count(False)
    if failed:
        print(f"contract check: FAIL ({failed} check(s) failed, {skipped} skipped)")
        return 1
    print(f"contract check: PASS ({skipped} check(s) skipped)" if skipped
          else "contract check: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
