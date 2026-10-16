#!/usr/bin/env python3
"""Exposure + light-scale sweep on ONE lease: one frame per config, report
luma stats.  Diagnoses why dome-lit frames come out near-black.

The remote program is assembled with explicit string concatenation (no %
formatting) so a mismatch between placeholders and arguments is impossible.

Only ever deletes the lease this script creates.
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


def req(method, path, body=None, timeout=300):
    h = {"X-API-Key": KEY}
    data = None
    if isinstance(body, dict):
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    elif isinstance(body, bytes):
        data = body
    r = urllib.request.Request(API + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except Exception as exc:
        return None, str(exc).encode()


def create():
    for _ in range(200):
        st, body = req("POST", "/sandboxes", {
            "accel": {"vram_gb": 6, "template": "omniverse", "reserve": "exec"}})
        if st == 201:
            return json.loads(body)["sandboxID"]
        time.sleep(20)
    return None


SCENE = sys.argv[1] if len(sys.argv) > 1 else "arm"
BUNDLE = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
    f"/tmp/smoke/{SCENE}.tar.gz")
CONFIGS = [
    (0.0, 1000.0, 100.0, 0.02),
    (-2.0, 1000.0, 100.0, 0.02),
    (-4.0, 1000.0, 100.0, 0.02),
    (-6.0, 1000.0, 100.0, 0.02),
    (1.0, 1000.0, 100.0, 0.02),
    (2.0, 1000.0, 100.0, 0.02),
    (0.0, 1.0, 100.0, 0.02),
    (0.0, 100000.0, 100.0, 0.02),
    (0.0, 1000.0, 6400.0, 0.02),
    (0.0, 1000.0, 100.0, 0.5),
]
bundle = BUNDLE.read_bytes()
job = (HERE / "render" / "render_job.py").read_bytes()
B64_BUNDLE = base64.b64encode(bundle).decode()
B64_JOB = base64.b64encode(job).decode()
BUNDLE_NAME = BUNDLE.name
CONFIGS_LIT = repr(CONFIGS)

code = f"""
import base64, importlib.util, json, pathlib, subprocess, sys, tarfile
import numpy as np
from PIL import Image
from pxr import Sdf, Usd, UsdLux
import ovrtx, ovstage

out = pathlib.Path(OUTPUT_DIR)
work = out / "bundle"
work.mkdir(parents=True, exist_ok=True)
# the bundle arrives via PUT /files/<name> (no out/ prefix — see run.py)
bundle_path = out / {BUNDLE_NAME!r}
if not bundle_path.exists():
    raise SystemExit("bundle missing from OUTPUT_DIR: " + str(bundle_path))
pathlib.Path(work / "render_job.py").write_bytes(
    base64.b64decode({B64_JOB!r}))
with tarfile.open(bundle_path, "r:gz") as tf:
    tf.extractall(work, filter="data")
spec = importlib.util.spec_from_file_location("rj", str(work / "render_job.py"))
rj = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rj)

scene_root = work / {SCENE!r}
PRODUCT = "/Render/Camera"
LDR_VAR = "/Render/LdrColor"
res = []
for cfg in {CONFIGS_LIT}:
    expo, lscale, iso, shutter = cfg
    wrapper = rj.author_wrapper(scene_root)
    stage = Usd.Stage.Open(str(wrapper))
    for p in stage.Traverse():
        if (p.IsA(UsdLux.DomeLight) or p.IsA(UsdLux.RectLight)
                or p.IsA(UsdLux.DistantLight)):
            a = p.GetAttribute("inputs:intensity")
            if a:
                base = float(a.Get() or 1.0)
                base = base / rj.LIGHT_SCALE if rj.LIGHT_SCALE else base
                a.Set(base * lscale)
        if p.GetTypeName() == "Camera":
            def setattr_t(name, value, vtype):
                a2 = p.GetAttribute(name) or p.CreateAttribute(name, vtype)
                a2.Set(value)
                return a2
            setattr_t("exposure", float(expo), Sdf.ValueTypeNames.Float)
            setattr_t("exposure:iso", iso, Sdf.ValueTypeNames.Float)
            setattr_t("exposure:time", shutter, Sdf.ValueTypeNames.Float)
            setattr_t("omni:rtx:autoExposure:enabled", False,
                      Sdf.ValueTypeNames.Bool)
    stage.Save()

    r = ovrtx.Renderer()
    stg = ovstage.Stage("omniverse.sweep")
    r.attach_ovstage(stg)
    r.open_usd(str(wrapper), ordinal=1)
    stg.advance_write_floor(1, ovstage.Scope.ALL).wait()
    prods = r.step(render_products={{PRODUCT}}, delta_time=1 / 30, ordinal=1)
    px = None
    for prod in prods.values():
        for fr in prod.frames:
            m = fr.render_vars[LDR_VAR].map(device=ovrtx.Device.CPU)
            px = np.from_dlpack(m).copy()
            m.unmap()
            del m
    if px is None:
        res.append({{"cfg": list(cfg), "error": "no pixels"}})
        r.detach_ovstage(); stg.destroy(); r.destroy()
        continue
    lum = 0.2126 * px[..., 0] + 0.7152 * px[..., 1] + 0.0722 * px[..., 2]
    res.append({{
        "exposure": expo, "light_scale": lscale, "iso": iso, "shutter": shutter,
        "mean": round(float(lum.mean()), 3),
        "p50": round(float(np.percentile(lum, 50)), 3),
        "p99": round(float(np.percentile(lum, 99)), 3),
        "max": round(float(lum.max()), 3),
        "nonblack_pct": round(float((lum > 1).mean()) * 100, 3),
    }})
    r.detach_ovstage(); stg.destroy(); r.destroy()
    del px
print("SWEEP-RESULT " + json.dumps(res))
"""

if __name__ != "__main__":
    # imported for inspection only: do not create a lease
    raise SystemExit(0)

sid = create()
if not sid:
    sys.exit("no lease")
try:
    t0 = time.monotonic()
    st, body = req("PUT", f"/sandboxes/{sid}/files/{BUNDLE_NAME}", bundle,
                   1800)
    print(f"upload {st} {len(bundle)/1024/1024:.1f} MB in "
          f"{time.monotonic() - t0:.1f} s", flush=True)
    if st not in (200, 201):
        print(body[:500])
        sys.exit(1)
    st, body = req("POST", f"/sandboxes/{sid}/exec",
                   {"code": code, "timeout_s": 1500}, 1600)
    print("exec", st)
    if st != 200:
        print(body[:2000])
        sys.exit(1)
    r = json.loads(body)["result"]
    print("ok:", r.get("ok"))
    for ln in r.get("stdout", "").splitlines():
        if ln.startswith("SWEEP-RESULT "):
            print(json.dumps(json.loads(ln[len("SWEEP-RESULT "):]), indent=1))
        else:
            print(ln[:500])
finally:
    st, body = req("DELETE", f"/sandboxes/{sid}")
    print("delete", st)
    for _ in range(20):
        st2, _ = req("GET", f"/sandboxes/{sid}")
        if st2 == 404:
            print("verified 404")
            break
        time.sleep(3)
    else:
        print("UNCONFIRMED", sid)
