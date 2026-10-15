#!/usr/bin/env python3
"""One-command run for the aicad-freecad-mcp demo.

Creates a disposable agent-next sandbox, and inside it:
  1. clones this repo (--ref, default main),
  2. runs judge/setup.sh (pinned FreeCAD 1.0.1 + freecad-mcp + judge stack),
  3. starts the FreeCAD GUI under Xvfb (the freecad-mcp addon auto-starts its
     RPC server on 127.0.0.1:9875) and the freecad-mcp MCP server,
  4. drives the MCP server with a scripted client that executes the checked-in
     agent build scripts inside FreeCAD, producing examples/good/<part>/,
  5. runs judge/selftest.sh and judge/grade.sh on each delivered part,
  6. prints the verdict JSONs and a short human summary,
  7. always kills the sandbox and confirms with sbx list.

Python 3.10+, standard library only. Needs the sbx CLI and SBX_API_KEY (or
E2B_API_KEY) in the environment.

No LLM key is used anywhere: the agent's build scripts are checked in, so the
run is deterministic. README.md shows the full loop a user's own agent would
follow instead.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

REPO_URL = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/aicad-freecad-mcp"
RPC_PORT = 9875


class Step:
    def __init__(self, name):
        self.name = name
        self.t0 = time.time()

    def done(self, detail=""):
        print("[%5.1fs] %s %s" % (time.time() - self.t0, self.name, detail))


def run(cmd, **kw):
    return subprocess.run(cmd, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main", help="repo ref to clone (default: main)")
    ap.add_argument("--timeout-min", type=int, default=30)
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox up and print its id")
    args = ap.parse_args()

    t_start = time.time()
    if not shutil.which("sbx"):
        print("FATAL: sbx CLI not found. pip install "
              "\"git+https://github.com/agent-next/sandbox#subdirectory=cli\"",
              file=sys.stderr)
        return 2
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        print("FATAL: SBX_API_KEY (or E2B_API_KEY) not in the environment",
              file=sys.stderr)
        return 2

    # -- create ------------------------------------------------------------
    step = Step("create sandbox")
    res = run(["sbx", "create", "--timeout-min", str(args.timeout_min)],
              capture_output=True, text=True)
    if res.returncode != 0:
        print("FATAL: sbx create failed: %s" % res.stderr.strip(), file=sys.stderr)
        return 2
    m = re.search(r"(sbx-[0-9a-zA-Z-]+)", res.stdout)
    if not m:
        print("FATAL: could not parse sandbox id from: %r" % res.stdout,
              file=sys.stderr)
        return 2
    sbx_id = m.group(1)
    step.done(sbx_id)

    def in_sandbox(script, timeout_s=1500):
        """Run a bash script inside the sandbox via sbx exec."""
        r = run(["sbx", "exec", "--timeout", str(timeout_s), sbx_id,
                 "bash -lc %s" % json.dumps(script)], capture_output=True,
                text=True)
        return r

    verdicts = {}
    try:
        # -- setup ---------------------------------------------------------
        step = Step("judge/setup.sh")
        script = (
            "set -e\n"
            "git clone --depth 1 -b %(ref)s %(repo)s /tmp/sandbox\n"
            "cd /tmp/sandbox/%(demo)s\n"
            "bash judge/setup.sh\n"
            "echo SETUP_DONE\n" % {"ref": args.ref, "repo": REPO_URL,
                                    "demo": DEMO_DIR})
        r = in_sandbox(script, timeout_s=2400)
        if r.returncode != 0 or "SETUP_DONE" not in r.stdout:
            print("FATAL: setup failed in sandbox %s:\n%s\n%s"
                  % (sbx_id, r.stdout[-2000:], r.stderr[-2000:]), file=sys.stderr)
            return 3
        step.done()

        # -- tool pipeline (the real thing, no LLM) ------------------------
        step = Step("drive FreeCAD via MCP")
        script = (
            "set -e\n"
            "cd /tmp/sandbox/%(demo)s\n"
            "FREECAD_DIR=$HOME/freecad-1.0.1\n"
            "xvfb-run -a -s \"-screen 0 1280x1024x24\" "
            "$FREECAD_DIR/usr/bin/freecad > /tmp/freecad.log 2>&1 &\n"
            "MCP=$HOME/.venvs/freecad-mcp/bin/freecad-mcp\n"
            "python3 driver/drive_freecad.py --mcp-command $MCP "
            " --freecadcmd $FREECAD_DIR/usr/bin/freecadcmd\n"
            "pkill -f freecad || true\n"
            "echo DRIVE_DONE\n" % {"demo": DEMO_DIR})
        r = in_sandbox(script, timeout_s=1800)
        if r.returncode != 0 or "DRIVE_DONE" not in r.stdout:
            print("FATAL: MCP drive failed in sandbox %s:\n%s\n%s"
                  % (sbx_id, r.stdout[-3000:], r.stderr[-3000:]), file=sys.stderr)
            return 3
        step.done(r.stdout.strip().splitlines()[-2] if r.stdout.count("\n") else "")

        # -- selftest -------------------------------------------------------
        step = Step("judge/selftest.sh")
        r = in_sandbox(
            "cd /tmp/sandbox/%s && bash judge/selftest.sh" % DEMO_DIR,
            timeout_s=2400)
        verdicts["selftest"] = r.stdout
        if r.returncode != 0:
            print("FATAL: selftest failed:\n%s" % r.stdout[-3000:], file=sys.stderr)
            return 3
        kill = re.search(r"kill rate: (\d+)/(\d+) = (\d+)%", r.stdout)
        step.done("kill rate %s" % kill.group(0) if kill else "")

        # -- grade ----------------------------------------------------------
        step = Step("judge/grade.sh")
        all_ok = True
        for part in ("bushing", "plate", "bracket"):
            r = in_sandbox(
                "cd /tmp/sandbox/%(demo)s && bash judge/grade.sh examples/good/%(part)s "
                "--json /tmp/v-%(part)s.json && cat /tmp/v-%(part)s.json"
                % {"demo": DEMO_DIR, "part": part}, timeout_s=900)
            ok = r.returncode == 0
            all_ok = all_ok and ok
            try:
                verdicts[part] = json.loads(r.stdout[r.stdout.index("{"):])
            except (ValueError, IndexError):
                verdicts[part] = {"error": r.stdout[-500:], "pass": False}
                all_ok = False
        if not all_ok:
            print("GRADE FAILED:\n%s" % json.dumps(verdicts, indent=1),
                  file=sys.stderr)
            return 4
        step.done("all parts pass")
    finally:
        # -- cleanup (always) ------------------------------------------------
        if args.keep:
            print("[keep] sandbox %s left running for exploration" % sbx_id)
        else:
            step = Step("kill sandbox")
            killed = run(["sbx", "kill", sbx_id], capture_output=True, text=True)
            time.sleep(2)
            listing = run(["sbx", "list"], capture_output=True, text=True)
            if killed.returncode != 0 or sbx_id in listing.stdout:
                print("FATAL: could not confirm sandbox %s is gone "
                      "(kill rc=%s, still listed: %s)"
                      % (sbx_id, killed.returncode, sbx_id in listing.stdout),
                      file=sys.stderr)
                sys.exit(5)
            step.done("confirmed gone")

    # -- summary ------------------------------------------------------------
    print("\n=== aicad-freecad-mcp demo summary (ref %s) ===" % args.ref)
    for part in ("bushing", "plate", "bracket"):
        v = verdicts.get(part, {})
        gates = v.get("gates", {})
        npass = sum(1 for g in gates.values() if g.get("pass"))
        vol = gates.get("brep", {}).get("volume_mm3", "?")
        print("  %-8s %d/%d gates pass, volume %s mm^3"
              % (part, npass, len(gates), vol))
    print("  wall time: %.0f s" % (time.time() - t_start))
    print("verdicts:")
    for part in ("bushing", "plate", "bracket"):
        print(json.dumps(verdicts.get(part, {}), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
