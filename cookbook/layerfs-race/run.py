#!/usr/bin/env python3
"""One-command run for the layerfs-race demo.

Creates a disposable agent-next sandbox, clones this repo at --ref
(default: main), runs judge/setup.sh, judge/selftest.sh and
judge/grade.sh on the known-good artifact, prints the verdict JSON, and
always kills the sandbox afterwards.

Needs the sbx CLI and SBX_API_KEY (or E2B_API_KEY) in the environment:
  pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"

Usage: run.py [--ref GIT_REF] [--keep] [--timeout-min N]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = "https://github.com/agent-next/sandbox"
DEMO = "cookbook/layerfs-race"


def sbx(*argv):
    """Run an sbx subcommand, return (output, exit_code)."""
    p = subprocess.run(["sbx", *argv], capture_output=True, text=True)
    return (p.stdout + p.stderr).strip(), p.returncode


def sbx_exec(sid, command, step_timeout=120):
    t0 = time.time()
    p = subprocess.run(["sbx", "exec", sid, "--timeout", str(step_timeout),
                        "--", "bash", "-lc", command],
                       capture_output=True, text=True)
    return p.stdout + p.stderr, p.returncode, time.time() - t0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", default="main", help="git ref to clone (default: main)")
    ap.add_argument("--local", action="store_true",
                    help="upload the local checkout instead of cloning "
                         "(for testing unpushed changes; --ref is ignored)")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox running and print its id")
    ap.add_argument("--timeout-min", type=int, default=60,
                    help="sandbox lifetime in minutes (default: 60)")
    args = ap.parse_args()

    if not shutil.which("sbx"):
        sys.exit("sbx CLI not found; install with: pip install "
                 "\"git+https://github.com/agent-next/sandbox#subdirectory=cli\"")
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        sys.exit("set SBX_API_KEY (or E2B_API_KEY) in the environment")

    sid = None
    try:
        t0 = time.time()
        out, rc = sbx("create", "--timeout-min", str(args.timeout_min))
        if rc != 0:
            sys.exit(f"sbx create failed: {out}")
        sid = out.splitlines()[-1].strip()
        print(f"[{time.time()-t0:5.1f}s] sandbox {sid}")

        def step(name, command, step_timeout=120):
            # Redirect step output to a file and cat it back: detached children
            # (e.g. `start-docker`'s sudo+dockerd) inherit the exec's stdout fd
            # and hold the stream open forever, which makes sbx exec time out.
            cmd = f"({command}) > /tmp/step-{name}.log 2>&1; rc=$?; cat /tmp/step-{name}.log; exit $rc"
            out, rc, el = sbx_exec(sid, cmd, step_timeout)
            status = "ok" if rc == 0 else f"FAILED rc={rc}"
            print(f"[{el:6.1f}s] {name}: {status}")
            if rc != 0:
                print(out[-4000:])
                sys.exit(rc)
            return out

        if args.local:
            # Upload the local demo dir as a tarball (base64 through sbx
            # exec), for testing changes that are not pushed yet.
            import base64
            import tarfile
            import tempfile

            demo_dir = Path(__file__).resolve().parent
            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tf:
                with tarfile.open(tf.name, "w:gz") as tar:
                    tar.add(demo_dir, arcname=demo_dir.name)
                payload = base64.b64encode(Path(tf.name).read_bytes()).decode()
            step("upload", "mkdir -p /tmp/repo/cookbook && "
                 f"echo {payload} | base64 -d > /tmp/demo.tar.gz && "
                 "tar xzf /tmp/demo.tar.gz -C /tmp/repo/cookbook")
            p = subprocess.run(["git", "-C", str(demo_dir), "rev-parse", "HEAD"],
                               capture_output=True, text=True)
            commit = p.stdout.strip()
        else:
            step("clone", f"git clone --depth 1 -b {args.ref} {REPO} /tmp/repo")
            out = step("clone-commit", "git -C /tmp/repo rev-parse HEAD")
            commit = out.split()[-1] if out.split() else ""
        d = f"/tmp/repo/{DEMO}"
        step("setup", f"cd {d} && bash judge/setup.sh", 2700)
        selftest_out = step("selftest", f"cd {d} && bash judge/selftest.sh", 3600)
        for line in selftest_out.splitlines():
            if "mutant KILLED" in line or "kill rate" in line or "determinism" in line:
                print(f"    {line}")
        out = step("grade", f"cd {d} && bash judge/grade.sh examples/good", 1200)
        verdict = json.loads(out[out.index("{"):])
        print(json.dumps(verdict, indent=2))
        ok = verdict.get("verdict") == "PASS"
        print(f"commit: {commit}")
        print(f"verdict: {verdict.get('verdict')}")
        sys.exit(0 if ok else 1)
    finally:
        if sid:
            if args.keep:
                print(f"kept sandbox {sid} (kill with: sbx kill {sid})")
            else:
                _, kill_rc = sbx("kill", sid)
                out, list_rc = sbx("list")
                if list_rc != 0 or sid in out:
                    why = "sbx list failed" if list_rc != 0 else "still in sbx list"
                    print(f"WARNING: cleanup of sandbox {sid} not confirmed "
                          f"({why}, kill rc={kill_rc}); kill it with: sbx kill {sid}",
                          file=sys.stderr)
                    sys.exit(2)
                print(f"sandbox {sid} removed")


if __name__ == "__main__":
    main()
