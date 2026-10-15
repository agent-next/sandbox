#!/usr/bin/env python3
"""untrusted-code-isolation demo: one command, one disposable sandbox.

Creates an agent-next sandbox, clones this repository inside it, installs
the pinned judge toolchain, runs the judge self-test (10 single-edit
mutants must all be killed), then grades the known-good containment
runner against 10 hostile and 5 benign snippets — and always kills the
sandbox afterwards, confirming it is gone.

    python3 cookbook/untrusted-code-isolation/run.py [--ref main] [--keep]
                                           [--report-json OUT.json]
                                           [--artifacts DIR]

Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

Standard library only. Wall time per step is printed.

The sandbox is the outer boundary of the demo: the hostile snippets are
real fork bombs, memory balloons and disk fillers, so run the judge
inside a disposable sandbox (or a VM you own), never on a machine that
hosts anything you care about.

Transport discipline (the gateway restarts under load; a long-lived exec
stream is the casualty):

- every step (clone, setup, selftest, grade) is started DETACHED inside
  the sandbox — `setsid nohup ... &` — and the driver polls a status
  file with short `sbx exec` calls, each retried with backoff. A restart
  between polls costs one retry, not the run;
- the verdict is read back from a file, never through the stream that
  ran the grade;
- cleanup never claims more than it saw: `sbx kill` is retried, and the
  sandbox is reported gone only when `sbx list` actually answers and the
  id is absent. A failed kill or an unreadable list is a non-zero exit
  naming the sandbox id — never a "confirmed gone" we did not confirm.

Transport errors (`ConnectError: Error reading content`, the 503
"gateway is restarting", connection resets) are retried with backoff in
both directions of every call — the CLI prints them on either stream, and
a retry must not depend on which one a given error lands on.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

REPO = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/untrusted-code-isolation"
ARTIFACT = "examples/good/runner.py"
STEP_TIMEOUTS = {"clone": 300, "setup": 900, "selftest": 3600, "grade": 900}
POLL_INTERVAL = 15
RETRIES = 6
RETRY_BACKOFF = 5.0

# Transient transport failures. The gateway restarts under load and answers
# 503 "gateway is restarting" while it does; the SDK's exec stream dies with
# "ConnectError: Error reading content" when the restart lands mid-stream.
# Both are worth a backoff-and-retry, and neither is a verdict about the
# command that was running: the retry must happen above the step, not in it.
TRANSIENT = ("gateway is restarting", "ConnectError", "Error reading content",
             "Gateway Timeout", "Bad Gateway", "Connection reset",
             "Connection refused", "timed out", "SSLError")


def transient(proc):
    """True when a failed sbx call looks like a transport blip, not a result.

    The CLI prints errors to stderr but a few reach stdout, and a
    stdout-captured call puts the command's own output in stdout too, so
    both streams are searched.
    """
    blob = (proc.stdout or "") + (proc.stderr or "")
    return any(mark in blob for mark in TRANSIENT)


def die(msg, code=1):
    print("run.py: %s" % msg, file=sys.stderr)
    raise SystemExit(code)


def need_sbx():
    if not shutil.which("sbx"):
        die("sbx CLI not found: pip install "
            "'git+https://github.com/agent-next/sandbox#subdirectory=cli'")
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        die("no API key: export SBX_API_KEY (or E2B_API_KEY)")


def run(step, *args, timeout=None):
    """One local sbx call (create / kill / list); transport errors retry."""
    t0 = time.monotonic()
    last = None
    for attempt in range(1, RETRIES + 1):
        proc = subprocess.run(list(args), capture_output=True, text=True,
                              timeout=timeout and timeout + 60)
        last = proc
        if proc.returncode == 0 or not transient(proc):
            break
        wait = RETRY_BACKOFF * attempt
        print("  [%s] transport blip (%s); attempt %d/%d, retry in %.0f s"
              % (step, (proc.stderr or proc.stdout or "").strip().splitlines()
                 [-1][:80] if (proc.stderr or proc.stdout or "").strip()
                 else "unknown", attempt, RETRIES, wait), flush=True)
        time.sleep(wait)
    dt = time.monotonic() - t0
    status = "ok" if last.returncode == 0 else "exit %d" % last.returncode
    print("  [%s] %s ... %s (%.0f s)" % (step, " ".join(args[:3]), status, dt),
          flush=True)
    return last, dt


def shq(text):
    """Single-quote one shell word (list joined with spaces for a command)."""
    if not isinstance(text, str):
        text = " ".join(text)
    return "'%s'" % text.replace("'", "'\\''")


def sbx_exec(sbx_id, timeout, cmd):
    """One short `sbx exec`, retried through gateway restarts.

    Returns (proc, attempts); the caller decides what exit codes mean. A
    retried call's partial output is discarded: the caller re-runs the whole
    command, which is why every command here is idempotent (a read, a
    no-op rm, an append of one status line).
    """
    last = None
    for attempt in range(1, RETRIES + 1):
        proc = subprocess.run(
            ["sbx", "exec", sbx_id, "--timeout", str(timeout), "--"] + cmd,
            capture_output=True, text=True, timeout=timeout + 60)
        last = proc
        if proc.returncode == 0 or not transient(proc):
            return proc, attempt
        wait = RETRY_BACKOFF * attempt
        print("  [exec] transport blip (%s); attempt %d/%d, retry in %.0f s"
              % ((proc.stderr or proc.stdout or "").strip().splitlines()
                 [-1][:80] if (proc.stderr or proc.stdout or "").strip()
                 else "unknown", attempt, RETRIES, wait), flush=True)
        time.sleep(wait)
    return last, RETRIES


def detached_step(sbx_id, name, cmd, log_path, status_path, timeout):
    """Run a long step detached in the sandbox; poll its status file.

    The command is started with `setsid nohup ... &` and the exec returns
    immediately; the step appends its exit status to `status_path` when it
    finishes. The driver polls with short execs, so a gateway restart
    costs one retried poll, not the step. The driver deletes the status
    file before the step starts; if a poll ever finds more than one line
    in it, a previous step with the same path is still writing and the
    poll fails loudly instead of guessing.
    """
    t0 = time.monotonic()
    inner = "%s >>%s 2>&1; echo $? >>%s" % (
        " ".join(shq(part) for part in cmd), shq(log_path), shq(status_path))
    start = "setsid sh -c %s </dev/null >/dev/null 2>&1 &" % shq(inner)
    proc, attempts = sbx_exec(sbx_id, 120, ["sh", "-c", start])
    if proc.returncode != 0:
        die("could not start %s in sandbox %s (exit %d)%s\n%s"
            % (name, sbx_id, proc.returncode,
               " after %d attempts" % attempts if attempts > 1 else "",
               (proc.stderr or "").strip()[-800:]))
    print("  [%s] running detached in the sandbox (log %s)"
          % (name, log_path), flush=True)

    while True:
        time.sleep(POLL_INTERVAL)
        proc, _ = sbx_exec(sbx_id, 60,
                           ["sh", "-c",
                            "cat %s 2>/dev/null || echo running"
                            % shq(status_path)])
        out = (proc.stdout or "").strip()
        if out.count("\n") > 1:
            die("%s poll in sandbox %s: status file holds %d lines (%r); "
                "a previous step may still be writing — read %s"
                % (name, sbx_id, out.count("\n") + 1, out[:100], log_path))
        if out and out != "running":
            dt = time.monotonic() - t0
            print("  [%s] finished: exit %s (%.0f s)" % (name, out, dt),
                  flush=True)
            return int(out), dt
        if time.monotonic() - t0 > timeout:
            die("%s exceeded %d s in sandbox %s; it may still be running — "
                "read %s" % (name, timeout, sbx_id, log_path))
        print("  [%s] still running (%.0f s elapsed)"
              % (name, time.monotonic() - t0), flush=True)
        if time.monotonic() - t0 > timeout:
            die("%s exceeded %d s in sandbox %s; it may still be running — "
                "read %s" % (name, timeout, sbx_id, log_path))


def read_remote_file(sbx_id, path, what, timeout=60):
    proc, attempts = sbx_exec(sbx_id, timeout, ["cat", path])
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        die("could not read %s from sandbox %s (exit %d)%s\n%s"
            % (what, sbx_id, proc.returncode,
               " after %d attempts" % attempts if attempts > 1 else "",
               (proc.stderr or "").strip()[-800:]))
    return proc.stdout


def kill_and_confirm(sbx_id):
    """Kill the sandbox and confirm it is gone, or fail loudly.

    `sbx kill` answers "not found" after the sandbox is already gone, so
    either exit code counts as killed; what may never be claimed is the
    confirmation. That comes only from a later `sbx list` that succeeds
    and does not contain the id — a list that cannot be read is an
    unconfirmed cleanup and exits non-zero naming the id (a restart blip
    is absorbed by run()'s retries; what survives them is real).
    """
    proc, _ = run("kill", "sbx", "kill", sbx_id, timeout=120)
    if proc.returncode != 0 and not transient(proc):
        die("sbx kill %s failed (exit %d)\n%s"
            % (sbx_id, proc.returncode, (proc.stderr or "").strip()[-800:]), 2)
    time.sleep(2.0)
    proc, _ = run("list", "sbx", "list", timeout=60)
    if proc.returncode != 0:
        die("cleanup not confirmed: sbx list failed (exit %d); sandbox %s "
            "may still be live — kill it with: sbx kill %s\n%s"
            % (proc.returncode, sbx_id, sbx_id,
               (proc.stderr or "").strip()[-800:]), 2)
    if sbx_id in (proc.stdout or ""):
        die("cleanup not confirmed: sandbox %s still listed after kill; "
            "kill it with: sbx kill %s" % (sbx_id, sbx_id), 2)
    print("cleanup: sandbox %s killed and confirmed gone" % sbx_id)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main",
                    help="repository ref to clone inside the sandbox")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox up and print its id")
    ap.add_argument("--report-json", metavar="PATH",
                    help="write the verdict JSON here")
    ap.add_argument("--artifacts", metavar="DIR",
                    help="fetch each step's log from the sandbox into DIR "
                         "before it is killed (for RECEIPT.md and media)")
    args = ap.parse_args()

    total0 = time.monotonic()
    need_sbx()
    proc, _ = run("create", "sbx", "create", "--timeout-min", "30",
                  timeout=120)
    if proc.returncode != 0:
        die("sbx create failed: %s" % (proc.stderr or "").strip())
    sbx_id = proc.stdout.strip().splitlines()[-1]
    print("sandbox: %s (template default)" % sbx_id)

    verdict = None
    try:
        steps = (
            ("clone",
             ["git", "clone", "--depth", "1", "-b", args.ref, REPO, "sandbox"],
             "/tmp/uci-clone"),
            ("setup",
             ["bash", "sandbox/%s/judge/setup.sh" % DEMO_DIR],
             "/tmp/uci-setup"),
            ("selftest",
             ["bash", "sandbox/%s/judge/selftest.sh" % DEMO_DIR],
             "/tmp/uci-selftest"),
            ("grade",
             ["bash", "sandbox/%s/judge/grade.sh" % DEMO_DIR,
              "sandbox/%s/%s" % (DEMO_DIR, ARTIFACT),
              "--json", "/tmp/verdict.json"],
             "/tmp/uci-grade"),
        )
        for name, cmd, prefix in steps:
            status_path = prefix + ".status"
            proc, _ = sbx_exec(sbx_id, 60,
                               ["sh", "-c", "rm -f %s" % shq(status_path)])
            if proc.returncode != 0 and not transient(proc):
                die("could not clear %s in sandbox %s before %s (exit %d)"
                    % (status_path, sbx_id, name, proc.returncode))
            rc, _ = detached_step(sbx_id, name, cmd, prefix + ".log",
                                  status_path, STEP_TIMEOUTS[name])
            if rc != 0:
                log = read_remote_file(sbx_id, prefix + ".log",
                                       "%s log" % name)
                die("step %s failed in sandbox %s (exit %d); log tail:\n%s"
                    % (name, sbx_id, rc, log[-1200:]))

        if args.artifacts:
            os.makedirs(args.artifacts, exist_ok=True)
            for name, _cmd, prefix in steps:
                try:
                    log = read_remote_file(sbx_id, prefix + ".log",
                                           "%s log" % name, timeout=90)
                except SystemExit:
                    log = ""
                with open(os.path.join(args.artifacts, "%s.log" % name),
                          "w") as fh:
                    fh.write(log)
            # VERSIONS.txt is what setup.sh recorded about the sandbox's
            # toolchain; RECEIPT.md quotes it, so fetch it before the kill.
            proc, _ = sbx_exec(
                sbx_id, 60, ["cat", "sandbox/%s/judge/VERSIONS.txt" % DEMO_DIR])
            if proc.returncode == 0 and (proc.stdout or "").strip():
                with open(os.path.join(args.artifacts, "VERSIONS.txt"),
                          "w") as fh:
                    fh.write(proc.stdout)
            print("artifacts: step logs and VERSIONS.txt saved to %s"
                  % args.artifacts, flush=True)

        raw = read_remote_file(sbx_id, "/tmp/verdict.json", "verdict JSON")
        try:
            verdict = json.loads(raw)
        except json.JSONDecodeError as exc:
            die("verdict JSON from the sandbox is unreadable (%s):\n%s"
                % (exc, raw[-800:]))
    finally:
        if args.keep:
            print("run.py: --keep: sandbox %s left running; "
                  "kill it with: sbx kill %s" % (sbx_id, sbx_id))
        else:
            kill_and_confirm(sbx_id)

    print("total: %.0f s" % (time.monotonic() - total0))
    if not verdict:
        die("no verdict JSON returned from the sandbox")
    if args.report_json:
        with open(args.report_json, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
        print("wrote verdict JSON: %s" % args.report_json)
    if args.artifacts:
        with open(os.path.join(args.artifacts, "verdict.json"), "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)

    ok = all(g.get("pass") for g in verdict.get("gates", {}).values()) \
        and verdict.get("judge_intact", False)
    print("\nuntrusted-code-isolation demo: %s" % ("PASS" if ok else "FAIL"))
    for name, g in sorted(verdict.get("gates", {}).items()):
        line = "  gate %s: %s" % (name, "pass" if g.get("pass") else "FAIL")
        if name == "containment":
            line += "  (%d/%d hostile contained)" % (g.get("contained", 0),
                                                     g.get("total", 0))
        if name == "benign":
            line += "  (%d/%d benign exact)" % (g.get("matched", 0),
                                                g.get("total", 0))
        print(line)
        for problem in (g.get("problems") or [])[:5]:
            print("    %s" % problem)
    runs = verdict.get("runs", {})
    print("  hostile verdicts:")
    for name in ("fork_bomb", "memory_balloon", "infinite_loop",
                 "disk_filler", "read_shadow", "write_outside",
                 "outbound_socket", "background_daemon", "huge_stdout",
                 "sleep_forever"):
        r = runs.get(name, {})
        print("    %-18s %-8s %-12s %s"
              % (name, r.get("verdict", "?"), r.get("reason", "?"),
                 "ok" if r.get("pass") else "FAIL"))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
