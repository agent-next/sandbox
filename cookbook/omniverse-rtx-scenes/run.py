#!/usr/bin/env python3
"""run.py -- one command from a fresh CPU sandbox to judged RTX hero frames.

Drives the whole Stage-2 path over the PUBLIC product API (exactly as a
customer does, no other route):

  1. build the three self-contained scene bundles on the CPU sandbox
     (scenes/build_scenes.py) -> <scene>.tar.zst, each <= 300 MB
  2. POST {API}/sandboxes {"accel":{"vram_gb":6,"template":"omniverse",
     "reserve":"exec"}} -> 201 with a gl- lease id
  3. PUT {API}/sandboxes/{id}/files/out/<scene>.tar.zst (raw body, capped
     512 MiB); a capability probe settles whether PUT works or the job
     must receive the bundles via an exec base64 fallback
  4. POST {API}/sandboxes/{id}/exec {"code": <job source>, "timeout_s": ...}
     -> untar each bundle, run render/render_job.py (OVRTX RTX path
     tracer), write PNG frames + mp4s into OUTPUT_DIR
  5. GET {API}/sandboxes/{id}/files, then /files/<name> for the frames
  6. judge the downloaded frames: judge/grade_frames.py + the mutant
     selftest (judge/mutate_frames.py --selftest)
  7. DELETE {API}/sandboxes/{id}, then GET it and prove 404/dead

`meters` is recorded from every reply that carries it (GPU seconds,
cost) so RECEIPT.md can show what a run actually pays for.

Wall time is printed per step.  Any non-recoverable failure deletes the
lease in a finally block and exits non-zero naming the id whose
destruction could not be confirmed (LESSONS.md: "a lost reply is not a
confirmation").

Standard library only; reads SBX_API_KEY (or E2B_API_KEY / GPU_API_KEY)
and SBX_API_URL (or E2B_API_URL / GPU_API_URL, documented default
https://api.sbx.agent-next.com) from the environment.  Do NOT use the
Cloudflare-fronted sandbox.agent-next.com host for exec (524s after
~100s).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RENDER_JOB = HERE / "render" / "render_job.py"
SCENES_DIR = HERE / "scenes"
BUILD_SCENES = SCENES_DIR / "build_scenes.py"
GRADE = HERE / "judge" / "grade_frames.py"
MUTATE = HERE / "judge" / "mutate_frames.py"

DEFAULT_API_URL = "https://api.sbx.agent-next.com"
SCENES = ("warehouse", "physics", "arm")
UPLOAD_CAP_BYTES = 512 * 1024 * 1024       # PUT raw body cap
BUNDLE_CAP_BYTES = 300 * 1024 * 1024       # per-bundle target (spec)
TIMEOUT_S = 3600                            # exec budget for the full render
CREATE_ATTEMPTS = 90                        # seat contention retries (~45 min)
FETCH_TIMEOUT = 120


def die(msg: str, code: int = 1) -> None:
    print(f"run.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def key_and_url() -> tuple[str, str]:
    key = (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
           or os.environ.get("GPU_API_KEY"))
    if not key:
        die("no API key: export SBX_API_KEY (or E2B_API_KEY / GPU_API_KEY)")
    url = (os.environ.get("SBX_API_URL") or os.environ.get("E2B_API_URL")
           or os.environ.get("GPU_API_URL") or DEFAULT_API_URL)
    return key, url.rstrip("/")


class ApiError(RuntimeError):
    pass


def request(key: str, method: str, url: str, body=None, timeout: float = FETCH_TIMEOUT):
    """One HTTP request; returns (status, payload, elapsed).

    A lost reply is NOT a success: the caller re-issues or verifies state
    (LESSONS.md -- "verify, don't claim").  Never replays an exec after
    a dropped response."""
    headers = {"X-API-Key": key}
    if isinstance(body, dict):
        body = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif isinstance(body, bytes):
        headers["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, raw, time.monotonic() - t0
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = raw
        return exc.code, payload, time.monotonic() - t0
    except Exception as exc:                        # unreachable/refused
        return None, str(exc), time.monotonic() - t0


def json_request(key: str, method: str, url: str, body=None, timeout: float = FETCH_TIMEOUT):
    status, raw, elapsed = request(key, method, url, body, timeout)
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    return status, raw, elapsed


def meters_of(body) -> dict:
    """Pull the `meters` dict out of a reply ({} when absent)."""
    if isinstance(body, dict):
        m = body.get("meters")
        if isinstance(m, dict):
            return m
    return {}


def valid_lease_id(sid) -> bool:
    """Only gateway-generated GPU ids may be interpolated into paths."""
    return (isinstance(sid, str) and sid.startswith("gl-")
            and all(c.isascii() and (c.isalnum() or c == "-") for c in sid))


def step(label: str, t0: float, extra: str = "") -> None:
    print(f"  [{label}] wall {time.monotonic() - t0:.1f} s{extra}", flush=True)


class Tee:
    """Mirror stdout to <out>/run.log so the terminal segment of the demo
    video is the real run's own output (STORYBOARD.md slot 5).

    The real stream is captured at CONSTRUCTION: writing through
    sys.stdout here would recurse (sys.stdout is this Tee)."""

    def __init__(self, out: Path):
        self.path = out / "run.log"
        self.fh = self.path.open("w")
        self.real = sys.stdout

    def write(self, s: str):
        self.real.write(s)
        self.fh.write(s)

    def flush(self):
        self.real.flush()
        self.fh.flush()


# --------------------------------------------------------------------------- #
# step 1: bundles (CPU)
# --------------------------------------------------------------------------- #
def build_bundle(work: Path) -> dict:
    """Build each scene with build_scenes.py, then tar+gzip the folder.

    gzip, not zstd: the omniverse image has neither the `zstandard`
    module nor a `zstd` binary (verified live, PRODUCT-FRICTION.md), so
    a .tar.zst bundle cannot be unpacked on the lease.  Stdlib tarfile
    reads gz on both sides.
    """
    if not BUILD_SCENES.exists():
        die(f"missing {BUILD_SCENES}")
    t0 = time.monotonic()
    proc = subprocess.run([sys.executable, str(BUILD_SCENES), "--no-bake"],
                          capture_output=True, text=True, cwd=str(HERE),
                          timeout=1800)
    if proc.returncode:
        die("build_scenes.py failed:\n" + (proc.stderr or "")[-2000:])
    step("build_scenes", t0, f" ({len(SCENES)} scenes)")

    out = {}
    t0 = time.monotonic()
    work.mkdir(parents=True, exist_ok=True)
    for scene in SCENES:
        src = SCENES_DIR / scene
        if not (src / "scene.usda").exists():
            die(f"scene {scene} missing scene.usda after build")
        dst = work / f"{scene}.tar.gz"
        with tarfile.open(dst, mode="w:gz") as tf:
            tf.add(str(src), arcname=scene, recursive=True)
        if dst.stat().st_size > UPLOAD_CAP_BYTES:
            die(f"bundle {scene} is {dst.stat().st_size} bytes, over the upload cap")
        out[scene] = {"path": dst, "bytes": dst.stat().st_size,
                      "sha256": hashlib.sha256(dst.read_bytes()).hexdigest()}
        print(f"  [bundle] {scene}: {dst.stat().st_size / 1024 / 1024:.1f} MB "
              f"(tar.gz) sha {out[scene]['sha256'][:12]}", flush=True)
    step("bundle", t0, f" (max {max(v['bytes'] for v in out.values()) / 1024 / 1024:.0f} MB)")
    return out


# --------------------------------------------------------------------------- #
# step 2-3: lease + upload
# --------------------------------------------------------------------------- #
# A lease that appeared during a lost POST reply: possibly created by this
# run, but NOT provably ours (no idempotency key in the API, clientID is
# constant) — recorded loudly, never auto-adopted or deleted.
POSSIBLE_LEAK: set[str] = set()


def create_lease(key: str, url: str, attempts: int = CREATE_ATTEMPTS) -> tuple[str, float, dict]:
    """POST /sandboxes with retry on every transient state.

    Retried, not fatal (all observed live on this account):
      * 409 gpu_capacity_exhausted — one nvidia.5090 node, one seat;
        the reply's retry_after_s:5 is advisory, there is no queue.
      * 5xx (503 "gateway is restarting", "no GPU node reachable") — the
        control plane restarts under load; the lease was NOT created.
      * a lost reply (timeout mid-read) — the lease may exist; see
        POSSIBLE_LEAK above for why it is recorded, never adopted.
    Only a 201 with a valid gl- id is accepted."""
    before = set(new_leases(key, url, before=set()))
    last = None
    for attempt in range(1, attempts + 1):
        status, body, elapsed = json_request(key, "POST", f"{url}/sandboxes", {
            "accel": {"vram_gb": 6, "template": "omniverse", "reserve": "exec"},
        }, timeout=180)
        if status == 201 and isinstance(body, dict) and valid_lease_id(body.get("sandboxID")):
            return body["sandboxID"], elapsed, body
        last = {"status": status, "body": body, "attempt": attempt}
        if status == 409:
            if attempt % 6 == 0 or attempt == 1:
                print(f"  [lease] no free seat (attempt {attempt}/{attempts}); "
                      f"waiting 30 s", flush=True)
            time.sleep(30)
            continue
        if status is None:
            # The POST may have created a lease whose reply we never saw.
            # The API offers no idempotency key and clientID is constant,
            # so a lease that appeared here is NOT provably ours — a
            # parallel agent creating at the same moment is
            # indistinguishable.  Never adopt-or-delete by listing:
            # record it for the operator (see PRODUCT-FRICTION.md F8) and
            # keep retrying; the seat it holds will 409 us until it is
            # resolved deliberately.
            maybe = new_leases(key, url, before)
            if maybe:
                print(f"  [lease] LOST REPLY + new lease appeared: {maybe} "
                      f"— possibly created by this run's POST; it is NOT "
                      f"provably ours, refusing to auto-adopt/delete",
                      flush=True)
                POSSIBLE_LEAK.update(maybe)
            print(f"  [lease] reply lost (attempt {attempt}/{attempts}); "
                  f"retrying in 20 s", flush=True)
            time.sleep(20)
            continue
        if isinstance(status, int) and 500 <= status < 600:
            wait = 5.0
            if isinstance(body, dict):
                wait = float(body.get("retry_after_s") or 5)
            print(f"  [lease] gateway {status} (attempt {attempt}/{attempts}); "
                  f"retrying in {wait:.0f} s", flush=True)
            time.sleep(max(2.0, min(wait, 30.0)))
            continue
        break
    die(f"GPU create failed: {last}")
    return "", 0.0, {}                     # unreachable


POSSIBLE_LEAK: set[str] = set()


def new_leases(key: str, url: str, before: set[str]) -> list[str]:
    """Leases that appeared since `before` (read-only inventory diff).

    With before=set() this is just the current inventory snapshot."""
    status, body, _ = request(key, "GET", f"{url}/sandboxes", None, timeout=60)
    if status != 200 or not isinstance(body, list):
        return []
    return sorted(r.get("sandboxID") for r in body
                  if isinstance(r, dict) and valid_lease_id(r.get("sandboxID"))
                  and r.get("sandboxID") not in before)


def probe_upload(key: str, url: str, sid: str) -> bool:
    """Probe whether PUT /files works on this plane; True => PUT route ok."""
    status, _, _ = request(key, "PUT",
                           f"{url}/sandboxes/{sid}/files/out/upload-probe",
                           b"", timeout=60)
    return status in (200, 201)


def upload_bundle(key: str, url: str, sid: str, path: Path) -> dict:
    """PUT <scene>.tar.zst under the workdir-relative out/ prefix."""
    t0 = time.monotonic()
    data = path.read_bytes()
    status, reply, elapsed = request(key, "PUT",
                                     f"{url}/sandboxes/{sid}/files/out/{path.name}",
                                     data, timeout=1800)
    if status not in (200, 201):
        die(f"upload {path.name} to {sid}: HTTP {status}")
    mbps = len(data) / 1024 / 1024 / max(elapsed, 1e-9)
    print(f"  [upload] {path.name}: {len(data) / 1024 / 1024:.1f} MB at "
          f"{mbps:.1f} MB/s ({elapsed:.1f} s)", flush=True)
    return {"bytes": len(data), "seconds": round(elapsed, 3),
            "mbps": round(mbps, 2), "meters": meters_of(reply)}


# --------------------------------------------------------------------------- #
# step 4: exec render
# --------------------------------------------------------------------------- #
def render_program(bundles: dict, job_source: str, fallback_upload: bool = False) -> str:
    """The Python the GPU lease runs: untar each bundle + run render_job.py.

    The gateway injects OUTPUT_DIR (the synced directory GET /files
    serves) and `report` (a dict returned verbatim in the exec reply).
    Files PUT under out/ land in OUTPUT_DIR, so the bundles are read from
    there and frames written next to them.  With fallback_upload the
    bundles are base64-embedded in the source instead (tiny bundles
    only; the real ~50-110 MB scenes never go this way)."""
    names = sorted(bundles)
    if fallback_upload:
        total = sum(Path(info["path"]).stat().st_size for info in bundles.values())
        if total > 40 * 1024 * 1024:
            die("bundle too large for the exec-base64 fallback; the PUT "
                "/files route must be available on this plane")
        setup = []
        for scene, info in bundles.items():
            b64 = base64.b64encode(Path(info["path"]).read_bytes()).decode()
            setup.append(f"_p = out / '{scene}.tar.gz'; "
                         f"_p.write_bytes(base64.b64decode({b64!r})); "
                         f"paths['{scene}'] = _p")
        uploads = "\n".join(setup)
    else:
        uploads = ""
    job_b64 = base64.b64encode(job_source.encode()).decode()
    return f"""
