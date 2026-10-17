"""sbx: create, use and kill agent-next cloud sandboxes from the shell."""

from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import sys
import time
from pathlib import Path

import httpx

DEFAULT_DOMAIN = "sbx.agent-next.com"
DEFAULT_TIMEOUT_MIN = 5
MAX_TIMEOUT_MIN = 1440
_RESTART_ATTEMPTS = 3
_RESTART_MAX_WAIT_S = 30


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


def _gateway_restart_wait_s(exc: BaseException) -> float | None:
    """Seconds the gateway asked for in a 503 'restarting' reply, else None."""
    text = str(exc)
    brace = text.find("{")
    end = text.rfind("}")
    # REST calls put the status first ("503: b'{...}'"); envd file calls raise
    # a TimeoutException that starts with the body and has no status
    if brace < 0 or end < brace or (brace and "503" not in text[:brace]):
        return None
    try:
        # the SDK appends the raw body as a bytes repr ("503: b'...'"), so the
        # JSON object ends at the last brace, not at the end of the string
        body = json.loads(text[brace:end + 1])
    except ValueError:
        return None
    if not isinstance(body, dict) or body.get("code") != "restarting":
        return None
    try:
        wait = float(body.get("retry_after_s"))
    except (TypeError, ValueError):
        wait = 0.0
    return min(max(wait, 1.0), _RESTART_MAX_WAIT_S)


def _sdk_retry(fn, *args, **kwargs):
    """Call an e2b SDK function, retrying the gateway's 503 'restarting' reply."""
    for attempt in range(_RESTART_ATTEMPTS):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            wait = _gateway_restart_wait_s(exc)
            if wait is None or attempt == _RESTART_ATTEMPTS - 1:
                raise
            _say(f"sbx: gateway is restarting; retrying in {wait:g}s", err=True)
            time.sleep(wait)


def cmd_create(args: argparse.Namespace) -> int:
    _positive_seconds(args.timeout_min, "--timeout-min", MAX_TIMEOUT_MIN)
    _credentials()
    sbx = _sdk_retry(
        _sandbox_cls().create, args.template, timeout=max(1, round(args.timeout_min * 60))
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
        sbx = _sdk_retry(_sandbox_cls().connect, args.sandbox_id)
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


def _cp_remote(value: str) -> tuple[str, str] | None:
    sid, separator, path = value.partition(":")
    if not separator or "/" in sid:
        return None
    if not sid or not path:
        raise SbxError("cp: remote endpoint must be ID:PATH with a nonempty id and path")
    return sid, path


def cmd_cp(args: argparse.Namespace) -> int:
    _positive_seconds(args.timeout, "--timeout")
    source, target = _cp_remote(args.source), _cp_remote(args.target)
    if bool(source) == bool(target):
        raise SbxError("cp: exactly one side must be ID:PATH")
    sid, remote = source or target
    local_name = args.target if source else args.source
    if not local_name:
        raise SbxError("cp: local path must not be empty")
    local = Path(local_name)
    try:
        if local_name.endswith("/") or remote.endswith("/") or local.is_dir():
            raise SbxError("cp: directories are not supported; give a file path on each side")
        data = None if source else local.read_bytes()
    except OSError as exc:
        raise SbxError(f"cp: {exc}") from exc

    _credentials()
    from e2b import FileType, InvalidArgumentException, NotFoundException, TimeoutException

    try:
        sbx = _sdk_retry(_sandbox_cls().connect, sid)
        try:
            info = _sdk_retry(sbx.files.get_info, remote)
        except NotFoundException:
            if source:
                raise
        else:
            if info.type == FileType.DIR:
                raise SbxError("cp: directories are not supported; give a file path on each side")
        if source:
            data = _sdk_retry(sbx.files.read, remote, format="bytes", request_timeout=args.timeout)
        else:
            _sdk_retry(sbx.files.write, remote, data, request_timeout=args.timeout)
    except (InvalidArgumentException, NotFoundException) as exc:
        raise SbxError(f"cp: {exc}") from exc
    except (TimeoutException, httpx.TimeoutException) as exc:
        # only a request deadline is ours; the SDK also raises TimeoutException
        # for an expired sandbox and for a gateway restart it could not wait out
        if isinstance(exc, TimeoutException) and not str(exc).startswith("Request timed out"):
            raise
        raise SbxError(f"cp: the transfer did not finish within --timeout {args.timeout:g} s") from exc

    if source:
        try:
            local.write_bytes(data)
        except OSError as exc:
            raise SbxError(f"cp: {exc}") from exc
    return 0


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


def cmd_templates(args: argparse.Namespace) -> int:
    key, domain = _credentials()
    base = os.environ.get("E2B_API_URL") or f"https://api.{domain}"
    resp = httpx.get(
        f"{base.rstrip('/')}/templates", headers={"X-API-Key": key}, timeout=30,
    )
    if resp.status_code == 401:
        raise SbxError("the gateway rejected the API key (401)")
    if resp.status_code != 200:
        raise SbxError(f"GET /templates failed with HTTP {resp.status_code}")
    try:
        items = resp.json()
    except ValueError as exc:
        raise SbxError("GET /templates returned invalid JSON") from exc
    if not isinstance(items, list):
        raise SbxError("GET /templates returned an invalid template list")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise SbxError("GET /templates returned an invalid template entry")
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list):
            raise SbxError("GET /templates returned invalid template aliases")
        for alias in aliases or [item.get("templateID")]:
            if not isinstance(alias, str) or not alias or not alias.isprintable() or any(c.isspace() for c in alias):
                raise SbxError("GET /templates returned an invalid template alias or id")
            if item.get("accel") is None:
                rows.append(alias)
    if args.json:
        _say(json.dumps(items))
        return 0
    for row in rows:
        _say(row)
    return 0


