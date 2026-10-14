#!/usr/bin/env python3
"""One-command run for the rf-openems demo.

Creates a disposable agent-next sandbox, clones this repository at `--ref`,
installs the pinned MEEP environment, runs judge/selftest.sh, then
judge/grade.sh on the known-good example, prints the verdict JSON and a
short summary, and *always* tears the sandbox down.

Usage:
    python3 run.py [--ref main] [--keep]
"""
import argparse, json, os, shlex, subprocess, sys, time

REPO = "https://github.com/agent-next/sandbox"
DEMO = "cookbook/rf-openems"


def run(cmd, check=True, capture=True, timeout=None):
    print(f"+ {shlex.join(cmd) if isinstance(cmd, list) else cmd}", flush=True)
    t0 = time.time()
    if isinstance(cmd, list):
        r = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout)
    else:
        r = subprocess.run(cmd, shell=True, capture_output=capture, text=True, timeout=timeout)
    dt = time.time() - t0
    if check and r.returncode != 0:
        sys.stderr.write((r.stdout or "")[-3000:] + (r.stderr or "")[-3000:])
        raise SystemExit(f"command failed ({r.returncode}): {cmd}")
    return r, dt


def sbx(*args, **kw):
    return run(["sbx", *args], **kw)


def sbx_exec(sid, script, **kw):
    run(["sbx", "exec", sid, "--", "bash", "-c", script], **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--timeout-min", type=int, default=60)
    args = ap.parse_args()

    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        sys.exit("set SBX_API_KEY (or E2B_API_KEY) in the environment first")

    sid = None
    cleaned = False
    walls = {}
    try:
        t0 = time.time()
        r, _ = sbx("create", "--timeout-min", str(args.timeout_min))
        sid = r.stdout.strip().splitlines()[-1].split()[-1]
        walls["create"] = round(time.time() - t0, 1)
        print(f"sandbox id: {sid}")

        t0 = time.time()
        sbx_exec(sid, f"git clone --depth 1 -b {shlex.quote(args.ref)} {shlex.quote(REPO)} w")
        walls["clone"] = round(time.time() - t0, 1)

        t0 = time.time()
        sbx_exec(sid, f"bash w/{DEMO}/judge/setup.sh")
        walls["setup"] = round(time.time() - t0, 1)

        t0 = time.time()
        sbx_exec(sid, f"bash w/{DEMO}/judge/selftest.sh")
        walls["selftest"] = round(time.time() - t0, 1)

        t0 = time.time()
        sbx_exec(sid, f"bash w/{DEMO}/judge/grade.sh w/{DEMO}/examples/good/antenna.py --json /tmp/verdict.json")
        walls["grade"] = round(time.time() - t0, 1)

        r, _ = sbx("exec", sid, "--", "cat", "/tmp/verdict.json")
        verdict = json.loads(r.stdout)
        print("\n=== verdict ===")
        print(json.dumps(verdict, indent=1))
        print("summary:", "PASS" if verdict.get("all_pass") else "FAIL")
        ok = bool(verdict.get("all_pass"))
    except Exception as e:
        print(f"!!!!!!!!!!!!!!!! error: {e}", file=sys.stderr)
        ok = False
    finally:
        if sid and not args.keep:
            try:
                sbx("kill", sid)
                r, _ = sbx("list")
                cleaned = sid not in r.stdout
            except Exception as e:
                print(f"cleanup problem for sandbox {sid}: {e}", file=sys.stderr)
        elif sid:
            print(f"kept sandbox: {sid}")
            cleaned = True

    print("wall times (s):", json.dumps(walls))
    if sid and not cleaned:
        print(f"!!! sandbox {sid} could not be confirmed killed")
        return 2
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