import base64, json, os, pathlib, subprocess, sys, tarfile, time
from pathlib import Path
out = pathlib.Path(OUTPUT_DIR)
out.mkdir(parents=True, exist_ok=True)
work = out / "bundle"
work.mkdir(parents=True, exist_ok=True)
(work / "render_job.py").write_bytes(base64.b64decode({job_b64!r}))
paths = {{}}
for name in {names!r}:
    cand = out / f"{{name}}.tar.gz"
    if not cand.exists():
        raise SystemExit("bundle missing from OUTPUT_DIR: " + str(cand))
    paths[name] = cand
{uploads}
for name, path in paths.items():
    with tarfile.open(path, "r:gz") as tf:
        tf.extractall(work, filter="data")
render_job = work / "render_job.py"
if not render_job.exists():
    raise SystemExit("render_job.py missing in bundle")
log = out / "render_job.log"
report = {{}} if not isinstance(globals().get('report'), dict) else globals()['report']
report['bundles'] = {{n: p.name for n, p in paths.items()}}
with log.open("wb") as fh:
    proc = subprocess.run(
        [sys.executable, str(render_job), "--workdir", str(work),
         "--outdir", str(out), "--jobs", "all"],
        stdout=fh, stderr=subprocess.STDOUT)
report["exit"] = proc.returncode
rp = out / "render_report.json"
if rp.exists():
    report["render"] = json.loads(rp.read_text())
