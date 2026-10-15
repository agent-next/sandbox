#!/usr/bin/env python3
"""Run one untrusted snippet under enforced limits and report the verdict.

    python3 runner.py run --snippet S --policy P --out O

Every limit is an input: the CPU, address-space, file-size, process-count,
wall-clock and output caps come from the policy file, never from constants
in this file. The runner builds a private workdir, executes the snippet
there under those limits, and writes one JSON record saying what happened
and why.

The limits are applied by a small supervisor that runs with the privileges
needed to create the namespaces and to stop the snippet afterwards; the
snippet itself is started from that supervisor with the limits already set,
so nothing the snippet does can widen them.

Isolation ladder (the strongest that works on this host is used, and the
mode is reported in the record):

  sudo-userns      `sudo` is available. The snippet runs in new mount,
                   network and PID namespaces, with the real uid dropped to
                   an unprivileged account. It cannot read root-only or
                   owner-only files, write outside its workdir, reach the
                   network, or leave a process behind.
  rootless-userns  no `sudo`, but unprivileged user namespaces are allowed.
                   New mount, network and PID namespaces; everything above
                   the workdir is remounted read-only. Writes are confined;
                   reads are not, because the uid cannot be changed, and the
                   record says so.
  none             neither is available. Limits still apply, but the record
                   carries a `:host` suffix on the reason instead of
                   implying confinement that did not happen.

Usage: python3 runner.py run --snippet PATH --policy PATH --out PATH
"""

import argparse
import hashlib
import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
import time

UID_FALLBACK = 65534         # nobody / nogroup
STDOUT_HEAD = 2048           # bytes of captured stdout echoed into the record

# ------------------------------------------------------------- supervisor
#
# Runs as root (sudo-userns) or as the invoking user (rootless-userns). It
# creates the namespaces, starts the snippet with the limits set, enforces
# the wall clock and the output cap, stops the job, and writes one JSON
# record. It exits 0 whatever the snippet did: the record carries the
# outcome, so a runner failure stays distinguishable from a snippet failure.
#
# Enforcement lives here rather than in the caller because the caller is not
# privileged: a plain process cannot signal a job that has dropped to another
# uid, and a job can call setsid to leave the caller's process group.

