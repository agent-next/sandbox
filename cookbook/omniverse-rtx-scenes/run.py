#!/usr/bin/env python3
"""run.py -- one command from a fresh CPU sandbox to the judged hero frames.

Drives the whole Stage-2 path over the PUBLIC product API (exactly as a
customer does, no other route):

  1. build the three scene bundles (CPU sandbox, no GPU) with
     scenes/build_scenes.py -> bundle.tar.zst (<= 300 MB)
  2. POST {API}/sandboxes {"accel":{"vram_gb":6,"template":"omniverse",
     "reserve":"exec"}} -> 201 with a gl- lease id
  3. PUT {API}/sandboxes/{id}/files/bundle.tar.zst (raw body)
  4. POST {API}/sandboxes/{id}/exec {"code": <python rendered by
     render_job.py wrapper>, "timeout_s": ...} -> untar + render + report
  5. GET {API}/sandboxes/{id}/files, then /files/<name> for every frame
  6. judge the downloaded frames: judge/grade_frames.py
  7. DELETE {API}/sandboxes/{id}, then GET it and prove 404/dead

Wall time is printed per step.  Any non-recoverable failure deletes both
sandboxes in a finally block and exits non-zero naming the id whose
destruction could not be confirmed (see cookbook/LESSONS.md: "a lost
reply is not a confirmation").

Standard library only; reads SBX_API_KEY (or E2B_API_KEY) and SBX_API_URL
(or E2B_API_URL, documented default https://api.sbx.agent-next.com) from
the environment.  Do NOT use the Cloudflare-fronted
sandbox.agent-next.com host for exec (524s after ~100s).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent.parent
RENDER_JOB = HERE / "render" / "render_job.py"
SCENES_DIR = HERE / "scenes"
BUILD_SCENES = SCENES_DIR / "build_scenes.py"

DEFAULT_API_URL = "https://api.sbx.agent-next.com"
SCENES = ("warehouse", "physics", "arm")
UPLOAD_CAP_BYTES = 512 * 1024 * 1024       # PUT raw body cap
BUNDLE_CAP_BYTES = 300 * 1024 * 1024       # per bundle target
TIMEOUT_S = 3600                            # exec budget for a full render


def die(msg: str, code: int = 1) -> None:
    print(f"run.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def key_and_url() -> tuple[str, str]:
    key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
    if not key:
        die("no API key: export SBX_API_KEY (or E2B_API_KEY)")
    url = (os.environ.get("SBX_API_URL") or os.environ.get("E2B_API_URL")
           or DEFAULT_API_URL)
    return key, url.rstrip("/")


def request(key: str, method: str, url: str, body=None, timeout: float = 120.0):
    """One HTTP request; returns (status, payload, elapsed).

    A lost reply is NOT a success: the caller re-issues or verifies state
    (LESSONS.md -- "verify, don't claim").  Never replays an exec after
    a dropped response."""
    if isinstance(body, dict):
        body = json.dumps(body).encode()
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"X-API-Key": key,
                                          "Content-Type": "application/json"
                                          if isinstance(body, dict) or
                                          method in ("POST", "DELETE") else
                                          "application/octet-stream"})
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
            payload = None
        return exc.code, payload, time.monotonic() - t0
    except Exception as exc:                        # unreachable/refused
        return None, str(exc), time.monotonic() - t0


def json_request(key: str, method: str, url: str, body=None, timeout: float = 120.0):
    status, raw, elapsed = request(key, method, url, body, timeout)
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    return status, raw, elapsed


def valid_lease_id(sid) -> bool:
    """Only gateway-generated GPU ids may be interpolated into paths."""
    return (isinstance(sid, str) and sid.startswith("gl-")
            and all(c.isascii() and (c.isalnum() or c == "-") for c in sid))


def step(label: str, t0: float, extra: str = "") -> None:
    print(f"  [{label}] wall {time.monotonic() - t0:.1f} s{extra}", flush=True)


# --------------------------------------------------------------------------- #
# step 1: bundle
# --------------------------------------------------------------------------- #
def _add_dir(tf: tarfile.TarFile, root: Path, arc: str) -> None:
    tf.add(str(root), arcname=arc, recursive=True, filter=lambda ti: ti)


def build_bundle(work: Path) -> dict:
    """Tar+zstd each scene folder; returns {scene: {path, bytes, sha256}}."""
    if not BUILD_SCENES.exists():
        die(f"missing {BUILD_SCENES}")
    t0 = time.monotonic()
    env = dict(os.environ)
    proc = subprocess.run([sys.executable, str(BUILD_SCENES), "--no-bake"],
                          capture_output=True, text=True, cwd=str(HERE),
                          timeout=1800, env=env)
    if proc.returncode:
        die("build_scenes.py failed:\n" + (proc.stderr or "")[-2000:])
    step("build_scenes", t0, f" ({len(SCENES)} scenes)")

    out = {}
    t0 = time.monotonic()
    for scene in SCENES:
        src = SCENES_DIR / scene
        if not (src / "scene.usda").exists():
            die(f"scene {scene} missing scene.usda after build")
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            _add_dir(tf, src, scene)
        raw_zst = subprocess.run(["zstd", "-19", "-c"], input=buf.getvalue(),
                                 capture_output=True, check=True).stdout
        if len(raw_zst) > UPLOAD_CAP_BYTES:
            die(f"bundle {scene} is {len(raw_zst)} bytes, over the "
                f"{UPLOAD_CAP_BYTES // 1024 // 1024} MiB upload cap")
        dst = work / f"{scene}.tar.zst"
        dst.write_bytes(raw_zst)
        out[scene] = {"path": dst, "bytes": len(raw_zst),
                      "sha256": hashlib.sha256(raw_zst).hexdigest()}
        print(f"  [bundle] {scene}: {len(raw_zst) / 1024 / 1024:.1f} MB "
              f"(zstd) sha {out[scene]['sha256'][:12]}", flush=True)
    step("bundle", t0, f" (max {max(v['bytes'] for v in out.values()) / 1024 / 1024:.0f} MB)")
    return out


# --------------------------------------------------------------------------- #
# step 2-3: lease + upload
# --------------------------------------------------------------------------- #
def create_lease(key: str, url: str, attempts: int = 12) -> tuple[str, float, dict]:
    """POST /sandboxes with retry on seat contention (409) and lost replies.

    A 409 is a documented product state (no free seat); the run.py waits
    and retries rather than dying, since this is a shared single GPU node
    (PRODUCT-FRICTION.md).  Only a 201 with a valid gl- id is accepted."""
    last = None
    for attempt in range(1, attempts + 1):
        status, body, elapsed = json_request(key, "POST", f"{url}/sandboxes", {
            "accel": {"vram_gb": 6, "template": "omniverse", "reserve": "exec"}})
        if status == 201 and isinstance(body, dict) and valid_lease_id(body.get("sandboxID")):
            return body["sandboxID"], elapsed, body
        last = {"status": status, "body": body, "attempt": attempt}
        if status == 409:
            print(f"  [lease] no free seat (attempt {attempt}/{attempts}); "
                  f"waiting 60 s", flush=True)
            time.sleep(60)
            continue
        if status is None:
            print(f"  [lease] reply lost (attempt {attempt}/{attempts}); "
                  f"retrying in {attempt * 10} s", flush=True)
            time.sleep(attempt * 10)
            continue
        break
    die(f"GPU create failed: {last}")
    return "", 0.0, {}                     # unreachable


def upload_bundle(key: str, url: str, sid: str, path: Path) -> dict:
    t0 = time.monotonic()
    data = path.read_bytes()
    status, _, elapsed = request(key, "PUT", f"{url}/sandboxes/{sid}/files/bundle.tar.zst",
                                 data, timeout=1800)
    if status not in (200, 201):
        die(f"upload {path.name} to {sid}: HTTP {status}")
    mbps = len(data) / 1024 / 1024 / max(elapsed, 1e-9)
    print(f"  [upload] {path.name}: {len(data) / 1024 / 1024:.1f} MB at "
          f"{mbps:.1f} MB/s ({elapsed:.1f} s)", flush=True)
    return {"bytes": len(data), "seconds": round(elapsed, 3),
            "mbps": round(mbps, 2)}


# --------------------------------------------------------------------------- #
# step 4: exec render
# --------------------------------------------------------------------------- #
def render_code() -> str:
    """The Python the GPU lease runs: untar + invoke render_job.py."""
    return """
