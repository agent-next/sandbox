#!/usr/bin/env python3
"""One-command run for the gpu-batch-image-gen demo.

Default (no flags) is the judge lane the cookbook standard describes:

    python3 cookbook/gpu-batch-image-gen/run.py [--ref main]

It creates a disposable agent-next sandbox, clones this repository at
``--ref`` inside it, installs the pinned judge toolchain, proves the judge
can fail (self-test) and grades the known-good batch. The sandbox is always
killed afterwards, and its absence is confirmed against the inventory.

``--render`` runs the GPU lane instead: it downloads and sha256-verifies the
pinned stabilityai/sd-turbo weights on this machine, creates a short-lived
GPU lease over the REST API (https://api.sbx.agent-next.com, header
``X-API-Key``), uploads the weights in <=400 MiB chunks, renders the pinned
16-prompt batch on the lease and downloads the artifact. The lease is always
deleted and its deletion confirmed; every lease id is recorded in the report
JSON. ``--render`` never grades; pair it with ``--grade DIR`` to grade what
it produced.

``--grade DIR`` runs the judge lane against a batch directory instead of the
known-good example.

Needs the ``sbx`` CLI
(``pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"``)
and ``SBX_API_KEY`` (or ``E2B_API_KEY``) in the environment.

Standard library only. Wall time is printed per step.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_URL = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/gpu-batch-image-gen"
API = "https://api.sbx.agent-next.com"

# GPU lease uploads are capped at 512 MiB per request on both the front and
# the node; stay clear of the cap and reassemble the parts on the lease.
UPLOAD_CHUNK = 400 * 1024 * 1024
WEIGHTS_URL = "https://huggingface.co/stabilityai/sd-turbo/resolve/main"

# Generous per-step budgets. sbx exec's own default is 60 s, which no step
# below fits in: setup.sh downloads a CPU torch wheel and the 578 MiB CLIP
# checkpoint, and the self-test grades the good batch plus 8 mutants.
STEP_TIMEOUTS = {
    "clone": 300,
    "setup": 2400,
    "selftest": 3600,
    "grade": 1200,
}


def die(msg, code=1):
    print(f"run.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def scrub(text):
    for name in ("SBX_API_KEY", "E2B_API_KEY", "GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[redacted]")
    return text


def need_key():
    key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
    if not key:
        die("no API key: export SBX_API_KEY (or E2B_API_KEY)")
    return key


def need_sbx():
    if not shutil.which("sbx"):
        die("sbx CLI not found: pip install "
            "'git+https://github.com/agent-next/sandbox#subdirectory=cli'")
    need_key()


# --------------------------------------------------------------- sbx shell

def sbx(step, *args, timeout=120, capture=False):
    """Run one sbx command; return (exit_code, output, seconds)."""
    cmd = ["sbx", *[str(a) for a in args]]
    t0 = time.monotonic()
    proc = subprocess.run(cmd, capture_output=capture, text=True,
                          timeout=timeout + 60)
    dt = time.monotonic() - t0
    out = scrub((proc.stdout or "") + (proc.stderr or "")) if capture else ""
    print(f"[run] {step:<26} {dt:7.1f}s  exit={proc.returncode}", flush=True)
    return proc.returncode, out, dt


def sbx_sh(step, sid, line, timeout, capture=False):
    """Run a shell line inside a sandbox."""
    return sbx(step, "exec", sid, "--timeout", timeout, "--",
               "bash", "-lc", line, timeout=timeout, capture=capture)


def kill_sandbox(sid, keep):
    """Kill the sandbox and confirm it left the inventory. Returns error text."""
    if keep:
        print(f"[run] --keep: sandbox {sid} left running", flush=True)
        return None
    sbx("sbx kill", "kill", sid, timeout=180, capture=True)
    rc, listing, _ = sbx("sbx list", "list", timeout=180, capture=True)
    if rc == 0 and sid not in listing:
        print(f"[run] cleanup confirmed: {sid} is gone", flush=True)
        return None
    return (f"could not confirm cleanup of sandbox {sid}: `sbx list` still "
            f"shows it (or the listing failed); run `sbx kill {sid}`")


# ------------------------------------------------------------- judge lane

def judge_lane(args):
    """Create a CPU sandbox, clone the repo, run setup + selftest + grade."""
    need_sbx()
    rc, out, _ = sbx("sbx create", "create", "--timeout-min", "30",
                     timeout=180, capture=True)
    if rc != 0 or not out.strip():
        die(f"sandbox create failed: {out.strip()}")
    sid = out.strip().splitlines()[-1].strip()
    if not sid:
        die("sandbox create printed no id")
    print(f"[run] sandbox id: {sid}", flush=True)

    failed = None
    verdict = None
    target = args.grade or "examples/good/batch"
    try:
        rc, _, _ = sbx_sh("git clone", sid,
                          f"git clone --depth 1 -b {args.ref} {REPO_URL} repo",
                          STEP_TIMEOUTS["clone"])
        if rc != 0:
            failed = "git clone"
        else:
            rc, _, _ = sbx_sh("judge/setup.sh", sid,
                              f"cd repo/{DEMO_DIR} && bash judge/setup.sh",
                              STEP_TIMEOUTS["setup"])
            if rc != 0:
                failed = "judge/setup.sh"

        if not failed:
            rc, out, _ = sbx_sh("judge/selftest.sh", sid,
                                f"cd repo/{DEMO_DIR} && bash judge/selftest.sh",
                                STEP_TIMEOUTS["selftest"], capture=True)
            print("\n".join(out.strip().splitlines()[-12:]), flush=True)
            if rc != 0:
                failed = "judge/selftest.sh"

        if not failed:
            rc, out, _ = sbx_sh(
                f"judge/grade.sh {os.path.basename(target)}", sid,
                f"cd repo/{DEMO_DIR} && bash judge/grade.sh {target} "
                f"--seed 0 --json /tmp/verdict.json >/tmp/grade.log 2>&1; "
                f"rc=$?; cat /tmp/verdict.json 2>/dev/null || cat /tmp/grade.log",
                STEP_TIMEOUTS["grade"], capture=True)
            verdict = parse_verdict(out)
            if rc != 0 or verdict is None or not all_pass(verdict):
                failed = f"judge/grade.sh {target}"
                if verdict is None:
                    print(out[-2000:], file=sys.stderr, flush=True)

        if verdict is not None:
            print_verdict(verdict)
    finally:
        cleanup_error = kill_sandbox(sid, args.keep)
        if cleanup_error:
            print(f"[run] ERROR: {cleanup_error}", file=sys.stderr, flush=True)
            failed = failed or "cleanup"

    if failed:
        die(f"failed at step '{failed}' (sandbox {sid})")
    if verdict is None or not all_pass(verdict):
        die("no all-gates-pass verdict was produced")
    print(f"\n[run] ACCEPTANCE_PASS: every gate passed "
          f"(sandbox {sid} killed)", flush=True)


def all_pass(verdict):
    gates = verdict.get("gates") or {}
    return bool(gates) and all(g.get("pass") for g in gates.values()
                               if isinstance(g, dict)) \
        and verdict.get("judge_intact", False)


def parse_verdict(text):
    """Pull the verdict JSON out of a grade.sh transcript."""
    start = text.find("{")
    while start != -1:
        try:
            candidate = json.loads(text[start:])
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        if isinstance(candidate, dict) and "gates" in candidate:
            return candidate
        start = text.find("{", start + 1)
    return None


def print_verdict(verdict):
    print("\n[run] ======== verdict ========", flush=True)
    print(json.dumps(verdict, indent=2, sort_keys=True), flush=True)
    print(f"[run] {'ALL GATES PASS' if all_pass(verdict) else 'FAILED'}", flush=True)


# ------------------------------------------------------------- HTTP (GPU)

def request(key, method, path, body=None, raw=None, timeout=900):
    """One gateway call. Returns (status, parsed-json-or-bytes-or-None)."""
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    ctype = "application/octet-stream" if raw is not None else "application/json"
    req = Request(API + path, data=data, method=method,
                  headers={"X-API-Key": key, "Content-Type": ctype})
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = resp.read()
            if resp.headers.get("Content-Type", "").startswith("application/json"):
                try:
                    return resp.status, json.loads(payload)
                except json.JSONDecodeError:
                    return resp.status, None
            return resp.status, payload
    except HTTPError as exc:
        # Do not echo a body that could carry credentials; the gateway's
        # error bodies are {"code","message"} and are safe to shorten.
        detail = ""
        try:
            detail = exc.read(400).decode("utf-8", "replace")
        except Exception:
            pass
        return exc.code, {"message": detail} if detail else None
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"message": f"{type(exc).__name__}: {exc}"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------- GPU lane

def weights_manifest(demo):
    with open(os.path.join(demo, "judge", "weights-manifest.json")) as fh:
        return json.load(fh)


def fetch_weights(demo, cache):
    """Download + sha256-verify the pinned sd-turbo files. Returns the dir."""
    manifest = weights_manifest(demo)["files"]
    os.makedirs(cache, exist_ok=True)
    for rel, want in sorted(manifest.items()):
        dst = os.path.join(cache, rel)
        if os.path.isfile(dst) and sha256_file(dst) == want:
            print(f"[run] weights cached: {rel}", flush=True)
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        url = f"{WEIGHTS_URL}/{rel}"
        tmp = dst + ".part"
        t0 = time.monotonic()
        req = Request(url, headers={"User-Agent": "run.py/1.0"})
        with urlopen(req, timeout=1800) as resp, open(tmp, "wb") as fh:
            shutil.copyfileobj(resp, fh, 1 << 20)
        got = sha256_file(tmp)
        if got != want:
            os.unlink(tmp)
            die(f"weights sha256 mismatch for {rel}: got {got}, want {want}")
        os.replace(tmp, dst)
        print(f"[run] weights {rel} "
              f"({os.path.getsize(dst)/2**20:.1f} MiB, {time.monotonic()-t0:.0f}s)",
              flush=True)
    return cache


def upload_weights(key, sid, cache, manifest):
    """Upload every weights file, chunking anything over UPLOAD_CHUNK."""
    for rel, want in sorted(manifest.items()):
        src = os.path.join(cache, rel)
        size = os.path.getsize(src)
        t0 = time.monotonic()
        if size <= UPLOAD_CHUNK:
            with open(src, "rb") as fh:
                data = fh.read()
            st, body = request(key, "PUT", f"/sandboxes/{sid}/files/weights/{rel}",
                               raw=data, timeout=1800)
            if st != 200 or not isinstance(body, dict) or body.get("sha256") != want:
                die(f"weights upload failed for {rel}: HTTP {st} {body}")
        else:
            parts = []
            with open(src, "rb") as fh:
                n = 0
                while True:
                    chunk = fh.read(UPLOAD_CHUNK)
                    if not chunk:
                        break
                    name = f"weights/{rel}.part{n:03d}"
                    st, body = request(key, "PUT",
                                       f"/sandboxes/{sid}/files/{name}",
                                       raw=chunk, timeout=1800)
                    if st != 200 or not isinstance(body, dict):
                        die(f"weights chunk upload failed for {name}: "
                            f"HTTP {st} {body}")
                    parts.append((name, hashlib.sha256(chunk).hexdigest()))
                    n += 1
            # Reassemble on the lease and verify against the pinned sha256.
            # The parts are removed only after the reassembled file matches.
            job = (
                "import hashlib, json, os, sys\n"
                "wd = sys.argv[1]\n"
                f"parts = {json.dumps([p for p, _ in parts])}\n"
                f"want = {json.dumps(want)}\n"
                "h = hashlib.sha256()\n"
                f"tmp = os.path.join(wd, 'weights', {json.dumps(rel + '.joined')})\n"
                "with open(tmp, 'wb') as out:\n"
                "    for p in parts:\n"
                "        with open(os.path.join(wd, p), 'rb') as fh:\n"
                "            while True:\n"
                "                b = fh.read(1 << 22)\n"
                "                if not b:\n"
                "                    break\n"
                "                h.update(b)\n"
                "                out.write(b)\n"
                "got = h.hexdigest()\n"
                "if got != want:\n"
                "    os.unlink(tmp)\n"
                f"    raise RuntimeError('reassembled {rel} sha256 ' + got + ' != ' + want)\n"
                f"os.replace(tmp, os.path.join(wd, 'weights', {json.dumps(rel)}))\n"
                "for p in parts:\n"
                "    os.unlink(os.path.join(wd, p))\n"
                "report['joined'] = got\n"
            )
            st, body = request(key, "POST", f"/sandboxes/{sid}/exec",
                               {"code": job, "timeout_s": 900})
            if st != 200:
                die(f"weights reassembly failed for {rel}: HTTP {st} {body}")
        print(f"[run] uploaded weights/{rel} ({size/2**20:.1f} MiB, "
              f"{time.monotonic()-t0:.0f}s)", flush=True)


def render_lane(args):
    """Render the pinned batch on a GPU lease; never leaves a lease behind."""
    key = need_key()
    demo = os.path.dirname(os.path.abspath(__file__))
    manifest = weights_manifest(demo)["files"]
    out_dir = os.path.abspath(args.out)
    report = {"leases": [], "steps": {}}

    # Download and verify before any lease exists, so a local failure cannot
    # leak a GPU lease.
    t0 = time.monotonic()
    cache = fetch_weights(demo, os.path.expanduser(args.weights_cache))
    report["steps"]["fetch_weights_s"] = round(time.monotonic() - t0, 1)

    print("[run] creating GPU lease (6 GiB VRAM slice)...", flush=True)
    t0 = time.monotonic()
    st, created = request(key, "POST", "/sandboxes",
                          {"accel": {"vram_gb": 6, "reserve": "exec"}})
    if st != 201 or not isinstance(created, dict) or "sandboxID" not in created:
        die(f"GPU lease create: HTTP {st} {created}; check GPU access, "
            "credit and capacity")
    sid = created["sandboxID"]
    # Only a gateway-generated GPU id may be interpolated into request paths.
    if not isinstance(sid, str) or not sid.startswith("gl-") or not all(
            c.isascii() and (c.isalnum() or c == "-") for c in sid):
        die(f"GPU lease create returned an unexpected id {sid!r}; it was not "
            "destroyed automatically: delete it by id")
    report["leases"].append({"id": sid, "class": (created.get("accel") or {}).get("class"),
                             "vram_gb": (created.get("accel") or {}).get("vram_gb")})
    print(f"[run] GPU lease {sid} created ({time.monotonic()-t0:.0f}s)", flush=True)

    try:
        t0 = time.monotonic()
        upload_weights(key, sid, cache, manifest)
        report["steps"]["upload_s"] = round(time.monotonic() - t0, 1)

        # Ship the generator and run it. The exec namespace's cwd is '/', and
        # the lease workdir is argv[1]; write the artifact into its out/.
        with open(os.path.join(demo, "gen.py"), "rb") as fh:
            st, body = request(key, "PUT", f"/sandboxes/{sid}/files/gen.py",
                               raw=fh.read(), timeout=300)
        if st != 200:
            die(f"gen.py upload: HTTP {st} {body}")

        job = (
            "import json, os, subprocess, sys, time\n"
            "wd = sys.argv[1]\n"
            "os.chdir(wd)\n"
            "t0 = time.monotonic()\n"
            "r = subprocess.run([sys.executable, 'gen.py', '--weights', 'weights',\n"
            "                    '--out', 'out'], capture_output=True, text=True)\n"
            "report['render_rc'] = r.returncode\n"
            "report['render_wall_s'] = round(time.monotonic() - t0, 1)\n"
            "report['stdout'] = r.stdout[-4000:]\n"
            "report['stderr'] = r.stderr[-4000:]\n"
            "if r.returncode != 0:\n"
            "    raise RuntimeError('gen.py exited %d' % r.returncode)\n"
        )
        t0 = time.monotonic()
        st, body = request(key, "POST", f"/sandboxes/{sid}/exec",
                           {"code": job, "timeout_s": 1800})
        if st != 200:
            die(f"GPU render exec: HTTP {st} {body}")
        rep = (body.get("result") or {}).get("report") or {}
        report["steps"]["render_s"] = round(time.monotonic() - t0, 1)
        print(rep.get("stdout", "").strip(), flush=True)
        if rep.get("stderr"):
            print(scrub(rep["stderr"][-1500:]), file=sys.stderr, flush=True)

        t0 = time.monotonic()
        download_artifact(key, sid, out_dir)
        report["steps"]["download_s"] = round(time.monotonic() - t0, 1)
        report["artifact"] = out_dir
    finally:
        print(f"[run] destroying GPU lease {sid}...", flush=True)
        st, _ = request(key, "DELETE", f"/sandboxes/{sid}")
        st2, remaining = request(key, "GET", f"/sandboxes/{sid}")
        dead = st2 == 404 or (st2 == 200 and isinstance(remaining, dict)
                              and remaining.get("phase") == "dead")
        entry = report["leases"][0]
        entry["delete_http"] = st
        entry["confirm_http"] = st2
        entry["confirmed_gone"] = bool(dead)
        if dead:
            print(f"[run] lease {sid} deleted; GET confirms gone "
                  f"(HTTP {st2})", flush=True)
        else:
            die(f"cleanup unconfirmed for GPU lease {sid}: GET returned "
                f"HTTP {st2}; it may still be live: DELETE /sandboxes/{sid}")

    if args.report:
        with open(args.report, "w") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
        print(f"[run] wrote {args.report}", flush=True)
    print(f"[run] RENDER_OK: artifact at {out_dir}", flush=True)


def download_artifact(key, sid, out_dir):
    """GET every file under the lease's OUTPUT_DIR (out/) into out_dir."""
    st, listing = request(key, "GET", f"/sandboxes/{sid}/files")
    if st != 200 or not isinstance(listing, dict) or "files" not in listing:
        die(f"artifact listing: HTTP {st} {listing}")
    names = [f["name"] for f in listing["files"]]
    if not names:
        die("the lease produced no files under out/")
    for name in sorted(names):
        st, payload = request(key, "GET", f"/sandboxes/{sid}/files/{name}",
                              timeout=1800)
        if st != 200 or not isinstance(payload, bytes):
            die(f"artifact download failed for {name}: HTTP {st}")
        dst = os.path.join(out_dir, name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(payload)
    print(f"[run] downloaded {len(names)} artifact files to {out_dir}", flush=True)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description="One-command run for the gpu-batch-image-gen demo.")
    ap.add_argument("--ref", default="main",
                    help="git ref of this repo to clone in the sandbox "
                         "(default: main)")
    ap.add_argument("--keep", action="store_true",
                    help="leave the CPU sandbox running and print its id")
    ap.add_argument("--render", action="store_true",
                    help="run the GPU lane: render the pinned batch on a "
                         "short-lived GPU lease")
    ap.add_argument("--grade", metavar="DIR",
                    help="judge lane target (default examples/good/batch)")
    ap.add_argument("--out", default="render-out",
                    help="--render: directory to download the artifact into")
    ap.add_argument("--report", metavar="JSON",
                    help="--render: write a JSON report (lease ids, timings)")
    ap.add_argument("--weights-cache",
                    default="~/.cache/gpu-batch-image-gen-weights",
                    help="--render: local cache for the sha256-pinned weights")
    args = ap.parse_args()

    t0 = time.monotonic()
    if args.render:
        render_lane(args)
    else:
        judge_lane(args)
    print(f"[run] total: {time.monotonic() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