SUPERVISOR = r'''#!/usr/bin/env python3
"""Limits, namespaces, uid drop, wall clock, output cap. Writes one record."""
import ctypes
import json
import os
import resource
import select
import signal
import sys
import time

CLONE_NEWNS = 0x00020000
CLONE_NEWNET = 0x40000000
CLONE_NEWPID = 0x20000000
MS_REC = 16384
MS_PRIVATE = 1 << 18
MS_BIND = 4096
MS_REMOUNT = 32
MS_RDONLY = 1
POLL_S = 0.02

libc = ctypes.CDLL("libc.so.6", use_errno=True)


def _oserror():
    err = ctypes.get_errno()
    return OSError(err, os.strerror(err))


def main():
    (cpu, as_bytes, fsize, nproc, wall, cap, workdir, snippet, env_path,
     out_path, uid, gid, drop_uid, read_only) = sys.argv[1:15]
    cpu, as_bytes = int(cpu), int(as_bytes)
    fsize, nproc, cap = int(fsize), int(nproc), int(cap)
    wall = float(wall)
    uid, gid = int(uid), int(gid)
    ns = {"mount": False, "net": False, "pid": False, "uid_dropped": False}

    try:
        if libc.unshare(CLONE_NEWNS) != 0:
            raise _oserror()
        libc.mount(None, b"/", None, MS_REC | MS_PRIVATE, None)
        ns["mount"] = True
    except OSError:
        ns["mount"] = False
    for flag, key in ((CLONE_NEWNET, "net"), (CLONE_NEWPID, "pid")):
        try:
            if libc.unshare(flag) != 0:
                raise _oserror()
            ns[key] = True
        except OSError:
            ns[key] = False

    # Confine writes: make everything above the workdir read-only, then bind
    # the workdir back read-write on top of it.
    if int(read_only) and ns["mount"]:
        try:
            parent = os.path.dirname(os.path.abspath(workdir)) or "/"
            libc.mount(parent.encode(), parent.encode(), None,
                       MS_BIND | MS_REC, None)
            libc.mount(None, parent.encode(), None,
                       MS_BIND | MS_REMOUNT | MS_RDONLY | MS_REC, None)
            libc.mount(workdir.encode(), workdir.encode(), None,
                       MS_BIND | MS_REC, None)
        except OSError:
            pass

    with open(env_path) as fh:
        child_env = json.load(fh)

    read_fd, write_fd = os.pipe()
    # 0644: the caller reads this file back, and under sudo the supervisor
    # runs as root, so a 0600 file would be unreadable to the caller.
    err_fd = os.open(os.path.join(os.path.dirname(out_path), "stderr.bin"),
                     os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    started = time.monotonic()

    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        os.dup2(write_fd, 1)
        os.dup2(err_fd, 2)
        os.close(write_fd)
        os.close(err_fd)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        resource.setrlimit(resource.RLIMIT_AS, (as_bytes, as_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
        resource.setrlimit(resource.RLIMIT_NPROC, (nproc, nproc))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if int(drop_uid):
            os.setgroups([])
            os.setgid(gid)
            os.setuid(uid)
            ns["uid_dropped"] = True
        os.chdir(workdir)
        os.execve(sys.executable, [sys.executable, snippet], child_env)

    os.close(write_fd)
    os.close(err_fd)

    # Stop by the snippet's own pid: it is PID 1 of its PID namespace, so
    # killing it takes down everything the snippet started, including a
    # daemon that called setsid and left the process group.
    def stop():
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    chunks, seen = [], 0
    truncated = False
    reason = None
    status = None
    while True:
        done, st = os.waitpid(pid, os.WNOHANG)
        if done == pid:
            status = st
            break
        if time.monotonic() - started > wall:
            reason = "timeout"
            stop()
            _, status = os.waitpid(pid, 0)
            break
        try:
            ready, _, _ = select.select([read_fd], [], [], POLL_S)
        except (OSError, ValueError):
            ready = []
        if not ready:
            continue
        try:
            piece = os.read(read_fd, 65536)
        except OSError:
            piece = b""
        if not piece:
            continue
        seen += len(piece)
        if seen > cap:
            truncated = True
            keep = cap - (seen - len(piece))
            if keep > 0:
                chunks.append(piece[:keep])
            reason = "output_cap"
            stop()
            _, status = os.waitpid(pid, 0)
            break
        chunks.append(piece)

    # Drain anything still in the pipe.
    while True:
        try:
            piece = os.read(read_fd, 65536)
        except OSError:
            piece = b""
        if not piece:
            break
        seen += len(piece)
        if seen > cap:
            truncated = True
            piece = piece[:cap - (seen - len(piece))] if seen - len(piece) < cap else b""
        if piece:
            chunks.append(piece)
        if truncated:
            break
    os.close(read_fd)

    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    stdout = b"".join(chunks)
    with open(out_path, "w") as fh:
        json.dump({"status": status, "reason": reason,
                   "truncated": truncated, "wall_s": time.monotonic() - started,
                   "stdout_len": len(stdout),
                   "stdout_sha256": __import__("hashlib").sha256(stdout).hexdigest(),
                   "stdout_head": stdout[:2048].decode("utf-8", "replace"),
                   "utime": usage.ru_utime, "stime": usage.ru_stime,
                   "maxrss_kb": usage.ru_maxrss, "ns": ns,
                   "uid": uid if int(drop_uid) else os.getuid()}, fh)
    sys.exit(0)


if __name__ == "__main__":
    main()
'''


# ------------------------------------------------------------------ helpers

def die(msg, code=2):
    sys.stderr.write("runner: %s\n" % msg)
    raise SystemExit(code)


def read_policy(path):
    try:
        with open(path) as fh:
            pol = json.load(fh)
    except (OSError, ValueError) as exc:
        die("cannot read policy %s: %s" % (path, exc))
    need = ("cpu_s", "as_bytes", "fsize_bytes", "nproc", "wall_s",
            "output_cap_bytes", "workdir")
    missing = [k for k in need if k not in pol]
    if missing:
        die("policy is missing %s" % ", ".join(missing))
    for key in ("cpu_s", "as_bytes", "fsize_bytes", "nproc", "wall_s",
                "output_cap_bytes"):
        val = pol[key]
        if isinstance(val, bool) or not isinstance(val, (int, float)) or val <= 0:
            die("policy %s must be a positive number, got %r" % (key, val))
    return pol


