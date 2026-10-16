#!/usr/bin/env python3
"""Live render smoke: build ONE scene bundle, upload, render N frames,
report s/frame + frame stats. Records everything for PRODUCT-FRICTION.md.
Only deletes the lease it created."""
import base64
import json
import os
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path("/home/user/w/cookbook/omniverse-rtx-scenes")
API = os.environ.get("GPU_API_URL", "https://api.sbx.agent-next.com").rstrip("/")
KEY = os.environ.get("GPU_API_KEY") or os.environ.get("SBX_API_KEY")
LOG = []


def req(method, path, body=None, timeout=300):
    headers = {"X-API-Key": KEY}
    data = None
    if isinstance(body, dict):
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif isinstance(body, bytes):
        data = body
        headers["Content-Type"] = "application/octet-stream"
    r = urllib.request.Request(API + path, data=data, method=method, headers=headers)
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
        parsed = body[:600].decode("utf-8", "replace")
    LOG.append({"label": label, "status": status, "elapsed_s": round(elapsed, 3),
                "reply": parsed})
    s = json.dumps(parsed, default=str)
    print(f"[{label}] HTTP {status} {elapsed:.2f}s {s[:900]}", flush=True)
    return parsed


def create():
    for attempt in range(1, 90):
        st, body, el = req("POST", "/sandboxes",
                           {"accel": {"vram_gb": 6, "template": "omniverse",
                                      "reserve": "exec"}}, 180)
        if st == 201:
            note("create", st, body, el)
            return json.loads(body)["sandboxID"]
        if st == 409:
            if attempt % 10 == 1:
                print(f"[create] 409 seat busy attempt {attempt}", flush=True)
            time.sleep(20)
            continue
        if st is None:
            print(f"[create] reply lost (attempt {attempt}); sleeping 10 s",
                  flush=True)
            time.sleep(10)
            continue
        note("create-failed", st, body, el)
        return None
    return None


SCENE = sys.argv[1] if len(sys.argv) > 1 else "physics"
NFRAMES = int(sys.argv[2]) if len(sys.argv) > 2 else 3
SPF = int(sys.argv[3]) if len(sys.argv) > 3 else 1

bundle = Path(f"/tmp/smoke_{SCENE}.tar.gz")
if not bundle.exists():
    with tarfile.open(bundle, "w:gz") as tf:
        tf.add(str(HERE / "scenes" / SCENE), arcname=SCENE, recursive=True)
print(f"bundle {bundle} {bundle.stat().st_size/1e6:.1f} MB", flush=True)

sid = create()
if not sid:
    sys.exit("no lease")
try:
    data = bundle.read_bytes()
    t0 = time.monotonic()
    st, body, el = req("PUT", f"/sandboxes/{sid}/files/out/{bundle.name}", data, 1800)
    mbps = len(data) / 1e6 / max(el, 1e-9)
    note(f"upload-{SCENE}", st, body, el)
    print(f"upload {len(data)/1e6:.1f} MB at {mbps:.1f} MB/s", flush=True)

    job_b64 = base64.b64encode((HERE / "render" / "render_job.py").read_bytes()).decode()
    code = f"""
import base64, json, pathlib, subprocess, sys, tarfile
from pathlib import Path
out = pathlib.Path(OUTPUT_DIR)
work = out / "bundle"
work.mkdir(parents=True, exist_ok=True)
(work / "render_job.py").write_bytes(base64.b64decode({job_b64!r}))
with tarfile.open(out / "{bundle.name}", "r:gz") as tf:
    tf.extractall(work, filter="data")
report = globals().get('report') if isinstance(globals().get('report'), dict) else {{}}
proc = subprocess.run([sys.executable, str(work/"render_job.py"),
                       "--workdir", str(work), "--outdir", str(out),
                       "--jobs", "{SCENE}", "--frame-limit", "{NFRAMES}",
                       "--steps-per-frame", "{SPF}"],
                      capture_output=True, text=True)
report["exit"] = proc.returncode
report["tail"] = (proc.stdout + proc.stderr)[-3000:]
rp = out / "render_report.json"
if rp.exists():
    report["render"] = json.loads(rp.read_text())
print(json.dumps({{"ok": proc.returncode == 0, "report": report}}))
"""
    st, body, el = req("POST", f"/sandboxes/{sid}/exec",
                       {"code": code, "timeout_s": 1800}, 1900)
    note("exec-render", st, body, el)
    st, body, el = req("GET", f"/sandboxes/{sid}/files", 120)
    note("files-list", st, body, el)
finally:
    st, body, el = req("DELETE", f"/sandboxes/{sid}", 120)
    note("delete", st, body, el)
    for _ in range(20):
        st2, body2, el2 = req("GET", f"/sandboxes/{sid}", 60)
        if st2 == 404:
            print("# cleanup verified 404", flush=True)
            break
        time.sleep(3)
with open(f"/tmp/render_smoke_{SCENE}.json", "w") as fh:
    json.dump(LOG, fh, indent=2, default=str)
