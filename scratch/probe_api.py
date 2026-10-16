#!/usr/bin/env python3
"""Live probe of the GPU sandbox product contract (for PRODUCT-FRICTION.md).

Creates ONE lease (retrying on 409 seat contention), then measures:
  * POST /sandboxes      -> reply shape, meters, wall time
  * PUT  /files/<name>   -> status, where the file lands
  * POST /exec           -> cwd, python, importable modules, OUTPUT_DIR
  * GET  /files          -> name space
  * DELETE               -> status + GET-after-delete
Only ever deletes the id this run created.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("GPU_API_URL", "https://api.sbx.agent-next.com").rstrip("/")
KEY = os.environ.get("GPU_API_KEY") or os.environ.get("SBX_API_KEY")
LOG = []


def req(method, path, body=None, timeout=120):
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
        parsed = body[:400].decode("utf-8", "replace")
    row = {"label": label, "status": status, "elapsed_s": round(elapsed, 3),
           "reply": parsed}
    LOG.append(row)
    print(json.dumps(row, default=str)[:1500], flush=True)
    return row


def create():
    t0 = time.monotonic()
    for attempt in range(1, 240):
        st, body, el = req("POST", "/sandboxes",
                           {"accel": {"vram_gb": 6, "template": "omniverse",
                                      "reserve": "exec"}}, timeout=180)
        if st == 201:
            note("create", st, body, el)
            d = json.loads(body)
            sid = d.get("sandboxID") or d.get("id") or d.get("sandbox_id")
            print(f"# create ok after {attempt} attempt(s), "
                  f"{time.monotonic()-t0:.1f}s total: {sid}", flush=True)
            return sid, d
        if st == 409:
            if attempt % 10 == 1:
                print(f"# 409 no free seat (attempt {attempt}, "
                      f"{time.monotonic()-t0:.0f}s)", flush=True)
            time.sleep(20)
            continue
        note("create-failed", st, body, el)
        return None, None
    return None, None


SMOKE = r"""
import json, os, sys, shutil
info = {
    "cwd": os.getcwd(),
    "argv0": sys.executable,
    "version": sys.version.split()[0],
    "OUTPUT_DIR": globals().get("OUTPUT_DIR", None),
    "report_type": type(globals().get("report")).__name__,
    "report": dict(globals().get("report") or {}),
    "modules": {},
    "which": {n: shutil.which(n) for n in ("ffmpeg", "ffprobe")},
}
import glob as _g
for m in ("ovrtx", "ovstage", "pxr", "PIL", "numpy", "av", "zstandard",
          "cv2", "scipy"):
    try:
        mod = __import__(m)
        info["modules"][m] = getattr(mod, "__version__", "ok")
    except Exception as exc:
        info["modules"][m] = f"ERR {type(exc).__name__}: {exc}"[:80]
# where do PUT files land?  probe from OUTPUT_DIR upwards
od = info["OUTPUT_DIR"]
seen = {}
if od:
    p = od
    for _ in range(4):
        try:
            seen[p] = sorted(os.listdir(p))[:12]
        except Exception as exc:
            seen[p] = f"ERR {exc}"
        p = os.path.dirname(p)
info["tree_from_output_dir"] = seen
try:
    import ovrtx
    info["ovrtx_api"] = sorted(n for n in dir(ovrtx) if not n.startswith("_"))[:40]
    info["has_denoise"] = [n for n in dir(ovrtx) if "denoise" in n.lower()]
except Exception as exc:
    info["ovrtx_api"] = f"ERR {exc}"
report.update(info)
print(json.dumps(info, default=str)[:4000])
"""

if __name__ == "__main__":
    sid, created = create()
    if not sid:
        sys.exit("could not create a lease")
    try:
        # capability probe exactly as the reference does
        st, body, el = req("PUT", f"/sandboxes/{sid}/files/probe.txt",
                           b"probe-bytes", timeout=60)
        note("put-file-root", st, body, el)
        st, body, el = req("PUT", f"/sandboxes/{sid}/files/out/probe2.txt",
                           b"probe2-bytes", timeout=60)
        note("put-file-out", st, body, el)
        st, body, el = req("POST", f"/sandboxes/{sid}/exec",
                           {"code": SMOKE, "timeout_s": 300}, timeout=400)
        note("exec-smoke", st, body, el)
        st, body, el = req("GET", f"/sandboxes/{sid}/files", timeout=120)
        note("files-list", st, body, el)
        st, body, el = req("GET", f"/sandboxes/{sid}", timeout=60)
        note("get-sandbox", st, body, el)
    finally:
        st, body, el = req("DELETE", f"/sandboxes/{sid}", timeout=120)
        note("delete", st, body, el)
        for _ in range(20):
            st2, body2, el2 = req("GET", f"/sandboxes/{sid}", timeout=60)
            if st2 == 404:
                note("get-after-delete", st2, body2, el2)
                print("# cleanup verified: 404", flush=True)
                break
            time.sleep(3)
        else:
            print(f"# cleanup UNCONFIRMED for {sid}", flush=True)
    with open("/tmp/probe_api_log.json", "w") as fh:
        json.dump(LOG, fh, indent=2, default=str)
