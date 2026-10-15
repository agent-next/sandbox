#!/usr/bin/env python3
"""judge/check_gates.py — run every gate on a shaders-gallery artifact.

Serves a scratch copy of the artifact plus the sha256-verified vendor
copy of the shaders library over http://127.0.0.1, drives headless
Chromium via playwright, and prints one JSON verdict.  All
wall-time-dependent fields live under "timing"; everything else is
deterministic for a given --seed (rendering is frame-locked).

Usage: check_gates.py <artifact_dir> [--seed N] [--json out.json]
Exit: 0 if every gate passes, 1 otherwise, 2 on usage/harness error.
"""

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
MOUNT_JS = os.path.join(HERE, "mount.js")
VENDOR = os.environ.get(
    "SHADERS_VENDOR", os.path.expanduser("~/.shaders-gallery/vendor"))
CHROMIUM = os.environ.get("CHROMIUM_BIN", "/usr/bin/chromium")
CHROME_ARGS = ["--no-sandbox", "--enable-unsafe-webgpu",
               "--enable-unsafe-swiftshader"]

FORBIDDEN_TOKENS = ["createShaderModule", "GPUShaderModule", "wgsl",
                    "gl_FragColor", "fragmentShader", "vertexShader"]
VAR_MIN = 12.0
COLORS_MIN = 20
DIFF_MIN = 4.0
FRAME_TIME_MAX = 20.0          # s/frame, SwiftShader floor (gate 6)
MOUNT_TIMEOUT = 30.0           # s, per SPEC
FRAME_TIMEOUT = 90.0           # s per renderFrame call


# --------------------------------------------------------------------------
# static analysis (gate 4)
# --------------------------------------------------------------------------

def registry_names(vendor):
    reg = os.path.join(vendor, "dist", "registry.js")
    text = open(reg, encoding="utf-8").read()
    # top-level entries only: 4-space indent, followed by "category"
    return set(re.findall(r'"name": "([A-Za-z0-9]+)",\n    "category"', text))


def scan_tokens(root):
    hits = []
    files = ["index.html"]
    html = open(os.path.join(root, "index.html"), encoding="utf-8").read()
    for m in re.finditer(r'(?:src|href)\s*=\s*["\']([^"\']+\.(?:js|mjs))["\']', html):
        files.append(m.group(1).lstrip("/"))
    for f in files:
        p = os.path.join(root, f)
        if not os.path.isfile(p):
            continue
        text = open(p, encoding="utf-8", errors="replace").read()
        for tok in FORBIDDEN_TOKENS:
            if tok in text:
                hits.append(f"{f}:{tok}")
    return hits


# --------------------------------------------------------------------------
# static file server: artifact at /, library at /vendor/
# --------------------------------------------------------------------------

def make_server(scratch, vendor):
    class H(SimpleHTTPRequestHandler):
        def translate_path(self, path):
            path = os.path.normpath(path.split("?")[0].split("#")[0])
            if path == "/vendor" or path.startswith("/vendor/"):
                base, rel = vendor, path[len("/vendor/"):]
            else:
                base, rel = scratch, path.lstrip("/")
            full = os.path.abspath(os.path.join(base, rel))
            if full.startswith(os.path.abspath(base) + os.sep) or \
                    full == os.path.abspath(base):
                return full
            return os.path.join(os.path.abspath(base), "__nope__")

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, srv.server_address[1]


# --------------------------------------------------------------------------
# browser grading
# --------------------------------------------------------------------------

