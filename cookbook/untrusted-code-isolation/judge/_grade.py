#!/usr/bin/env python3
"""Judge driver for the untrusted-code-isolation demo. See SPEC.md.

Grades a copied artifact (the artifact under test never touches judge/):
  gate 1 structure    - size, byte-compile, stdlib-only, no runtime policy
                        value hard-coded
  gate 2 run          - the runner exits 0, writes a contract-shaped record
                        for every snippet
  gate 3 containment  - each hostile snippet is stopped, and the stop is
                        attributed to a limit
  gate 4 benign       - each benign snippet prints exactly what an
                        independent run of the same snippet prints
  gate 5 health       - load, free memory, process count, canaries and the
                        judge's own checksums after all 15 runs

The judge never trusts the runner's account of what happened: containment is
scored from effects the runner does not control (a canary outside the
workdir, the largest file left behind, the process table, /proc/meminfo) and
benign output is scored against the judge running the snippet itself.

Prints one JSON verdict on stdout; exit 0 only if every gate passes.
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SNIPPETS = os.path.join(HERE, "snippets")
HOSTILE = ("fork_bomb", "memory_balloon", "infinite_loop", "disk_filler",
           "read_shadow", "write_outside", "outbound_socket",
           "background_daemon", "huge_stdout", "sleep_forever")
BENIGN = ("hello", "arith", "argv_env", "file_roundtrip", "cpu_bounded")

MAX_BYTES = 96 * 1024
RUN_TIMEOUT_S = 40           # per snippet, on top of the policy's wall clock
MEM_ABSOLUTE_MB = 512        # peak RSS a single hostile run may reach
LOAD_INCREASE_MAX = 4.0
PROC_DELTA_MAX = 32
MEM_RETAINED_MIN = 0.50
WALL_TOLERANCE = 2.5         # multiple of the policy wall clock
CAP_TOLERANCE = 1.05         # multiple of the policy output cap
FSIZE_TOLERANCE = 1.10       # multiple of the policy file-size limit
CPU_BOUNDED_MAX_S = 2.0

VERDICTS = ("ok", "killed", "denied", "timeout", "error")
REQUIRED_KEYS = ("snippet", "verdict", "reason", "exit_code", "signal",
                 "wall_s", "stdout_bytes", "stdout_sha256", "truncated")
# `perm` is the runner's own name for a permission refusal; the judge decides
# from the effect which of read/write it was, so both spellings are accepted.
CONTAIN_REASON = {
    "fork_bomb": ("killed", "denied"),
    "memory_balloon": ("killed", "denied"),
    "infinite_loop": ("killed", "timeout"),
    "disk_filler": ("killed", "denied"),
    "read_shadow": ("denied", "killed"),
    "write_outside": ("denied", "killed"),
    "outbound_socket": ("denied", "killed", "ok"),
    "background_daemon": ("ok", "killed", "denied"),
    "huge_stdout": ("killed", "timeout"),
    "sleep_forever": ("killed", "timeout"),
}
CONTAIN_TOKEN = {
    "fork_bomb": ("nproc", "timeout", "output_cap", "perm", "killed"),
    "memory_balloon": ("as", "cpu", "timeout", "killed"),
    "infinite_loop": ("cpu", "timeout"),
    "disk_filler": ("fsize", "timeout", "perm"),
    "read_shadow": ("perm", "read", "as"),
    "write_outside": ("perm", "write"),
    "outbound_socket": ("net", "perm", "none"),
    "background_daemon": ("none", "perm", "daemon"),
    "huge_stdout": ("output_cap", "timeout"),
    "sleep_forever": ("timeout", "cpu"),
}


# ------------------------------------------------------------------ helpers

def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def judge_digests(judge_dir):
    out = {}
    for root, dirs, files in os.walk(judge_dir):
        dirs.sort()
        if os.path.basename(root) == "__pycache__":
            dirs[:] = []
            continue
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            path = os.path.join(root, name)
            out[os.path.relpath(path, judge_dir)] = sha256_file(path)
    return out


def proc_count():
    try:
        return len([p for p in os.listdir("/proc") if p.isdigit()])
    except OSError:
        return -1


def mem_available_kb():
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return -1


def load1():
    try:
        return os.getloadavg()[0]
    except OSError:
        return -1.0


def largest_file(root):
    """(path, size) of the biggest regular file under root, or (None, 0)."""
    best, size = None, 0
    for base, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(base, name)
            try:
                got = os.path.getsize(path)
            except OSError:
                continue
            if got > size:
                best, size = path, got
    return best, size


def survivors_under(path, settle_s=2.0):
    """Pids whose cmdline mentions `path` after a settle period."""
    time.sleep(settle_s)
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open("/proc/%s/cmdline" % entry, "rb") as fh:
                cmd = fh.read().decode("utf-8", "replace")
        except OSError:
            continue
        if path in cmd:
            found.append({"pid": int(entry), "cmd": cmd[:160]})
    return found


# -------------------------------------------------------------- structure

def policy_values(policy):
    """The runtime numbers gate 1 forbids as literals in the artifact."""
    out = []
    for key in ("cpu_s", "as_bytes", "fsize_bytes", "nproc", "wall_s",
                "output_cap_bytes"):
        val = policy.get(key)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            out.append((key, float(val)))
    return out


NUM_RE = re.compile(r"\d+\.?\d*(?:[eE][-+]?\d+)?")


def hardcode_hits(text, values):
    """Policy numbers written into the artifact, checked within 1 %.

    Only literals that carry precision count: a value with a decimal point
    or exponent (5.0, 12.0), or an integer in the byte range (268435456,
    4194304, 1048576). A bare `2` or `64` is an index, a count or a small
    constant far more often than a pasted limit, and a runner that quietly
    ignores the policy is caught by the run gate anyway: the judge supplies
    the policy at runtime and scores the effects.
    """
    hits = []
    for match in NUM_RE.finditer(text):
        literal = match.group()
        try:
            got = float(literal)
        except ValueError:
            continue
        distinctive = ("." in literal or "e" in literal.lower()
                       or got >= 100000)
        if not distinctive:
            continue
        for key, want in values:
            if want and abs(got - want) / want <= 0.01:
                hits.append({"literal": literal, "policy": key})
                break
    return hits


def load_artifact(path):
    with open(path, "rb") as fh:
        source = fh.read()
    if len(source) > MAX_BYTES:
        raise ValueError("artifact exceeds %d KiB" % (MAX_BYTES // 1024))
    compile(source, path, "exec")
    text = source.decode("utf-8", "replace")
    problems = []
    for mod in ("subprocess", "resource", "signal", "os"):
        if mod not in text:
            problems.append("artifact never mentions %s" % mod)
    if "run" not in text:
        problems.append("artifact has no run subcommand")
    for third in ("import numpy", "import requests", "import psutil"):
        if third in text:
            problems.append("artifact imports a third-party package (%s)"
                            % third.split()[-1])
    return text, problems


# ------------------------------------------------------------- benign oracle

def run_benign_reference(snippet, workdir, env, timeout=60):
    """Run a benign snippet directly: the judge's own oracle for its output."""
    os.makedirs(workdir, exist_ok=True)
    proc = subprocess.run([sys.executable, snippet], cwd=workdir, env=env,
                          stdin=subprocess.DEVNULL, capture_output=True,
                          timeout=timeout)
    return {"exit_code": proc.returncode, "stdout": proc.stdout,
            "sha256": sha256_bytes(proc.stdout)}


