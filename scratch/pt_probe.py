#!/usr/bin/env python3
"""One-lease spp-vs-noise probe for the PathTracing render mode.

Renders a few frames of each scene at several --spp settings (denoised,
plus one raw config to isolate the OptiX denoiser) through the SAME
render_job.py the real run uses, and reports s/frame + converged_pct +
luma_std per config so the run's per-scene spp can be picked against the
3600 s exec budget.  Also downloads one frame of the last config for a
visual check.

Only ever deletes the lease this script created.
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path("/home/user/w/cookbook/omniverse-rtx-scenes")
API = (os.environ.get("SBX_API_URL") or os.environ.get(
    "GPU_API_URL", "https://api.sbx.agent-next.com")).rstrip("/")
KEY = os.environ.get("SBX_API_KEY") or os.environ.get("GPU_API_KEY")
LOG = []

# (scene, tag, extra render_job.py argv)
CONFIGS = [
    ("arm", "arm-rtpt-1", ["--render-mode", "RealTimePathTracing",
                           "--steps-per-frame", "1", "--frame-limit", "3"]),
    ("arm", "arm-pt16", ["--render-mode", "PathTracing", "--spp", "16",
                         "--frame-limit", "3"]),
    ("arm", "arm-pt32", ["--render-mode", "PathTracing", "--spp", "32",
                         "--frame-limit", "3"]),
    ("arm", "arm-pt64", ["--render-mode", "PathTracing", "--spp", "64",
                         "--frame-limit", "3"]),
    ("arm", "arm-pt128", ["--render-mode", "PathTracing", "--spp", "128",
                          "--frame-limit", "3"]),
    ("arm", "arm-pt64-raw", ["--render-mode", "PathTracing", "--spp", "64",
                             "--no-denoise", "--frame-limit", "3"]),
    ("warehouse", "wh-pt32", ["--render-mode", "PathTracing", "--spp", "32",
                              "--frame-limit", "3"]),
]
BUNDLES = ["arm.tar.gz", "warehouse.tar.gz"]


def req(method, path, body=None, timeout=300):
    h = {"X-API-Key": KEY}
    data = None
    if isinstance(body, dict):
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    elif isinstance(body, bytes):
        data = body
        h["Content-Type"] = "application/octet-stream"
    r = urllib.request.Request(API + path, data=data, method=method, headers=h)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read(), time.monotonic() - t0
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), time.monotonic() - t0
    except Exception as exc:
        return None, str(exc).encode(), time.monotonic() - t0


def note(label, status, body, elapsed):
    try:
        parsed = json.loads(body)
    except Exception:
        parsed = body[:1500].decode("utf-8", "replace")
    LOG.append({"label": label, "status": status,
                "elapsed_s": round(elapsed, 3), "reply": parsed})
    print(f"[{label}] HTTP {status} {elapsed:.2f}s "
          f"{json.dumps(parsed, default=str)[:2500]}", flush=True)
    return parsed


def create():
    for attempt in range(1, 200):
        st, body, el = req("POST", "/sandboxes",
                           {"accel": {"vram_gb": 6, "template": "omniverse",
                                      "reserve": "exec"}}, 180)
        if st == 201:
            note("create", st, body, el)
            return json.loads(body)["sandboxID"]
        if st == 409:
            if attempt % 5 == 1:
                print(f"  [create] 409 seat busy (attempt {attempt})", flush=True)
            time.sleep(20)
            continue
        if st is None:
            print(f"  [create] reply lost (attempt {attempt}); retry", flush=True)
            time.sleep(15)
            continue
        note("create-failed", st, body, el)
        return None
    return None


job_b64 = base64.b64encode((HERE / "render" / "render_job.py").read_bytes()).decode()
configs_lit = repr([(s, t, e) for s, t, e in CONFIGS])
code = f"""
import base64, json, pathlib, subprocess, sys, tarfile, time
from pathlib import Path
out = pathlib.Path(OUTPUT_DIR)
work = out / "bundle"
work.mkdir(parents=True, exist_ok=True)
(work / "render_job.py").write_bytes(base64.b64decode({job_b64!r}))
for name in {BUNDLES!r}:
    with tarfile.open(out / name, "r:gz") as tf:
        tf.extractall(work, filter="data")
