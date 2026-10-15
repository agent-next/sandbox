#!/usr/bin/env python3
"""Render and test the studio in a fresh blender sandbox, then confirm deletion."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REMOTE = "/tmp/studio-repo/cookbook/blender-studio"


def sbx(*args):
    try:
        result = subprocess.run(["sbx", *args], text=True, capture_output=True, timeout=150)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"sbx {args[0]} timed out") from None
    if result.returncode:
        raise RuntimeError(f"sbx {args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def create(minutes):
    output = sbx("create", "--template", "blender", "--timeout-min", str(minutes))
    # The id is the last line; anything before it is CLI chatter, not a failure.
    candidate = output.splitlines()[-1].strip() if output else ""
    if not re.fullmatch(r"[a-zA-Z0-9-]{8,80}", candidate):
        raise RuntimeError("create returned no sandbox id")
    return candidate


def remote_step(sid, label, command, budget):
    start = time.monotonic()
    token = os.urandom(6).hex()
    prefix = f"/tmp/studio-{token}"
    job = (f"{command}; code=$?; printf '%s' \"$code\" > {prefix}.exit.tmp; "
           f"mv {prefix}.exit.tmp {prefix}.exit")
    sbx("exec", sid, "--timeout", "120",
        f"nohup sh -c {shlex.quote(job)} >{prefix}.log 2>&1 </dev/null &")
    probe = (
        "import json,pathlib; "
        f"p=pathlib.Path({prefix!r}); e=pathlib.Path(str(p)+'.exit'); "
        "print(json.dumps({'done':e.exists(),"
        "'code':int(e.read_text()) if e.exists() else None,"
        "'log':pathlib.Path(str(p)+'.log').read_text() if e.exists() else ''}))")
    while time.monotonic() - start < budget:
        state = json.loads(sbx("exec", sid, "--timeout", "120",
                               "python3 -c " + shlex.quote(probe)))
        if state["done"]:
            print(state["log"], flush=True)
            print(f"{label}: exit={state['code']} wall={time.monotonic()-start:.1f}s",
                  flush=True)
            if state["code"]:
                raise RuntimeError(f"{label} failed in sandbox {sid}")
            return state["log"]
        time.sleep(2)
    raise RuntimeError(f"{label} exceeded {budget}s in sandbox {sid}")


def snapshot():
    """Ship only judge/source files, not media, credentials, or working outputs."""
    files = {}
    for pattern in ("judge/*.py", "judge/*.sh", "examples/good/*.py"):
        for path in sorted(HERE.glob(pattern)):
            files[path.relative_to(HERE).as_posix()] = base64.b64encode(
                path.read_bytes()).decode()
    encoded = json.dumps(files, sort_keys=True)
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    code = ("import base64,json,pathlib; "
            f"root=pathlib.Path({REMOTE!r}); files=json.loads({encoded!r}); "
            "[(root/name).parent.mkdir(parents=True,exist_ok=True) for name in files]; "
            "[(root/name).write_bytes(base64.b64decode(data)) for name,data in files.items()]; "
            f"print('source snapshot sha256={digest}')")
    return "python3 -c " + shlex.quote(code)


def cleanup(sid):
    error = None
    for attempt in range(3):
        try:
            sbx("kill", sid)
        except Exception as exc:
            error = exc
        try:
            inventory = sbx("list")
            ids = {line.split()[0] for line in inventory.splitlines() if line.strip()}
            if sid not in ids:
                print(f"cleanup confirmed: {sid} absent from sbx list", flush=True)
                return
        except Exception as exc:
            error = exc
        time.sleep(attempt + 1)
    raise RuntimeError(f"cleanup unconfirmed for sandbox {sid}: {error or 'id still listed'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="main", help="public repository branch or tag to clone")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        parser.error("set SBX_API_KEY or E2B_API_KEY")
    if not shutil.which("sbx"):
        parser.error("install sbx; see README.md")
    if not 0 <= args.seed < 32000:
        parser.error("--seed must be in [0, 32000)")
    sid, failed = None, False
    start = time.monotonic()
    try:
        before = time.monotonic()
        sid = create(30)
        print(f"create: sandbox={sid} template=blender wall={time.monotonic()-before:.1f}s",
              flush=True)
        remote_step(sid, "clone",
                    "git clone --depth 1 -b " + shlex.quote(args.ref) +
                    " https://github.com/agent-next/sandbox /tmp/studio-repo && "
                    "git -C /tmp/studio-repo rev-parse HEAD", 180)
        # Keep unpublished local demo code runnable without pushing the user's branch.
        # The clone SHA and exact source snapshot digest are printed separately.
        remote_step(sid, "snapshot", snapshot(), 120)
        prefix = "cd " + REMOTE + " && "
        remote_step(sid, "setup", prefix + "sh judge/setup.sh", 60)
        remote_step(sid, "selftest", prefix +
                    f"sh judge/selftest.sh --seed {args.seed}", 600)
        output = remote_step(sid, "grade", prefix +
                             f"sh judge/grade.sh examples/good/scene.py --seed {args.seed}",
                             140)
        verdict = json.loads(output.strip().splitlines()[-1])
        if not verdict["pass"]:
            raise RuntimeError("grade did not pass")
        print(f"PASS: five gates; seed={args.seed}; Blender {verdict['blender']}; "
              f"time-to-result={time.monotonic()-start:.1f}s", flush=True)
    except (Exception, KeyboardInterrupt) as exc:
        failed = True
        message = str(exc)
        for name in ("SBX_API_KEY", "E2B_API_KEY"):
            if os.environ.get(name):
                message = message.replace(os.environ[name], "[redacted]")
        print(message, file=sys.stderr)
        if sid is None:
            print("No sandbox id was confirmed. A lost create reply can leave a "
                  "sandbox alive; inspect sbx list before retrying.", file=sys.stderr)
    finally:
        if sid:
            if args.keep:
                print(f"Kept sandbox: {sid}", flush=True)
            else:
                try:
                    cleanup(sid)
                except Exception as exc:
                    failed = True
                    print(str(exc), file=sys.stderr)
    print(f"run: exit={1 if failed else 0} wall={time.monotonic()-start:.1f}s", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