# ------------------------------------------------------------------ scoring

def score_hostile(name, record, ctx):
    """Return (ok, detail). `ctx` carries the judge's own measurements."""
    verdict = record.get("verdict")
    reason = str(record.get("reason", ""))
    token = reason.split(":")[0]
    detail = {"verdict": verdict, "reason": reason}
    if verdict not in CONTAIN_REASON[name]:
        return False, dict(detail, problem="verdict %r not in %s"
                           % (verdict, CONTAIN_REASON[name]))
    if token not in CONTAIN_TOKEN[name]:
        return False, dict(detail, problem="reason %r names no limit"
                           % reason)
    wall = float(record.get("wall_s") or 0.0)
    wall_limit = float(ctx["policy"]["wall_s"])

    if name == "fork_bomb":
        if ctx["proc_delta"] > PROC_DELTA_MAX:
            return False, dict(detail, problem="process count +%d after run"
                               % ctx["proc_delta"])
    elif name == "memory_balloon":
        rss = record.get("maxrss_kb")
        if rss is not None and rss > MEM_ABSOLUTE_MB * 1024:
            return False, dict(detail, problem="peak RSS %d KiB exceeds %d MiB"
                               % (rss, MEM_ABSOLUTE_MB))
    elif name == "infinite_loop":
        if wall > WALL_TOLERANCE * wall_limit:
            return False, dict(detail, problem="wall %.1f s > %.1f s"
                               % (wall, WALL_TOLERANCE * wall_limit))
    elif name == "disk_filler":
        path, size = ctx["largest_file"]
        cap = float(ctx["policy"]["fsize_bytes"]) * FSIZE_TOLERANCE
        if size > cap:
            return False, dict(detail, problem="%s is %d bytes > %d"
                               % (os.path.basename(path or "?"), size, int(cap)))
    elif name == "read_shadow":
        if ctx["shadow_leak"]:
            return False, dict(detail, problem="a shadow entry reached stdout")
    elif name == "write_outside":
        if not ctx["canary_intact"]:
            return False, dict(detail, problem="the planted canary changed")
    elif name == "outbound_socket":
        if ctx["net_accepted"]:
            return False, dict(detail,
                               problem="the snippet reached the judge's probe")
    elif name == "background_daemon":
        if ctx["survivors"]:
            return False, dict(detail, problem="%d process(es) survived the run"
                               % len(ctx["survivors"]))
    elif name == "huge_stdout":
        cap = float(ctx["policy"]["output_cap_bytes"]) * CAP_TOLERANCE
        if float(record.get("stdout_bytes") or 0) > cap:
            return False, dict(detail, problem="stdout_bytes %.0f > %.0f"
                               % (record.get("stdout_bytes") or 0, cap))
        if not record.get("truncated"):
            return False, dict(detail, problem="truncated is false")
    elif name == "sleep_forever":
        if wall > WALL_TOLERANCE * wall_limit:
            return False, dict(detail, problem="wall %.1f s > %.1f s"
                               % (wall, WALL_TOLERANCE * wall_limit))
    return True, detail