def unprivileged_uid():
    for name in ("nobody", "nogroup"):
        try:
            entry = pwd.getpwnam(name)
        except KeyError:
            continue
        if entry.pw_uid != 0:
            return entry.pw_uid, entry.pw_gid
    return UID_FALLBACK, UID_FALLBACK


def can_run(argv):
    try:
        return subprocess.run(argv, capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def pick_mode(policy):
    want_uid = bool(policy.get("uid_drop", True))
    want_net = bool(policy.get("net_isolate", True))
    if (want_uid and want_net and shutil.which("sudo")
            and can_run(["sudo", "-n", "true"])):
        return "sudo-userns"
    if shutil.which("unshare") and can_run(["unshare", "-U", "-r", "true"]):
        return "rootless-userns"
    return "none"


def snippet_env(policy, workdir):
    """A small allowlist: the snippet never inherits the host environment."""
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": workdir,
           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TMPDIR": workdir,
           "PYTHONDONTWRITEBYTECODE": "1"}
    for key in sorted(os.environ):
        if key.startswith("UCI_"):
            env[key] = os.environ[key]
    for key, val in (policy.get("env") or {}).items():
        env[str(key)] = str(val)
    return env


# ------------------------------------------------------------------ the run

def execute(policy, snippet, workdir, supervisor, mode, uid, gid):
    sup = os.path.join(supervisor, "supervisor.py")
    with open(sup, "w") as fh:
        fh.write(SUPERVISOR)
    os.chmod(sup, 0o755)
    env_path = os.path.join(supervisor, "env.json")
    with open(env_path, "w") as fh:
        json.dump(snippet_env(policy, workdir), fh)
    os.chmod(env_path, 0o644)
    out_path = os.path.join(supervisor, "record.json")

    drop_uid = mode == "sudo-userns"
    read_only = mode == "rootless-userns"
    argv = [sys.executable, sup,
            str(int(policy["cpu_s"])), str(int(policy["as_bytes"])),
            str(int(policy["fsize_bytes"])), str(int(policy["nproc"])),
            str(float(policy["wall_s"])), str(int(policy["output_cap_bytes"])),
            workdir, snippet, env_path, out_path,
            str(uid), str(gid), "1" if drop_uid else "0",
            "1" if read_only else "0"]
    if mode == "sudo-userns":
        # sudo resets the environment, so the child env travels as a file.
        argv = ["sudo", "-n", "--"] + argv

    started = time.monotonic()
    try:
        proc = subprocess.run(argv, cwd=supervisor, stdin=subprocess.DEVNULL,
                              capture_output=True,
                              timeout=float(policy["wall_s"]) + 30)
    except subprocess.TimeoutExpired:
        return {"reason": "unavailable:supervisor-hung",
                "wall_s": time.monotonic() - started, "ns": {}}
    except OSError as exc:
        return {"reason": "unavailable:exec", "stderr": str(exc),
                "wall_s": time.monotonic() - started, "ns": {}}

    record = {}
    try:
        with open(out_path) as fh:
            record = json.load(fh)
    except (OSError, ValueError):
        record = {}
    if not record:
        tail = (proc.stderr or b"").decode("utf-8", "replace")[-400:]
        return {"reason": "unavailable:supervisor",
                "stderr": tail or ("supervisor exit %d" % proc.returncode),
                "wall_s": time.monotonic() - started, "ns": {}}
    try:
        with open(os.path.join(supervisor, "stderr.bin"), "rb") as fh:
            record["stderr"] = fh.read(65536).decode("utf-8", "replace")
    except OSError:
        record["stderr"] = ""
    return record


