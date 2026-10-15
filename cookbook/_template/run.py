#!/usr/bin/env python3
"""One-command run for the __NAME__ demo.

Creates a disposable agent-next sandbox, clones this repo at --ref
(default: main), runs judge/setup.sh, judge/selftest.sh and
judge/grade.sh on the known-good artifact, prints the verdict JSON, and
always kills the sandbox afterwards.

Needs the sbx CLI and SBX_API_KEY (or E2B_API_KEY) in the environment:
  pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"

Usage: run.py [--ref GIT_REF] [--keep] [--timeout-min N]
"""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = "https://github.com/agent-next/sandbox"
DEMO = "cookbook/__NAME__"


def sbx(*argv):
    """Run an sbx subcommand, return (output, exit_code)."""
    p = subprocess.run(["sbx", *argv], capture_output=True, text=True)
    return (p.stdout + p.stderr).strip(), p.returncode


def sbx_exec(sid, command, step_timeout=900):
    t0 = time.time()
    p = subprocess.run(["sbx", "exec", sid, "--timeout", str(step_timeout),
                        "--", "bash", "-lc", command],
                       capture_output=True, text=True)
    return p.stdout + p.stderr, p.returncode, time.time() - t0


def _gates_from_verdict(verdict):
    """Map the grade JSON's gates (dict or list shape) to result gates."""
    raw = verdict.get("gates", {})
    items = raw.items() if isinstance(raw, dict) else (
        (g.get("name", f"gate {i}"), g) for i, g in enumerate(raw))
    gates = []
    for name, g in items:
        g = g if isinstance(g, dict) else {}
        gates.append({
            "name": str(name),
            "pass": bool(g.get("pass", g.get("passed", False))),
            "measured": g.get("measured", g.get("detail", "")),
            "threshold": g.get("threshold", g.get("tolerance", "")),
        })
    return gates or [{"name": "TODO", "pass": False,
                      "measured": "", "threshold": ""}]


def write_result_manifest(verdict, ok, commit):
    """Refresh media/result.json from the grade JSON (schema:
    cookbook/tools/result.schema.json). The manifest feeds the in-chat
    result card, the demo gallery and the storyboard — keep headline,
    numbers and the ask_agent prompt in sync with README/RECEIPT.
    `commit` is the sandbox clone's HEAD the numbers were produced at."""
    tool = Path(__file__).resolve().parents[1] / "tools" / "result.py"
    spec = importlib.util.spec_from_file_location("cookbook_result", tool)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    demo_dir = Path(__file__).resolve().parent
    out = demo_dir / "media" / "result.json"
    mod.write_result(
        out,
        demo=demo_dir.name,
        headline="TODO: one sentence naming the measured hero result.",
        verdict="PASS" if ok else "FAIL",
        gates=_gates_from_verdict(verdict),
        numbers=[{"label": "TODO: hero number", "value": "TODO", "unit": "",
                  "source": "TODO: command or receipt line"}],
        hero={"kind": "image", "path": "media/result.png",
              "caption": "TODO: what the hero frame shows"},
        gallery=[
            {"kind": "image", "path": "media/loop.png",
             "caption": "agent loop + self-test kill rate"},
            {"kind": "video", "path": "media/demo.mp4",
             "poster": "media/result.png", "caption": "demo video"},
        ],
        launch={"command": f"python3 cookbook/{demo_dir.name}/run.py",
                "ask_agent": "TODO: the README \"Ask your agent\" prompt"},
        receipt="RECEIPT.md",
        sandbox_commit=commit if len(commit) == 40 else "0" * 40,
    )
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", default="main", help="git ref to clone (default: main)")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox running and print its id")
    ap.add_argument("--timeout-min", type=int, default=30,
                    help="sandbox lifetime in minutes (default: 30)")
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

        def step(name, command):
            t0 = time.time()
            out, rc, el = sbx_exec(sid, command)
            status = "ok" if rc == 0 else f"FAILED rc={rc}"
            print(f"[{el:6.1f}s] {name}: {status}")
            if rc != 0:
                print(out[-4000:])
                sys.exit(rc)
            return out

        step("clone", f"git clone --depth 1 -b {args.ref} {REPO} /tmp/repo")
        # The numbers are produced by the clone's judge, so the manifest
        # records the clone's commit — not the caller's local HEAD.
        out = step("clone-commit", "git -C /tmp/repo rev-parse HEAD")
        commit = out.split()[-1] if out.split() else ""
        d = f"/tmp/repo/{DEMO}"
        step("setup", f"cd {d} && bash judge/setup.sh")
        selftest_out = step("selftest", f"cd {d} && bash judge/selftest.sh")
        for line in selftest_out.splitlines():
            if line.startswith(("mutant ", "kill rate:", "determinism:")):
                print(f"    {line}")
        out = step("grade", f"cd {d} && bash judge/grade.sh examples/good")
        verdict = json.loads(out[out.index("{"):])
        print(json.dumps(verdict, indent=2))
        ok = verdict.get("verdict") == "PASS"
        manifest = write_result_manifest(verdict, ok, commit)
        print(f"manifest: {manifest}")
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