report["log_tail"] = log.read_text(errors="replace")[-4000:] if log.exists() else ""
result = {{"ok": proc.returncode == 0, "report": report,
          "log": str(out / "render_job.log")}}
(out / "job-result.json").write_text(json.dumps(result))
print(json.dumps(result))
"""


def exec_render(key: str, url: str, sid: str, code: str, timeout: int) -> tuple[dict, float]:
    """POST /exec, never replaying after a dropped reply: poll for the
    result file instead (LESSONS.md -- a stream drop is not an exit)."""
    t0 = time.monotonic()
    status, body, _ = json_request(key, "POST", f"{url}/sandboxes/{sid}/exec",
                                   {"code": code, "timeout_s": timeout},
                                   timeout=timeout + 120)
    result = None
    if status == 200 and isinstance(body, dict):
        result = body.get("result") if isinstance(body.get("result"), dict) else body
    elif status in (502, 503, 504, 524):
        print(f"  [exec] HTTP {status}; polling for the job result file", flush=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            st, got, _ = json_request(key, "GET",
                                      f"{url}/sandboxes/{sid}/files/job-result.json")
            if st == 200 and isinstance(got, dict):
                result = got.get("result") if isinstance(got.get("result"), dict) else got
                break
            st2, _, _ = json_request(key, "GET", f"{url}/sandboxes/{sid}")
            if st2 == 404:
                die(f"lease {sid} disappeared during execution")
            print("  [exec] result not yet available; sleeping 10 s", flush=True)
            time.sleep(10)
        if result is None:
            die(f"exec result never arrived for {sid} within {timeout} s")
    else:
        die(f"exec: HTTP {status}: {body}")
    ok = result.get("ok", False)
    if not ok:
        rpt = result.get("report") or {}
        detail = (rpt or {}).get("exit") or (result.get("log"))
        tail = (rpt or {}).get("log_tail") or ""
        die(f"GPU job failed (ok=False, exit={detail})\n{tail[-1500:]}")
    return result, time.monotonic() - t0


def download_outputs(key: str, url: str, sid: str, dest: Path,
                     want_png_stride: int = 15) -> dict:
    """GET /files then every artifact; keep full frames on a stride.

    The mp4s, report, log and hero frames are small and always fetched;
    full-resolution PNGs are fetched every `want_png_stride` frames (the
    judge samples frames at that stride and needs consecutive windows for
    the temporal gate)."""
    t0 = time.monotonic()
    status, listing, _ = json_request(key, "GET", f"{url}/sandboxes/{sid}/files",
                                      timeout=120)
    if status != 200 or not isinstance(listing, dict):
        die(f"file listing: HTTP {status}")
    rows = listing.get("files", [])
    if not rows:
        die("no files listed in the lease")
    dest.mkdir(parents=True, exist_ok=True)
    seen = bytes_total = 0
    errors = []
    for r in rows:
        name = r.get("name", "")
        if not name:
            continue
        keep = (not name.startswith("frames/")
                or _on_stride(name, want_png_stride))
        if not keep:
            continue
        st, data, _ = request(key, "GET",
                              f"{url}/sandboxes/{sid}/files/{name}",
                              timeout=300)
        if st != 200:
            errors.append(f"download {name}: HTTP {st}")
            continue
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        seen += 1
        bytes_total += len(data)
        if "size" in r and len(data) != r["size"]:
            errors.append(f"download {name}: incomplete ({len(data)} of "
                          f"{r['size']} bytes)")
    if errors:
        die("; ".join(errors[:3]))
    step("download", t0, f" ({seen} files, {bytes_total / 1024 / 1024:.0f} MB)")
    return {"files": seen, "bytes": bytes_total, "listed": len(rows)}


def _on_stride(name: str, stride: int) -> bool:
    """frames/<scene>/NNNN.png kept when NNNN % stride == 0 or in the first
    30-frame window (the temporal gate needs a consecutive run)."""
    stem = Path(name).stem
    if not stem.isdigit():
        return True
    idx = int(stem)
    return idx % stride == 0 or idx < 30


# --------------------------------------------------------------------------- #
# cleanup
# --------------------------------------------------------------------------- #
def destroy_lease(key: str, url: str, sid: str) -> None:
    """DELETE then GET and prove the lease is gone.  A lost reply is not a
    confirmation -- the GET decides (LESSONS.md)."""
    try:
        status, _, _ = request(key, "DELETE", f"{url}/sandboxes/{sid}")
    except Exception as exc:
        die(f"DELETE {sid} raised {exc}; confirm its state manually")
    deadline = time.monotonic() + 60
    st = None
    while time.monotonic() < deadline:
        st, body, _ = json_request(key, "GET", f"{url}/sandboxes/{sid}")
        if st == 404:
            print(f"  [cleanup] destroyed {sid}; verified absent (GET 404)", flush=True)
            return
        if st == 200 and isinstance(body, dict) and body.get("phase") == "dead":
            print(f"  [cleanup] destroyed {sid}; verified dead", flush=True)
            return
        time.sleep(3)
    die(f"cleanup unconfirmed for {sid}: GET HTTP {st}; resolve it manually")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "out"),
                    help="output dir (frames, verdict, receipt)")
    ap.add_argument("--timeout-s", type=int, default=TIMEOUT_S)
    ap.add_argument("--keep", action="store_true",
                    help="leave the lease up and print its id")
    ap.add_argument("--fallback-upload", action="store_true",
                    help="force the exec-base64 upload path (debug)")
    ap.add_argument("--skip-selftest", action="store_true",
                    help="skip the mutant selftest (debug)")
    args = ap.parse_args()

    key, url = key_and_url()
    print(f"run.py: api {url}", flush=True)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    real_stdout = sys.stdout
    sys.stdout = Tee(out)
    receipt: dict = {"api": url,
                     "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    t_start = time.monotonic()
    bundles = build_bundle(out / "bundles")
    receipt["bundles"] = {s: {"bytes": v["bytes"], "sha256": v["sha256"]}
                          for s, v in bundles.items()}

    sid, create_s, created = create_lease(key, url)
    receipt["gpu_sandbox_id"] = sid
    receipt["create"] = {"seconds": round(create_s, 3), "meters": meters_of(created)}
    print(f"  [lease] created {sid} in {create_s:.1f} s", flush=True)
    verdict: dict = {"pass": False}
    try:
        up = {}
        use_put = args.fallback_upload or probe_upload(key, url, sid)
        receipt["upload_method"] = "PUT" if use_put else "exec-base64"
        print(f"  [upload] route: {'PUT /files' if use_put else 'exec base64'}",
              flush=True)
        if use_put:
            for scene, b in bundles.items():
                up[scene] = upload_bundle(key, url, sid, b["path"])
        receipt["uploads"] = up
        result, render_s = exec_render(key, url, sid,
                                       render_program(bundles, RENDER_JOB.read_text(),
                                                      fallback_upload=not use_put),
                                       args.timeout_s)
        receipt["render_seconds"] = round(render_s, 2)
        receipt["exec_result"] = result
        receipt["render_report"] = (result.get("report") or {}).get("render")
        step("render", t_start, f" ({render_s:.0f} s on the lease)")
        src = out / "frames"
        receipt["download"] = download_outputs(key, url, sid, src)
        # final meters snapshot before the lease dies
        st, snap, _ = json_request(key, "GET", f"{url}/sandboxes/{sid}")
        receipt["final_meters"] = meters_of(snap) if st == 200 else {}
        g = subprocess.run([sys.executable, str(GRADE), "--run", str(out), "--json"],
                           capture_output=True, text=True, cwd=str(HERE))
        verdict = json.loads(g.stdout)
        (out / "verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True))
        print(f"  [judge] {'PASS' if verdict['pass'] else 'FAIL'} "
              f"(exit {g.returncode})", flush=True)
        if not args.skip_selftest:
            m = subprocess.run([sys.executable, str(MUTATE), "--selftest",
                                "--frames", str(src)],
                               capture_output=True, text=True, cwd=str(HERE))
            (out / "selftest.txt").write_text(m.stdout + m.stderr)
            print(m.stdout.strip().splitlines()[-1] if m.stdout.strip()
                  else "selftest produced no output", flush=True)
            if m.returncode:
                verdict = dict(verdict)
                verdict["selftest_kill"] = "FAILED"
    finally:
        if args.keep:
            print(f"keeping lease {sid}", flush=True)
        else:
            destroy_lease(key, url, sid)

    receipt["total_seconds"] = round(time.monotonic() - t_start, 2)
    if POSSIBLE_LEAK:
        receipt["possible_leaked_leases"] = sorted(POSSIBLE_LEAK)
        print("run.py: WARNING — leases that appeared during lost POST "
              "replies (NOT provably this run's; verify before deleting): "
              f"{sorted(POSSIBLE_LEAK)}", flush=True)
    (out / "run-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True))
    print(f"run.py: total {receipt['total_seconds'] / 60:.1f} min; verdict "
          f"{verdict.get('pass')}", flush=True)
    sys.stdout = real_stdout
    print(f"run.py: total {receipt['total_seconds'] / 60:.1f} min; verdict "
          f"{verdict.get('pass')}; log {out / 'run.log'}", flush=True)
    return 0 if verdict.get('pass') else 1


if __name__ == "__main__":
    sys.exit(main())