def classify(record, policy):
    """Turn the supervisor's record into (verdict, reason)."""
    reason = record.get("reason")
    if reason == "output_cap":
        return "killed", "output_cap"
    if reason == "timeout":
        return "timeout", "timeout"
    if reason and str(reason).startswith("unavailable:"):
        return "error", str(reason)
    status = record.get("status")
    if status is None:
        return "error", "exit"
    cpu_limit = float(policy["cpu_s"])
    cpu = (record.get("utime", 0.0) or 0.0) + (record.get("stime", 0.0) or 0.0)
    err = record.get("stderr") or ""

    if os.WIFSIGNALED(status):
        sig = os.WTERMSIG(status)
        if sig == signal.SIGXFSZ:
            return "killed", "fsize"
        if sig == signal.SIGKILL:
            # SIGKILL from the CPU rlimit arrives at the hard limit; SIGKILL
            # before that is the wall clock, which the supervisor records as
            # an explicit reason.
            return "killed", "cpu" if cpu >= cpu_limit - 0.05 else "killed"
        if sig in (signal.SIGSEGV, signal.SIGBUS, signal.SIGABRT):
            return "error", "exit"
        return "killed", "signal"
    if os.WEXITSTATUS(status) == 0:
        return "ok", "none"
    # A non-zero exit is how most limits surface: the interpreter turns the
    # failed syscall into an exception and prints a traceback.
    if "MemoryError" in err:
        return "denied", "as"
    if "BlockingIOError" in err or "Resource temporarily unavailable" in err:
        return "denied", "nproc"
    if "Errno 27" in err or "File too large" in err:
        return "denied", "fsize"
    if "PermissionError" in err or "Errno 13" in err:
        # Read and write refusals look alike from here; which one it was is
        # decided by the judge from the effect (the canary's bytes, the
        # absence of a secret in stdout), not from this token.
        return "denied", "perm"
    return "error", "exit"


def run_one(args):
    policy = read_policy(args.policy)
    snippet = os.path.abspath(args.snippet)
    if not os.path.isfile(snippet):
        die("snippet %s does not exist" % args.snippet)
    name = os.path.splitext(os.path.basename(snippet))[0]

    workdir = os.path.abspath(policy["workdir"])
    if os.path.isdir(workdir):
        shutil.rmtree(workdir, ignore_errors=True)
    os.makedirs(workdir)
    os.chmod(workdir, 0o777)
    # The supervisor dir holds the supervisor and the env file the snippet
    # must read; world-readable, owner-writable, so the snippet can read them
    # and cannot rewrite them.
    supervisor = tempfile.mkdtemp(prefix="uci-supervisor-")
    os.chmod(supervisor, 0o755)
    mode = pick_mode(policy)
    uid, gid = unprivileged_uid()
    if mode != "sudo-userns":
        uid = gid = os.getuid()

    try:
        record = execute(policy, snippet, workdir, supervisor, mode, uid, gid)
    finally:
        shutil.rmtree(supervisor, ignore_errors=True)

    verdict, reason = classify(record, policy)
    if mode == "none" and reason not in ("none",):
        reason = "%s:host" % reason
    status = record.get("status")

    out = {"snippet": name, "verdict": verdict, "reason": reason,
           "exit_code": os.WEXITSTATUS(status) if status is not None
           and not os.WIFSIGNALED(status) else None,
           "signal": os.WTERMSIG(status) if status is not None
           and os.WIFSIGNALED(status) else None,
           "wall_s": round(record.get("wall_s", 0.0), 4),
           "stdout_bytes": record.get("stdout_len", 0),
           "stdout_sha256": record.get("stdout_sha256",
                                       hashlib.sha256(b"").hexdigest()),
           "stdout_head": record.get("stdout_head", "")[:STDOUT_HEAD],
           "truncated": bool(record.get("truncated")),
           "isolation": mode,
           "child_uid": record.get("uid"),
           "cpu_s": round((record.get("utime", 0.0) or 0.0)
                          + (record.get("stime", 0.0) or 0.0), 4),
           "maxrss_kb": record.get("maxrss_kb"),
           "namespaces": record.get("ns")}
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
        fh.write("\n")
    sys.stdout.write("run %s verdict=%s reason=%s\n" % (name, verdict, reason))
    return 0


def main():
    ap = argparse.ArgumentParser(description="run one untrusted snippet")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run one snippet under the policy")
    r.add_argument("--snippet", required=True)
    r.add_argument("--policy", required=True)
    r.add_argument("--out", required=True)
    r.set_defaults(func=run_one)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