report = dict(globals().get("report") or {{}})
results = {{}}
for scene, tag, extra in {configs_lit}:
    t0 = time.monotonic()
    proc = subprocess.run([sys.executable, str(work / "render_job.py"),
                           "--workdir", str(work), "--outdir", str(out),
                           "--jobs", scene] + extra,
                          capture_output=True, text=True)
    el = time.monotonic() - t0
    rp = out / "render_report.json"
    row = json.loads(rp.read_text()) if rp.exists() else {{"error": "no report"}}
    # keep the last config's frames for download; earlier ones are stale
    results[tag] = {{"scene": scene, "extra": extra,
                     "returncode": proc.returncode, "wall_s": round(el, 2),
                     "report": row,
                     "tail": (proc.stdout + proc.stderr)[-2500:]}}
    print("CONFIG-DONE " + tag + " rc=" + str(proc.returncode), flush=True)
report["probe"] = results
print("PROBE-RESULT " + json.dumps(results))
"""

if __name__ != "__main__":
    raise SystemExit(0)  # imported for inspection only

sid = create()
if not sid:
    sys.exit("could not create a lease")
try:
    for name in BUNDLES:
        data = Path(f"/tmp/smoke/{name}").read_bytes()
        t0 = time.monotonic()
        st, body, el = req("PUT", f"/sandboxes/{sid}/files/{name}", data, 1800)
        note(f"upload-{name}", st, body, el)
        print(f"# upload {name}: {len(data)/1024/1024:.1f} MB at "
              f"{len(data)/1024/1024/max(el,1e-9):.2f} MB/s", flush=True)
        if st not in (200, 201):
            sys.exit(1)
    st, body, el = req("POST", f"/sandboxes/{sid}/exec",
                       {"code": code, "timeout_s": 2400}, 2500)
    note("exec-probe", st, body, el)
    if st == 200:
        result = json.loads(body)["result"]
        for tag, row in (result.get("report") or {}).get("probe", {}).items():
            rr = row.get("report") or {}
            job = rr.get("jobs") or {}
            for scene, r in job.items():
                print(f"# {tag}: {scene} rc={row['returncode']} "
                      f"mode={r.get('render_mode')} spp={r.get('spp')} "
                      f"denoise={r.get('denoise')} "
                      f"{r.get('s_per_frame')} s/frame "
                      f"converged={r.get('converged_pct')}% "
                      f"luma_std_p50={r.get('luma_std_p50')}", flush=True)
    # grab one rendered frame of the last config for a visual check
    st, body, el = req("GET", f"/sandboxes/{sid}/files", 120)
    if st == 200:
        files = json.loads(body).get("files", [])
        pngs = sorted(f["name"] for f in files
                      if f["name"].startswith("frames/") and f["name"].endswith(".png"))
        if pngs:
            want = pngs[min(1, len(pngs) - 1)]
            st, data, el = req("GET", f"/sandboxes/{sid}/files/{want}", 300)
            if st == 200:
                dst = Path("/tmp/smoke/probe_frame.png")
                dst.write_bytes(data)
                print(f"# downloaded {want} ({len(data)/1024:.0f} KiB) -> {dst}",
                      flush=True)
finally:
    st, body, el = req("DELETE", f"/sandboxes/{sid}", 120)
    note("delete", st, body, el)
    for _ in range(20):
        st2, _, _ = req("GET", f"/sandboxes/{sid}", 60)
        if st2 == 404:
            print("# cleanup verified 404", flush=True)
            break
        time.sleep(3)
    else:
        print(f"# CLEANUP UNCONFIRMED for {sid}", flush=True)
with open("/tmp/smoke/pt_probe.json", "w") as fh:
    json.dump(LOG, fh, indent=2, default=str)
