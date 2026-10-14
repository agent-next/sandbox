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
    """Remove any configured API key or GitHub token value from text bound for the terminal."""
    for name in ("E2B_API_KEY", "SBX_API_KEY", "GH_TOKEN", "GITHUB_TOKEN", "GH_WEBHOOK_SECRET"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[redacted]")
    return text


def _say(text: str, *, err: bool = False) -> None:
    print(_scrub(text), file=sys.stderr if err else sys.stdout)


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
    _say(sbx.sandbox_id)
    return 0


def cmd_exec(args: argparse.Namespace) -> int:
    from e2b import CommandExitException, SandboxNotFoundException, TimeoutException

    _positive_seconds(args.timeout, "--timeout")
    _credentials()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SbxError("exec: no command given")
    line = command[0] if len(command) == 1 else shlex.join(command)
    try:
        sbx = _sandbox_cls().connect(args.sandbox_id)
        try:
            result = sbx.commands.run(line, timeout=args.timeout)
        except CommandExitException as exc:
            result = exc
    except SandboxNotFoundException:
        # The SDK says "Paused sandbox <id> not found" even for an id that
        # never existed; say what an agent can act on instead. Exit code
        # stays 1, as it was when the SDK exception leaked through.
        _say(
            f"sbx: exec: sandbox {args.sandbox_id} not found "
            "(it was killed, expired, or the id is wrong)",
            err=True,
        )
        return 1
    except TimeoutException:
        # The SDK's text addresses SDK callers ("pass 'timeout' when making
        # the request"); point at the CLI flag instead, and warn that the
        # command may still be running. Exit code stays 1.
        _say(
            f"sbx: exec: no result within --timeout {args.timeout:g}s; the command may "
            "still be running in the sandbox. Raise --timeout, or run the command "
            "detached with output redirected to a file and read the file back.",
            err=True,
        )
        return 1
    sys.stdout.write(_scrub(result.stdout))
    sys.stderr.write(_scrub(result.stderr))
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
    try:
        data = resp.json()
    except ValueError as exc:
        raise SbxError("GET /sandboxes returned invalid JSON") from exc
    items = data.get("sandboxes") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise SbxError("GET /sandboxes returned an invalid sandbox list")
    # Validate the entire response before printing any rows: malformed data
    # must never look like a successful empty or partial inventory.
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise SbxError("GET /sandboxes returned an invalid sandbox entry")
        sid = item.get("sandboxID") or item.get("sandbox_id")
        if not isinstance(sid, str) or not sid or not sid.isprintable() or any(c.isspace() for c in sid):
            raise SbxError("GET /sandboxes returned an entry without a sandbox id")
        for name in ("alias", "templateID", "startedAt"):
            value = item.get(name)
            if value is not None and (not isinstance(value, str) or (value and not value.isprintable())):
                raise SbxError("GET /sandboxes returned an invalid sandbox column")
        template = item.get("alias") or item.get("templateID") or "-"
        started = item.get("startedAt") or "-"
        rows.append(f"{sid}\t{template}\t{started}")
    for row in rows:
        _say(row)
    return 0


def cmd_kill(args: argparse.Namespace) -> int:
    _credentials()
    killed = _sandbox_cls().kill(args.sandbox_id)
    if killed:
        _say(f"killed {args.sandbox_id}")
    else:
        _say(f"{args.sandbox_id}: not found (already gone)", err=True)
    return 0


def cmd_runners_image(args: argparse.Namespace) -> int:
    from . import runners

    key, domain = _credentials()
    with httpx.Client() as http:
        version = args.runner_version or runners.latest_runner_version(http)
    template = args.template
    if template is None:
        base = os.environ.get("E2B_API_URL") or f"https://api.{domain}"
        with httpx.Client(base_url=base.rstrip("/"), headers={"X-API-Key": key}, timeout=60) as api:
            template = runners.ensure_template(api, image=args.from_image, size=args.size)
    snapshot = runners.build_image(_sandbox_cls(), template=template, runner_version=version)
    _say(snapshot)
    return 0


def _key_concurrency(key: str, domain: str) -> int | None:
    """The key's concurrent-sandbox limit from the account API, or None if it cannot be read."""
    base = os.environ.get("E2B_API_URL") or f"https://api.{domain}"
    try:
        resp = httpx.get(f"{base.rstrip('/')}/v0/account", headers={"X-API-Key": key}, timeout=30)
        limit = resp.json()["limits"]["max_concurrent"] if resp.status_code == 200 else None
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None
    return limit if type(limit) is int and limit > 0 else None


def cmd_runners_serve(args: argparse.Namespace) -> int:
    import threading

    from . import runners

    key, domain = _credentials()
    for value, flag in ((args.interval, "--interval"), (args.idle_min, "--idle-min"),
                        (args.job_timeout_min, "--job-timeout-min")):
        _positive_seconds(value, flag)
    if args.job_timeout_min + args.idle_min + 5 > MAX_TIMEOUT_MIN:
        raise SbxError(f"--job-timeout-min + --idle-min must leave 5 minutes under the {MAX_TIMEOUT_MIN}-minute sandbox lifetime")
    if bool(args.org) == bool(args.repo):
        raise SbxError("runners serve: give exactly one of --org or --repo")
    if not 0 <= args.warm <= args.max:
        raise SbxError("runners serve: need 0 <= --warm <= --max")
    if not args.prefix.strip():
        raise SbxError("runners serve: --prefix must not be empty (it decides which runners this pool owns)")
    if args.webhook_port is not None and args.watch:
        raise SbxError("runners serve: --watch and --webhook-port are alternatives; give one")
    secret = os.environ.get("GH_WEBHOOK_SECRET")
    if args.webhook_port is not None and not secret:
        raise SbxError("--webhook-port needs GH_WEBHOOK_SECRET (the webhook's secret)")
    scope = f"orgs/{args.org}" if args.org else f"repos/{args.repo}"
    labels = ["self-hosted", *[x.strip() for x in args.labels.split(",") if x.strip()]]
    gh = runners.GitHub(runners.github_token(), scope)
    watch = args.watch or ([args.repo] if args.repo else [])
    for repo in args.watch or []:
        gh.check_repo(repo)
    boot = runners.sandbox_boot(
        gh, _sandbox_cls(), snapshot=args.snapshot, labels=labels, group_id=args.group_id,
        job_timeout_s=round(args.job_timeout_min * 60), idle_ttl_s=round(args.idle_min * 60),
    )
    wake = threading.Event()
    if args.webhook_port is not None:
        queue = runners.JobQueue(secret, labels, on_change=wake.set)
        runners.webhook_server(queue, args.webhook_host, args.webhook_port)
        queued, cheap = queue.__len__, True
    else:
        queued, cheap = ((lambda: gh.queued(watch, labels)) if watch else (lambda: 0)), False
    warm, maximum = args.warm, args.max
    limit = _key_concurrency(key, domain)
    if limit is not None and limit < maximum:  # past the key's limit every spawn is a 429
        runners.emit("max_capped", requested=maximum, key_limit=limit)
        warm, maximum = min(warm, limit), limit
    pool = runners.Pool(
        gh, boot, warm=warm, maximum=maximum, prefix=args.prefix,
        idle_ttl=args.idle_min * 60, queued=queued, queued_is_cheap=cheap,
    )
    runners.sweep(gh, _sandbox_cls(), args.prefix)
    runners.serve(pool, interval=args.interval, stop=threading.Event(), wake=wake)
    return 0


def cmd_runners_migrate(args: argparse.Namespace) -> int:
    from . import migrate, runners

    jobs = {x.strip() for x in args.jobs.split(",") if x.strip()} if args.jobs else None
    _say(migrate.run(
        args.repo, runners.github_token(), apply=args.apply, labels=migrate.parse_labels(args.label),
        only=args.only, jobs=jobs, base=args.base))
    return 0


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {_scrub(message)}\n")


def build_parser() -> argparse.ArgumentParser:
    ap = _Parser(
        prog="sbx",
        description="Create, use and kill agent-next cloud sandboxes.",
    )
    ap.add_argument("--version", action="version", version=_version())
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=_Parser)

    p = sub.add_parser("create", help="start a sandbox and print its id")
    p.add_argument("--template", default=None, help="template name (default: the default template)")
    p.add_argument(
        "--timeout-min",
        type=float,
        default=DEFAULT_TIMEOUT_MIN,
        help=f"idle minutes before deletion (default {DEFAULT_TIMEOUT_MIN})",
    )
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("exec", help="run a command in a sandbox; exit code is the command's")
    p.add_argument("sandbox_id")
    p.add_argument("--timeout", type=float, default=60, help="command timeout in seconds (default 60)")
    p.add_argument(
        "command",
        nargs="+",
        help="command: one string is run as a shell line; put -- before it when it has several words or options",
    )
    p.set_defaults(func=cmd_exec)

    p = sub.add_parser("list", help="list live sandboxes held by this key")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("kill", help="kill a sandbox")
    p.add_argument("sandbox_id")
    p.set_defaults(func=cmd_kill)

    p = sub.add_parser("runners", help="serve GitHub Actions jobs from disposable sandboxes")
    rsub = p.add_subparsers(dest="runners_cmd", required=True, parser_class=_Parser)
    r = rsub.add_parser("image", help="bake a runner snapshot (actions/runner + Docker) and print its id")
    r.add_argument("--from-image", default="ubuntu:24.04", help="public OCI image to bake from (default ubuntu:24.04, like GitHub's runners)")
    r.add_argument("--size", default="small", choices=["small", "standard"], help="runner size: small 2 vCPU / 8 GB (default), standard 4 vCPU / 16 GB")
    r.add_argument("--template", default=None, help="bake from this existing template instead of --from-image")
    r.add_argument("--runner-version", default=None, help="actions/runner version (default: latest release)")
    r.set_defaults(func=cmd_runners_image)

    r = rsub.add_parser("serve", help="keep a warm pool of single-job runners; Ctrl-C drains")
    r.add_argument("--org", help="register runners at this organization")
    r.add_argument("--repo", help="or at this OWNER/REPO")
    r.add_argument("--snapshot", required=True, help="snapshot id from `sbx runners image`")
    r.add_argument("--labels", default="sbx", help="comma-separated labels besides self-hosted (default sbx)")
    r.add_argument("--group-id", type=int, default=1, help="runner group id (default 1, the Default group)")
    r.add_argument("--warm", type=int, default=2, help="idle runners to keep registered (default 2)")
    r.add_argument("--max", type=int, default=10, help="most sandboxes at once (default 10)")
    r.add_argument("--watch", action="append", help="OWNER/REPO whose queued jobs (in its 50 newest active runs) scale the pool past --warm (repeatable)")
    r.add_argument(
        "--webhook-port", type=int, default=None,
        help="also take workflow_job webhooks on this port (secret: GH_WEBHOOK_SECRET); queued jobs then scale the pool at once",
    )
    r.add_argument("--webhook-host", default="127.0.0.1", help="webhook bind address (default 127.0.0.1; put a TLS proxy or tunnel in front)")
    r.add_argument("--idle-min", type=float, default=30, help="recycle a runner idle this long (default 30)")
    r.add_argument("--job-timeout-min", type=float, default=360, help="longest job; bounds sandbox lifetime (default 360)")
    r.add_argument("--prefix", default="sbx-", help="runner name prefix this pool owns (default sbx-)")
    r.add_argument("--interval", type=float, default=5, help="seconds between pool checks (default 5)")
    r.epilog = "Ctrl-C drains (idle runners go, busy ones finish their job); a second Ctrl-C kills them all."
    r.set_defaults(func=cmd_runners_serve)

    r = rsub.add_parser("migrate", help="propose moving a repo's ubuntu-* jobs onto sbx runners (diff, or a pull request)")
    r.add_argument("--repo", required=True, help="OWNER/REPO whose workflows to migrate")
    mode = r.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the diff and a job table only (default)")
    mode.add_argument("--apply", action="store_true", help="push branch sbx-runners-migrate and open a pull request")
    r.add_argument("--label", default="[self-hosted, sbx]", help="new runs-on labels (default '[self-hosted, sbx]')")
    r.add_argument("--only", default=None, help="only this workflow file (name or path)")
    r.add_argument("--jobs", default=None, help="only these comma-separated job ids")
    r.add_argument("--base", default=None, help="branch to read and target (default: the repo's default branch)")
    r.set_defaults(func=cmd_runners_migrate)
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
        _say(f"sbx: {exc}", err=True)
        return 2
    except Exception as exc:  # SDK errors carry the gateway's message
        _say(f"sbx: {type(exc).__name__}: {exc}", err=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