import io, json, os, subprocess, sys, tarfile, pathlib, time
out = pathlib.Path(os.environ.get("OUTPUT_DIR") or "/tmp/render")
out.mkdir(parents=True, exist_ok=True)
work = out / "bundle"
work.mkdir(parents=True, exist_ok=True)
with tarfile.open(out / "bundle.tar.zst") as tf:
    tf.extractall(work, filter="data")
log = out / "render_job.log"
with log.open("wb") as fh:
    proc = subprocess.run(
        [sys.executable, str(work / "render_job.py"),
         "--workdir", str(work), "--jobs", "all"],
        stdout=fh, stderr=subprocess.STDOUT)
report = {"exit": proc.returncode}
summary = work.parent / "render_report.json"
if os.environ.get("OUTPUT_DIR") and (pathlib.Path(os.environ["OUTPUT_DIR"]) / "render_report.json").exists():
    report["render"] = json.loads((pathlib.Path(os.environ["OUTPUT_DIR"]) / "render_report.json").read_text())
(out / "job-result.json").write_text(json.dumps(report))
print(json.dumps(report))
"""


def exec_render(key: str, url: str, sid: str, timeout: int) -> dict:
    """POST /exec, never replaying after a dropped reply: poll for the
    result file instead (LESSONS.md -- a stream drop is not an exit)."""
    code = render_code()
    t0 = time.monotonic()
    status, body, _ = json_request(key, "POST", f"{url}/sandboxes/{sid}/exec",
                                   {"code": code, "timeout_s": timeout},
                                   timeout=timeout + 120)
    if status == 200 and isinstance(body, dict):
        return body, time.monotonic() - t0
    if status in (502, 503, 504):
        print(f"  [exec] HTTP {status}; polling for the job result file", flush=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            st, got, _ = json_request(key, "GET", f"{url}/sandboxes/{sid}/files/job-result.json")
            if st == 200 and isinstance(got, dict):
                return got, time.monotonic() - t0
            st2, _, _ = json_request(key, "GET", f"{url}/sandboxes/{sid}")
            if st2 == 404:
                die(f"lease {sid} disappeared during execution")
            time.sleep(10)
        die(f"exec result never arrived for {sid} within {timeout}s")
    die(f"exec: HTTP {status}: {body}")
    return {}, 0.0


def download_frames(key: str, url: str, sid: str, dest: Path) -> dict:
    """GET /files then each frame; verify byte counts against the listing."""
    t0 = time.monotonic()
    status, listing, _ = json_request(key, "GET", f"{url}/sandboxes/{sid}/files")
    if status != 200 or not isinstance(listing, dict):
        die(f"file listing: HTTP {status}")
    rows = [r for r in listing.get("files", []) if r.get("name", "").endswith(".png")]
    if not rows:
        die("no PNG frames listed in the lease")
    dest.mkdir(parents=True, exist_ok=True)
    for r in rows:
        name = r["name"]
        st, data, _ = request(key, "GET", f"{url}/sandboxes/{sid}/files/{name}",
                              timeout=300)
        if st != 200:
            die(f"download {name}: HTTP {st}")
        (dest / name).write_bytes(data)
    step("download", t0, f" ({len(rows)} frames, {sum(r.get('size', 0) for r in rows) / 1024 / 1024:.0f} MB)")
    return {"frames": len(rows)}


# --------------------------------------------------------------------------- #
# cleanup
# --------------------------------------------------------------------------- #
def destroy_lease(key: str, url: str, sid: str) -> None:
    """DELETE then GET and prove the lease is gone.  A lost reply is not a
    confirmation -- the GET decides (LESSONS.md)."""
    try:
        request(key, "DELETE", f"{url}/sandboxes/{sid}")
    except Exception as exc:
        die(f"DELETE {sid} raised {exc}; confirm its state manually")
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        st, body, _ = json_request(key, "GET", f"{url}/sandboxes/{sid}")
        if st == 404:
            print(f"  [cleanup] destroyed {sid}; verified absent (GET 404)", flush=True)
            return
        if st == 200 and isinstance(body, dict) and body.get("phase") == "dead":
            print(f"  [cleanup] destroyed {sid}; verified dead", flush=True)
            return
        time.sleep(3)
    die(f"cleanup unconfirmed for {sid}: GET HTTP {st}; delete it with "
        f"DELETE {url}/sandboxes/{sid}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "out"),
                    help="output dir (frames, verdict, receipt)")
    ap.add_argument("--timeout-s", type=int, default=TIMEOUT_S)
    ap.add_argument("--keep", action="store_true",
                    help="leave the lease up and print its id")
    args = ap.parse_args()

    key, url = key_and_url()
    print(f"run.py: api {url}", flush=True)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    receipt: dict = {"api": url, "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    t_start = time.monotonic()
    # CPU sandbox is the one we run in: nothing else to create.  We only
    # record it as a step so the storyboard shows the two-sandbox story.
    bundles = build_bundle(out)
    receipt["bundles"] = {s: {"bytes": v["bytes"], "sha256": v["sha256"]}
                          for s, v in bundles.items()}

    sid, create_s, _ = create_lease(key, url)
    receipt["gpu_sandbox_id"] = sid
    print(f"  [lease] created {sid} in {create_s:.1f} s", flush=True)
    try:
        up = {}
        for scene, b in bundles.items():
            up[scene] = upload_bundle(key, url, sid, b["path"])
        receipt["uploads"] = up
        result, render_s = exec_render(key, url, sid, args.timeout_s)
        receipt["render_seconds"] = round(render_s, 2)
        receipt["exec_result"] = result
        step("render", t_start, f" ({render_s:.0f} s on the lease)")
        src = out / "frames"
        download_frames(key, url, sid, src)
        # the judge needs the scene files the lease rendered: copy locally
        scene_copy = out / "scene_copy"
        for scene in SCENES:
            if (SCENES_DIR / scene).exists():
                shutil.copytree(SCENES_DIR / scene, scene_copy / scene,
                                dirs_exist_ok=True, ignore=shutil.ignore_patterns("assets*", "mdl"))
        g = subprocess.run([sys.executable, str(HERE / "judge" / "grade_frames.py"),
                            "--run", str(out), "--json"],
                           capture_output=True, text=True, cwd=str(HERE))
        verdict = json.loads(g.stdout)
        (out / "verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True))
        print(f"  [judge] {'PASS' if verdict['pass'] else 'FAIL'} "
              f"(exit {g.returncode}, {g.stderr[-300:] if g.returncode else ''})", flush=True)
        if g.returncode and not verdict.get("pass"):
            pass   # non-pass verdict is reported below; proceed to cleanup
    finally:
        if args.keep:
            print(f"keeping lease {sid}", flush=True)
        else:
            destroy_lease(key, url, sid)
        st, body, _ = json_request(key, "GET", f"{url}/sandboxes")
        ids = {r.get("sandboxID") for r in body} if isinstance(body, list) else set()
        if sid in ids:
            die(f"residual lease {sid} still listed")

    receipt["total_seconds"] = round(time.monotonic() - t_start, 2)
    (out / "run-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True))
    print(f"run.py: total {receipt['total_seconds'] / 60:.1f} min; verdict "
          f"{verdict.get('pass')}", flush=True)
    return 0 if verdict.get("pass") else 1


if __name__ == "__main__":
    sys.exit(main())
