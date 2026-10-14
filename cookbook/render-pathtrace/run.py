#!/usr/bin/env python3
"""Standard-library-only workstation runner; all rendering happens remotely."""

import argparse
import json
import os
import secrets
import shlex
import shutil
import subprocess
import sys
import time


def sbx(*args):
    result = subprocess.run(["sbx", *args], text=True, capture_output=True, timeout=150)
    if result.returncode:
        raise RuntimeError(f"sbx {args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def remote_step(sid, label, command, budget):
    start = time.monotonic()
    prefix = "/tmp/pathtrace-" + secrets.token_hex(6)
    job = (f"{command}; code=$?; printf '%s' \"$code\" > {prefix}.exit")
    launch = f"nohup sh -c {shlex.quote(job)} >{prefix}.log 2>&1 </dev/null &"
    sbx("exec", sid, "--timeout", "120", launch)
    probe = (
        "import json,pathlib; "
        f"p=pathlib.Path({prefix!r}); e=pathlib.Path(str(p)+'.exit'); "
        "print(json.dumps({'done':e.exists(),"
        "'code':int(e.read_text()) if e.exists() else None,"
        "'log':pathlib.Path(str(p)+'.log').read_text() if e.exists() else ''}))"
    )
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
        time.sleep(3)
    raise RuntimeError(f"{label} exceeded {budget}s in sandbox {sid}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="main")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    if not shutil.which("sbx"):
        parser.error("install the sbx CLI first; see README.md")
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        parser.error("set SBX_API_KEY or E2B_API_KEY")
    if not 0 <= args.seed < 32000:
        parser.error("--seed must be in [0, 32000)")
    sid = None
    failed = False
    try:
        start = time.monotonic()
        sid = sbx("create", "--timeout-min", "30")
        if not sid or len(sid.split()) != 1:
            raise RuntimeError(f"invalid sandbox id: {sid!r}")
        print(f"create: sandbox={sid} wall={time.monotonic()-start:.1f}s", flush=True)
        remote_step(sid, "clone",
                    "git clone --depth 1 -b " + shlex.quote(args.ref)
                    + " https://github.com/agent-next/sandbox /tmp/pathtrace-repo", 180)
        directory = "/tmp/pathtrace-repo/cookbook/render-pathtrace"
        prefix = "cd " + directory + " && "
        remote_step(sid, "setup", prefix + "sh judge/setup.sh", 300)
        remote_step(sid, "selftest", prefix + f"sh judge/selftest.sh --seed {args.seed}", 2400)
        output = remote_step(sid, "grade", prefix +
                             f"sh judge/grade.sh examples/good/scene.json --seed {args.seed}",
                             630)
        verdict = json.loads(output.strip().splitlines()[-1])
        if not verdict["pass"]:
            raise RuntimeError("grade did not pass")
        print(f"PASS: five gates; backend={verdict['backend']}; "
              f"adapter={verdict['adapter']}", flush=True)
    except (Exception, KeyboardInterrupt) as exc:
        failed = True
        print(str(exc), file=sys.stderr)
    finally:
        if sid:
            if args.keep:
                print(f"Kept sandbox: {sid}", flush=True)
            else:
                try:
                    sbx("kill", sid)
                    inventory = sbx("list")
                    ids = {line.split()[0] for line in inventory.splitlines() if line.strip()}
                    if sid in ids:
                        raise RuntimeError("id still present in sbx list")
                    print(f"cleanup confirmed: {sid}", flush=True)
                except Exception as exc:
                    failed = True
                    print(f"cleanup unconfirmed for sandbox {sid}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