SHADOW_LINE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*:[^:]*:[^:]*:[^:]*:"
                         r"[^:]*:[^:]*:[^:]*", re.M)


def looks_like_shadow(text):
    """A passwd-style line with a hashed field: what a shadow read leaks."""
    for match in SHADOW_LINE.finditer(text or ""):
        fields = match.group(0).split(":")
        if len(fields) >= 7 and ("$" in fields[1] or fields[1] in ("!", "*")):
            return True
    return False


# ------------------------------------------------------------------- driver

class Probe(object):
    """A TCP listener the judge owns: the oracle for the egress snippet."""

    def __init__(self):
        self.sock = None
        self.port = None
        self.accepted = 0

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.sock.settimeout(0.5)
        self.port = self.sock.getsockname()[1]
        return self

    def poll(self):
        if self.sock is None:
            return
        try:
            conn, _ = self.sock.accept()
        except (socket.timeout, OSError):
            return
        self.accepted += 1
        try:
            conn.close()
        except OSError:
            pass

    def stop(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--skip-run", action="store_true")
    ap.add_argument("--judge-dir")
    args = ap.parse_args()

    judge_dir = os.path.abspath(args.judge_dir or HERE)
    artifact = os.path.abspath(args.artifact)
    if not os.path.isfile(artifact):
        sys.stderr.write("grade.sh: artifact %s does not exist\n"
                         % args.artifact)
        raise SystemExit(2)
    with open(os.path.join(judge_dir, "policy.json")) as fh:
        policy = json.load(fh)
    policy.pop("_comment", None)
    if args.seed:
        # The seed only perturbs the canary nonce; verdicts never depend on it.
        pass

    sha_before = judge_digests(judge_dir)
    verdict = {"demo": "untrusted-code-isolation",
               "artifact": os.path.basename(args.artifact),
               "seed": args.seed, "gates": {}, "timing": {}, "runs": {}}
    rc = 0
    # Baselines are taken before any snippet runs and are always defined, so
    # the health gate can report them even when an earlier gate failed.
    load_before = load1()
    mem_before = mem_available_kb()
    proc_before = proc_count()
    root = tempfile.mkdtemp(prefix="uci-grade-")
    work = os.path.join(root, "work")
    outside = os.path.join(root, "outside")
    os.makedirs(outside)
    os.chmod(root, 0o755)
    os.chmod(outside, 0o755)
    canary = os.path.join(outside, "canary.txt")
    nonce = secrets.token_hex(8)
    with open(canary, "w") as fh:
        fh.write(nonce + "\n")
    os.chmod(canary, 0o644)
    canary_before = sha256_file(canary)

    probe = Probe().start()
    env = dict(os.environ)
    env["UCI_OUTSIDE_DIR"] = outside
    env["UCI_MARKER"] = "judge-probe"
    env["UCI_NET_PROBE"] = "127.0.0.1:%d" % probe.port

    try:
        # ---- gate 1: structure
        try:
            text, problems = load_artifact(artifact)
        except Exception as exc:
            verdict["gates"]["structure"] = {"pass": False,
                                             "problems": [str(exc)[:300]]}
            rc = 1
        else:
            problems += [{"literal": h["literal"], "policy value": h["policy"]}
                         for h in hardcode_hits(text, policy_values(policy))]
            verdict["gates"]["structure"] = {"pass": not problems,
                                             "problems": problems}
            if problems:
                rc = 1

        if rc == 0 and args.skip_run:
            verdict["gates"]["run"] = {
                "pass": False,
                "problems": ["--skip-run is not supported: containment is "
                             "scored from effects the runner must produce"]}
            rc = 1

        # ---- gate 2: run every snippet
        records = {}
        run_dir = None
        if rc == 0:
            run_problems = []
            run_dir = tempfile.mkdtemp(prefix="uci-runs-", dir=root)
            # The snippet runs as an unprivileged uid and must be able to
            # read the run tree, so it is world-readable but not world
            # writable; the canary it must not touch lives outside it.
            os.chmod(run_dir, 0o755)
            # Grade a copy: the artifact under test never runs from its own
            # directory and never gets a path back into judge/.
            runner_copy = os.path.join(run_dir, "runner.py")
            shutil.copy(artifact, runner_copy)
            os.chmod(runner_copy, 0o644)
            for name in HOSTILE + BENIGN:
                snippet = os.path.join(SNIPPETS, "hostile" if name in HOSTILE
                                       else "benign", name + ".py")
                pol = dict(policy)
                pol["workdir"] = os.path.join(run_dir, name)
                pol_path = os.path.join(run_dir, name + ".policy.json")
                with open(pol_path, "w") as fh:
                    json.dump(pol, fh)
                out_path = os.path.join(run_dir, name + ".json")
                t0 = time.monotonic()
                try:
                    proc = subprocess.run(
                        [sys.executable, runner_copy, "run",
                         "--snippet", snippet, "--policy", pol_path,
                         "--out", out_path],
                        cwd=run_dir, env=env, stdin=subprocess.DEVNULL,
                        capture_output=True, timeout=RUN_TIMEOUT_S)
                    rc_runner = proc.returncode
                    runner_err = (proc.stderr or b"").decode("utf-8",
                                                             "replace")[-400:]
                except subprocess.TimeoutExpired:
                    rc_runner, runner_err = None, "judge timeout"
                probe.poll()
                wall = time.monotonic() - t0
                entry = {"runner_exit": rc_runner, "wall_s": round(wall, 2)}
                if rc_runner != 0:
                    run_problems.append("%s: runner exited %s (%s)"
                                        % (name, rc_runner, runner_err.strip()))
                record = {}
                try:
                    with open(out_path) as fh:
                        record = json.load(fh)
                except (OSError, ValueError) as exc:
                    run_problems.append("%s: no readable record (%s)"
                                        % (name, exc))
                missing = [k for k in REQUIRED_KEYS if k not in record]
                if record and missing:
                    run_problems.append("%s: record lacks %s"
                                        % (name, ", ".join(missing)))
                elif record:
                    if record.get("verdict") not in VERDICTS:
                        run_problems.append("%s: verdict %r not in %s"
                                            % (name, record.get("verdict"),
                                               VERDICTS))
                    digest = record.get("stdout_sha256")
                    if not (isinstance(digest, str) and len(digest) == 64
                            and all(c in "0123456789abcdef" for c in digest)):
                        run_problems.append("%s: stdout_sha256 is not a "
                                            "sha256 hex digest" % name)
                    w = record.get("wall_s")
                    if not isinstance(w, (int, float)) or w < 0:
                        run_problems.append("%s: wall_s is not a number >= 0"
                                            % name)
                entry["record"] = record
                entry["workdir"] = pol["workdir"]
                records[name] = entry
            verdict["gates"]["run"] = {"pass": not run_problems,
                                       "problems": run_problems}
            if run_problems:
                rc = 1

        # ---- gates 3-4: containment + benign exactness
        if rc == 0:
            probe.poll()
            largest_path, largest = largest_file(run_dir)
            survivors = survivors_under(run_dir, settle_s=2.0)
            proc_after = proc_count()
            canary_after = sha256_file(canary)
            ctx_base = {
                "policy": policy,
                "largest_file": (largest_path, largest),
                "canary_intact": canary_before == canary_after,
                "net_accepted": probe.accepted > 0,
                "proc_delta": max(0, proc_after - proc_before),
            }
            contain_problems = []
            for name in HOSTILE:
                record = records[name]["record"]
                ctx = dict(ctx_base)
                ctx["survivors"] = (survivors if name == "background_daemon"
                                    else [])
                ctx["shadow_leak"] = looks_like_shadow(
                    record.get("stdout_head", ""))
                ok, detail = score_hostile(name, record, ctx)
                detail["pass"] = ok
                verdict["runs"][name] = detail
                if not ok:
                    contain_problems.append("%s: %s" % (name,
                                                        detail.get("problem")))
            verdict["gates"]["containment"] = {
                "pass": not contain_problems,
                "problems": contain_problems,
                "contained": len(HOSTILE) - len(contain_problems),
                "total": len(HOSTILE),
                "effects": {"canary_intact": ctx_base["canary_intact"],
                            "net_accepted": probe.accepted,
                            "largest_file_bytes": largest,
                            "survivors": len(survivors),
                            "proc_delta": ctx_base["proc_delta"]}}
            if contain_problems:
                rc = 1

            # gate 4: benign snippets must match the judge's own run of them
            benign_problems = []
            ref_dir = os.path.join(root, "ref")
            for name in BENIGN:
                snippet = os.path.join(SNIPPETS, "benign", name + ".py")
                reference = run_benign_reference(
                    snippet, os.path.join(ref_dir, name),
                    {"PATH": "/usr/bin:/bin", "UCI_MARKER": "judge-probe",
                     "HOME": os.path.join(ref_dir, name)})
                record = records[name]["record"]
                detail = {"expected_sha256": reference["sha256"],
                          "got_sha256": record.get("stdout_sha256"),
                          "expected_exit": reference["exit_code"],
                          "got_exit": record.get("exit_code")}
                ok = True
                if record.get("verdict") != "ok":
                    ok = False
                    detail["problem"] = ("verdict %r, expected ok"
                                         % record.get("verdict"))
                elif record.get("exit_code") != reference["exit_code"]:
                    ok = False
                    detail["problem"] = ("exit %s, expected %d"
                                         % (record.get("exit_code"),
                                            reference["exit_code"]))
                elif record.get("stdout_sha256") != reference["sha256"]:
                    ok = False
                    detail["problem"] = "stdout differs from the reference run"
                elif record.get("truncated"):
                    ok = False
                    detail["problem"] = "stdout was truncated"
                elif (name == "cpu_bounded"
                      and float(record.get("wall_s") or 0) >= CPU_BOUNDED_MAX_S):
                    ok = False
                    detail["problem"] = ("wall %.2f s >= %.1f s"
                                         % (record.get("wall_s"),
                                            CPU_BOUNDED_MAX_S))
                detail["pass"] = ok
                verdict["runs"][name] = detail
                if not ok:
                    benign_problems.append("%s: %s" % (name,
                                                       detail.get("problem")))
            verdict["gates"]["benign"] = {
                "pass": not benign_problems, "problems": benign_problems,
                "matched": len(BENIGN) - len(benign_problems),
                "total": len(BENIGN)}
            if benign_problems:
                rc = 1

        # ---- gate 5: sandbox health
        sha_after = judge_digests(judge_dir)
        mem_after = mem_available_kb()
        load_after = load1()
        proc_final = proc_count()
        survivors_final = survivors_under(run_dir, settle_s=2.0) \
            if run_dir else []
        canary_final = sha256_file(canary)
        health = {}
        problems = []
        load_rise = load_after - load_before
        health["load_before"] = round(load_before, 2)
        health["load_after"] = round(load_after, 2)
        health["load_increase"] = round(load_rise, 2)
        if load_rise >= LOAD_INCREASE_MAX:
            problems.append("load average rose %.2f (>= %.1f)"
                            % (load_rise, LOAD_INCREASE_MAX))
        retained = (float(mem_after) / mem_before) if mem_before > 0 else 0.0
        health["mem_before_kb"] = mem_before
        health["mem_after_kb"] = mem_after
        health["mem_retained"] = round(retained, 3)
        if retained < MEM_RETAINED_MIN:
            problems.append("free memory fell to %.0f%% of the pre-run value"
                            % (retained * 100))
        health["proc_before"] = proc_before
        health["proc_after"] = proc_final
        health["proc_delta"] = proc_final - proc_before
        if abs(proc_final - proc_before) > PROC_DELTA_MAX:
            problems.append("process count moved by %d (> %d)"
                            % (proc_final - proc_before, PROC_DELTA_MAX))
        health["survivors"] = survivors_final
        if survivors_final:
            problems.append("%d process(es) still reference the run tree"
                            % len(survivors_final))
        health["canary_intact"] = canary_final == canary_before
        if not health["canary_intact"]:
            problems.append("a canary outside the workdir changed")
        health["judge_intact"] = sha_before == sha_after
        if not health["judge_intact"]:
            problems.append("judge/ checksums changed during the grade")
        health["pass"] = not problems
        health["problems"] = problems
        verdict["gates"]["health"] = health
        if problems:
            rc = 1
        verdict["judge_intact"] = sha_before == sha_after
    finally:
        probe.stop()
        shutil.rmtree(root, ignore_errors=True)

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    sys.exit(rc)


if __name__ == "__main__":
    main()