async def grade(artifact, seed, vendor):
    from playwright.async_api import async_playwright

    verdict = {
        "artifact": os.path.basename(artifact.rstrip("/")),
        "seed": seed,
        "backend": {"readback": "copyTextureToBuffer",
                    "renderer": "createRendererFromJSON/frame-locked"},
        "gates": {},
        "timing": {},
    }
    console_errors = []
    page_errors = []

    shim = open(MOUNT_JS, encoding="utf-8").read()
    srv, port = make_server(artifact, vendor)
    url = f"http://127.0.0.1:{port}/index.html"
    t_start = time.monotonic()
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                executable_path=CHROMIUM, headless=True, args=CHROME_ARGS)
            ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
            await ctx.add_init_script(shim)
            page = await ctx.new_page()
            page.on("console", lambda m: console_errors.append(m.text[:200])
                    if m.type == "error" else None)
            page.on("pageerror", lambda e: page_errors.append(str(e)[:200]))

            await page.goto(url, wait_until="load", timeout=30000)
            await page.wait_for_timeout(500)
            probe = await page.evaluate("window.__judge.probe()")
            verdict["backend"]["probe"] = probe

            # ---- mounts + pixel gates + perf ----
            manifest = json.load(open(os.path.join(artifact, "artist.json")))
            mounts, per_fx = {}, {}
            for fx in manifest["effects"]:
                name = f"{fx['type']}#{fx['region']}"
                sel = f"#{fx['region']} canvas"
                t0 = time.monotonic()
                try:
                    res = await asyncio.wait_for(page.evaluate(
                        "([sel, preset]) => window.__judge.mount(sel, preset)",
                        [sel, json.dumps(
                            {"components": [{"type": fx["type"], "id": "fx",
                                             "props": fx.get("props", {})}]})]),
                        timeout=MOUNT_TIMEOUT)
                except Exception as e:
                    res = {"ok": False, "error": str(e)[:200]}
                mounts[name] = res
                entry = {"mount": res.get("ok"), "fail": res.get("fail")}
                if res.get("ok"):
                    fid = res["id"]
                    times = []
                    async def frame(d):
                        t = time.monotonic()
                        r = await asyncio.wait_for(page.evaluate(
                            "([fid, d]) => window.__judge.frame(fid, d)",
                            [fid, d]), timeout=FRAME_TIMEOUT)
                        times.append(time.monotonic() - t)
                        return r
                    try:
                        await frame(0.1)               # warmup (known flat)
                        fA = await frame(0.5)          # capture A
                        fB = await frame(1.0)          # capture B (+1.0s)
                        entry["statsA"] = fA.get("stats")
                        entry["statsB"] = fB.get("stats")
                        entry["diffAB"] = await page.evaluate(
                            "id => window.__judge.diffLast(id)", fid)
                        entry["frameTimes"] = [round(t, 3) for t in times]
                    except Exception as e:
                        entry["error"] = str(e)[:200]
                per_fx[name] = entry
                entry["wall_s"] = round(time.monotonic() - t0, 3)

            # ---- gate 5 layout at 1440 and 375 ----
            lay = {}
            lay["w1440"] = await page.evaluate("window.__judge.layout()")
            lay["regions1440"] = {
                fx["region"]: await page.evaluate(
                    "sel => window.__judge.regionBox(sel)",
                    f"#{fx['region']}") for fx in manifest["effects"]}
            page2 = await ctx.new_page()
            await page2.set_viewport_size({"width": 375, "height": 780})
            await page2.goto(url, wait_until="load", timeout=30000)
            await page2.wait_for_timeout(300)
            lay["w375"] = await page2.evaluate("window.__judge.layout()")
            lay["regions375"] = {
                fx["region"]: await page2.evaluate(
                    "sel => window.__judge.regionBox(sel)",
                    f"#{fx['region']}") for fx in manifest["effects"]}
            await browser.close()
    finally:
        srv.shutdown()

    # ------------------------- verdict -------------------------
    verdict["consoleErrors"] = console_errors
    verdict["pageErrors"] = page_errors
    verdict["effects"] = per_fx

    ok = lambda b: bool(b)
    verdict["gates"]["g1_page_and_probes"] = {
        "pass": ok(not console_errors and not page_errors
                   and all(m.get("ok") for m in mounts.values())),
        "consoleErrors": len(console_errors),
        "pageErrors": len(page_errors),
        "mounts": {k: {"ok": m.get("ok"), "error": m.get("error"),
                       "fail": m.get("fail")} for k, m in mounts.items()},
        "adapter": probe.get("adapter"),
    }
    verdict["gates"]["g2_nonblank"] = {
        "pass": all(e.get("statsA", {}).get("ok")
                    and e["statsA"]["variance"] > VAR_MIN
                    and e["statsA"]["distinctColors12"] > COLORS_MIN
                    for e in per_fx.values()) and bool(per_fx),
        "thresholds": {"variance": VAR_MIN, "distinctColors12": COLORS_MIN},
        "measured": {k: e.get("statsA") for k, e in per_fx.items()},
    }
    verdict["gates"]["g3_animation"] = {
        "pass": all(e.get("diffAB") is not None and e["diffAB"] > DIFF_MIN
                    for e in per_fx.values()) and bool(per_fx),
        "thresholds": {"meanAbsDiff": DIFF_MIN},
        "measured": {k: e.get("diffAB") for k, e in per_fx.items()},
    }
    g5 = {
        "w1440": lay["w1440"], "w375": lay["w375"],
        "regions1440": lay["regions1440"], "regions375": lay["regions375"],
    }
    g5ok = (g5["w1440"]["scrollWidth"] <= g5["w1440"]["innerWidth"] + 1
            and g5["w375"]["scrollWidth"] <= g5["w375"]["innerWidth"] + 1
            and g5["w1440"]["h1Height"] > 0 and g5["w375"]["h1Height"] > 0
            and all((b and b["h"] >= 100) for b in lay["regions1440"].values())
            and all((b and b["h"] >= 80) for b in lay["regions375"].values()))
    g5["pass"] = ok(g5ok)
    verdict["gates"]["g5_layout"] = g5

    perf = {k: (sum(e["frameTimes"]) / len(e["frameTimes"])
                if e.get("frameTimes") else None)
            for k, e in per_fx.items()}
    verdict["timing"]["performance"] = {
        "meanFrameTimeS": perf,
        "thresholdS": FRAME_TIME_MAX,
    }
    verdict["gates"]["g6_performance"] = {
        "pass": all(v is not None and v <= FRAME_TIME_MAX for v in perf.values())
                and bool(per_fx),
    }
    verdict["timing"]["total_s"] = round(time.monotonic() - t_start, 3)

    return verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json")
    ap.add_argument("--vendor", default=VENDOR)
    args = ap.parse_args()

    if not os.path.isdir(args.artifact):
        sys.exit(f"not an artifact dir: {args.artifact}")
    for f in ("index.html", "artist.json"):
        if not os.path.isfile(os.path.join(args.artifact, f)):
            sys.exit(f"artifact missing {f}")

    verdict_static = {"g4_provenance": {"pass": True, "problems": []}}
    names = registry_names(args.vendor)
    manifest = json.load(open(os.path.join(args.artifact, "artist.json")))
    probs = verdict_static["g4_provenance"]["problems"]
    if not manifest.get("effects"):
        probs.append("artist.json has no effects")
    for fx in manifest.get("effects", []):
        if fx.get("type") not in names:
            probs.append(f"type not in registry: {fx.get('type')}")
        if not isinstance(fx.get("region"), str):
            probs.append(f"bad region for {fx.get('type')}")
        elif not os.path.isfile(os.path.join(args.artifact, "index.html")):
            probs.append("no index.html")
    for hit in scan_tokens(args.artifact):
        probs.append(f"forbidden token: {hit}")
    if probs:
        verdict_static["g4_provenance"]["pass"] = False

    scratch = tempfile.mkdtemp(prefix="sg-artifact.")
    try:
        for f in os.listdir(args.artifact):
            src = os.path.join(args.artifact, f)
            if os.path.isfile(src):
                shutil.copy2(src, scratch)
        verdict = asyncio.run(grade(scratch, args.seed, args.vendor))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    verdict["gates"]["g4_provenance"] = verdict_static["g4_provenance"]
    # order gates g1..g6 for readability
    order = ["g1_page_and_probes", "g2_nonblank", "g3_animation",
             "g4_provenance", "g5_layout", "g6_performance"]
    verdict["gates"] = {k: verdict["gates"][k] for k in order}
    verdict["pass"] = all(g["pass"] for g in verdict["gates"].values())

    out = json.dumps(verdict, indent=2, sort_keys=True)
    if args.json:
        open(args.json, "w").write(out + "\n")
    print(out)
    sys.exit(0 if verdict["pass"] else 1)


if __name__ == "__main__":
    main()