def cmd_kill(args: argparse.Namespace) -> int:
    _credentials()
    killed = _sdk_retry(_sandbox_cls().kill, args.sandbox_id)
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
    if args.keep_failed < 0:
        raise SbxError("--keep-failed must be a positive snapshot cap")
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
        failed_jobs=_failed_jobs(key, domain) if args.keep_failed else None,
        keep_failed=args.keep_failed,
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


def cmd_runners_stats(args: argparse.Namespace) -> int:
    from datetime import datetime, timedelta, timezone
    import json
    import re

    from . import runners, runner_stats

    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo):
        raise SbxError("runners stats: --repo must be OWNER/REPO")
    if not args.prefix.strip():
        raise SbxError("runners stats: --prefix must not be empty")
    if args.run is not None and args.run < 1:
        raise SbxError("runners stats: --run must be a positive ID")
    if not math.isfinite(args.price_per_vcpu_min) or args.price_per_vcpu_min < 0:
        raise SbxError("--price-per-vcpu-min must be finite and nonnegative")
    since = None
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if args.run is None:
        duration = re.fullmatch(r"(\d+(?:\.\d+)?)([mhd])", args.since or "24h")
        if not duration:
            raise SbxError("runners stats: --since needs a duration such as 30m, 24h or 7d")
        seconds = float(duration[1]) * {"m": 60, "h": 3600, "d": 86400}[duration[2]]
        _positive_seconds(seconds, "--since", 365 * 86400)
        since = (now - timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
    events = []
    if args.serve_log:
        line_no = 0
        try:
            with open(args.serve_log) as stream:
                for line_no, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        raise ValueError("expected event object")
                    events.append(event)
        except (OSError, ValueError) as exc:
            detail = f"invalid JSONL at line {line_no}" if isinstance(exc, ValueError) else "cannot read file"
            raise SbxError(f"runners stats: --serve-log {detail}") from exc
    gh = runners.GitHub(runners.github_token(access="Actions read access on the repo"), f"repos/{args.repo}")
    try:
        runs = [gh.workflow_run(args.repo, args.run)] if args.run is not None else gh.workflow_runs(
            args.repo, since, now.isoformat().replace("+00:00", "Z"),
        )
        jobs = [job for run in runs for job in gh.jobs(args.repo, run["id"], run["run_attempt"])]
    finally:
        gh.http.close()
    report = runner_stats.build_report(
        args.repo, jobs, prefix=args.prefix, size=args.size,
        price_per_vcpu_min=args.price_per_vcpu_min, events=events,
    )
    report["selection"] = {"run": args.run, "since": since, "attempts": "latest"}
    _say(json.dumps(report, allow_nan=False) if args.json else runner_stats.format_report(report))
    return 0


def _failed_jobs(key: str, domain: str):
    from .runner_debug import FailedJobs, state_directory

    endpoint = os.environ.get("E2B_API_URL") or f"https://api.{domain}"
    return FailedJobs(state_directory(key, endpoint), _sandbox_cls())


def cmd_runners_debug(args: argparse.Namespace) -> int:
    from .runner_debug import job_reference

    if sum(bool(x) for x in (args.job, args.list, args.delete)) != 1:
        raise SbxError("runners debug: give one job, --list, or --delete JOB")
    if args.exec is not None and not args.job:
        raise SbxError("--exec needs a job to restore")
    _positive_seconds(args.timeout_min, "--timeout-min", MAX_TIMEOUT_MIN)
    _positive_seconds(args.timeout, "--timeout")
    if args.job or args.delete:
        job_reference(args.job or args.delete)
    key, domain = _credentials()
    store = _failed_jobs(key, domain)
    if args.list:
        for record in store.list():
            _say(json.dumps(record))
        return 0
    if args.delete:
        record = store.delete(args.delete)
        _say(f"deleted snapshot {record['snapshot_id']} for job {record['job_id']}")
        return 0
    record = store.find(args.job)
    sbx = _sdk_retry(
        _sandbox_cls().create,
        record["snapshot_id"], timeout=max(1, round(args.timeout_min * 60)),
        metadata={"sbx-debug-job": str(record["job_id"])}, lifecycle={"on_timeout": "kill"},
    )
    sid = shlex.quote(sbx.sandbox_id)
    _say(sbx.sandbox_id)
    _say(f"sbx exec {sid} -- 'cd /opt/actions-runner/_work && pwd && ls -la'")
    _say(f"sbx exec {sid} -- 'cat /path/to/file'")
    _say(f"sbx kill {sid}")
    if args.exec is not None:
        from e2b import CommandExitException

        try:
            result = sbx.commands.run(args.exec, timeout=args.timeout)
        except CommandExitException as exc:
            result = exc
        sys.stdout.write(_scrub(result.stdout))
        sys.stderr.write(_scrub(result.stderr))
        return result.exit_code
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

    p = sub.add_parser("cp", help="copy a file between the local machine and a sandbox")
    p.add_argument("source", help="local file path or ID:PATH")
    p.add_argument("target", help="local file path or ID:PATH")
    p.add_argument("--timeout", type=float, default=600, help="deadline per transfer attempt in seconds (default 600)")
    p.set_defaults(func=cmd_cp)

    p = sub.add_parser("list", help="list live sandboxes held by this key")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("templates", help="list CPU template aliases")
    p.add_argument("--json", action="store_true", help="print the raw template list (including GPU entries)")
    p.set_defaults(func=cmd_templates)

    p = sub.add_parser("kill", help="kill a sandbox")
    p.add_argument("sandbox_id")
    p.set_defaults(func=cmd_kill)

    from . import gpu

    gpu.register(sub, _Parser)

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
    r.add_argument("--keep-failed", type=int, nargs="?", const=5, default=0, metavar="N",
                   help="snapshot failed jobs; retain the newest N (default 5 when enabled)")
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

    r = rsub.add_parser("stats", help="job/step timing, runtime cost and hosted comparison (Actions read access)")
    r.add_argument("--repo", required=True, help="OWNER/REPO to inspect")
    selection = r.add_mutually_exclusive_group()
    selection.add_argument("--run", type=int, help="workflow run ID (latest attempt)")
    selection.add_argument("--since", help="runs created in this duration: 30m, 24h, 7d (default 24h)")
    r.add_argument("--prefix", default="sbx-", help="runner name prefix used by serve (default sbx-)")
    r.add_argument("--size", choices=["small", "standard"], default="small",
                   help="assumed size when jobs lack a small/standard size label (default small, 2 vCPU)")
    r.add_argument("--price-per-vcpu-min", type=float, default=0.002,
                   help="estimated dollars per vCPU-minute of job runtime (default 0.002)")
    r.add_argument("--serve-log", help="serve stdout JSONL, joined by runner name for VM-ready/reclaim timing")
    r.add_argument("--json", action="store_true", help="machine-readable report; unknown timings are null")
    r.set_defaults(func=cmd_runners_stats)

    r = rsub.add_parser("debug", help="restore, list, or delete retained failed-job snapshots")
    r.add_argument("job", nargs="?", help="job id or GitHub Actions job URL")
    r.add_argument("--list", action="store_true", help="print retained jobs as JSONL")
    r.add_argument("--delete", metavar="JOB", help="delete a job's snapshot")
    r.add_argument("--exec", metavar="CMD", help="run CMD in the restored machine")
    r.add_argument("--timeout-min", type=float, default=30, help="debug sandbox lifetime (default 30 minutes)")
    r.add_argument("--timeout", type=float, default=60, help="--exec command timeout (default 60 seconds)")
    r.set_defaults(func=cmd_runners_debug)
    return ap


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("agent-next-sandbox")
    except PackageNotFoundError:
        return "0+unknown"


def _dead_pipe_exit() -> int:
    """Drop pending output so shutdown flushes nowhere, and exit the way
    SIGPIPE would have ended the process."""
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        for stream in (sys.stdout, sys.stderr):
            try:
                os.dup2(devnull, stream.fileno())
            except (AttributeError, OSError):
                pass
    finally:
        os.close(devnull)
    return 141


def main(argv: list[str] | None = None) -> int:
    try:
        try:
            args = build_parser().parse_args(argv)
            try:
                rc = args.func(args)
            except SbxError as exc:
                _say(f"sbx: {exc}", err=True)
                rc = 2
            except BrokenPipeError:
                raise  # a stream without a real fd; handled by the outer catch
            except Exception as exc:  # SDK errors carry the gateway's message
                origin = type(exc).__module__.split(".")[0]
                name = "" if origin == "e2b" else f"{type(exc).__name__}: "
                _say(f"sbx: {name}{exc}", err=True)
                rc = 1
            return rc
        finally:
            # short writes stay buffered until interpreter shutdown, past the
            # catch below; flush here so a closed pipe exits the same way a
            # mid-stream one does (this also covers --version/--help, which
            # leave through SystemExit)
            sys.stdout.flush()
            sys.stderr.flush()
    except BrokenPipeError:
        return _dead_pipe_exit()


if __name__ == "__main__":
    sys.exit(main())
