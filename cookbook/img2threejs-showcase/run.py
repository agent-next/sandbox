"""Build img2threejs-showcase at a pinned SHA in an agent-next sandbox and render every demo.

usage: SBX_API_KEY=<your key> python run.py [--shards N] [--only ID ...] [--out DIR] [--keep]
Needs the sbx CLI package installed (it brings the e2b SDK and ensure_template).
The pipeline runs detached inside the sandbox (pipeline.sh); this driver only polls and downloads,
so no single HTTP stream has to outlive a 20-minute render.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx
from e2b import Sandbox
from sbx import runners

SHA = "5b3078e92959b86c0dee18742d84473ef0a385c9"
IMAGE = "docker.io/library/node:22-bookworm"  # template builds accept docker.io; chromium is installed in-sandbox
SIZE = "standard"  # 4 vCPU / 16 GB; the default 3 GB shape OOMs in vite/esbuild
HERE = Path(__file__).resolve().parent
DEADLINE_S = 5400
EXTRA_PAGES = ["greenvale.html", "iphone-duo.html"]


def log(msg: str, shard: int | None = None) -> None:
    tag = "" if shard is None else f"[s{shard}] "
    print(f"[{datetime.now(timezone.utc):%H:%M:%SZ}] {tag}{msg}", flush=True)


def sh(sbx: Sandbox, cmd: str) -> str:
    return sbx.commands.run(cmd, timeout=60, request_timeout=90).stdout


def confirm_gone(sandbox_id: str) -> None:
    """A kill reply is not proof: the sandbox must answer 404 before the run calls it gone."""
    url = f"https://api.{os.environ['E2B_DOMAIN']}/sandboxes/{sandbox_id}"
    for delay in (0, 2, 5, 10):
        time.sleep(delay)
        try:
            if httpx.get(url, headers={"X-API-Key": os.environ["E2B_API_KEY"]}, timeout=30).status_code == 404:
                return
        except httpx.HTTPError:
            pass
    raise RuntimeError(f"could not confirm sandbox {sandbox_id} is gone; run: sbx kill {sandbox_id}")


def demo_ids() -> list[str]:
    """Registered demo routes at the pinned SHA, in registry order."""
    src = subprocess.run(["gh", "api", f"repos/img2threejs/img2threejs-showcase/contents/src/demos/registry.ts?ref={SHA}",
                          "-H", "Accept: application/vnd.github.raw"], check=True, capture_output=True, text=True).stdout
    return re.findall(r"^    id: '([^']+)'", src, re.M)


def run_shard(k: int, targets: list[str], template: str, out: Path, keep: bool) -> str:
    out.mkdir(parents=True, exist_ok=True)
    sbx = Sandbox.create(template, timeout=DEADLINE_S + 3600)  # room for a slow download after the run
    log(f"sandbox {sbx.sandbox_id} targets {' '.join(targets)}", k)
    status = "unknown"
    try:
        for name in ("pipeline.sh", "render_all.cjs"):
            sbx.files.write(f"/w/{'r/' if name.endswith('.cjs') else ''}{name}", (HERE / name).read_text())
        for ctl in sorted((HERE / "controls").glob("*.html")):
            sbx.files.write(f"/w/controls/{ctl.name}", ctl.read_text())
        sh(sbx, f"cd /w && (setsid nohup bash pipeline.sh {SHA} {' '.join(targets)} > /w/pipeline.log 2>&1 &)")
        start, last = time.monotonic(), ""
        while time.monotonic() - start < DEADLINE_S:
            time.sleep(30)
            try:
                status = sh(sbx, "cat /w/status 2>/dev/null").strip()
                rendered = sh(sbx, "wc -l < /w/out/render.log 2>/dev/null || echo 0").strip()
            except Exception as exc:  # one lost poll is not a lost run
                log(f"poll error {exc!r}", k)
                continue
            line = f"status {status} rendered {rendered}"
            if line != last:
                log(line, k)
                last = line
            if status == "done" or status.startswith("failed"):
                break
        # Download in child processes (a large read blocks the shared in-process client): verdicts,
        # logs and screenshots first, videos second. A failed download leaves the sandbox up.
        for mode in ("--no-video", "--video-only"):
            try:
                fetch = subprocess.run([sys.executable, str(HERE / "fetch_out.py"), sbx.sandbox_id, str(out), mode],
                                       capture_output=True, text=True, timeout=4000)
            except subprocess.TimeoutExpired:
                log(f"download {mode} timed out", k)
                keep, status = True, f"failed:download{mode}"
                continue
            log(f"download {mode} exit {fetch.returncode}: {(fetch.stdout + fetch.stderr).strip().splitlines()[-1:]}", k)
            if fetch.returncode:
                keep, status = True, f"failed:download{mode}"
        return status
    finally:
        if keep:
            log(f"kept sandbox {sbx.sandbox_id}", k)
        else:
            sbx.kill()
            confirm_gone(sbx.sandbox_id)
            log(f"killed sandbox {sbx.sandbox_id} (confirmed gone)", k)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=f"img2threejs-showcase-{datetime.now():%Y%m%d_%H%M%S}")
    ap.add_argument("--shards", type=int, default=8)
    ap.add_argument("--only", nargs="*", help="render just these targets")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)
    key = os.environ.get("E2B_API_KEY") or os.environ["SBX_API_KEY"]
    os.environ["E2B_API_KEY"] = key
    domain = os.environ.setdefault("E2B_DOMAIN", "sbx.agent-next.com")

    targets = args.only or demo_ids() + EXTRA_PAGES
    log(f"{len(targets)} targets over {args.shards} shards")
    with httpx.Client(base_url=f"https://api.{domain}", headers={"X-API-Key": key}, timeout=60) as api:
        template = runners.ensure_template(api, image=IMAGE, size=SIZE)
    log(f"template {template}")
    shards = [targets[k::args.shards] for k in range(args.shards) if targets[k::args.shards]]
    with ThreadPoolExecutor(len(shards)) as pool:
        futures = [pool.submit(run_shard, k, t, template, out / f"shard-{k}", args.keep) for k, t in enumerate(shards)]
        statuses = []
        for k, f in enumerate(futures):
            try:
                statuses.append(f.result())
            except Exception as exc:
                log(f"shard crashed: {exc!r}", k)
                statuses.append(f"crashed:{exc!r}")

    results = []
    for res in sorted(out.glob("shard-*/out/results.json")):
        results += json.loads(res.read_text())
    (out / "results.json").write_text(json.dumps(results, indent=2))
    counts: dict[str, int] = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    log(f"shards {statuses}")
    log(f"{len(results)} results, verdicts {counts}")
    return 0 if all(s == "done" for s in statuses) else 1


if __name__ == "__main__":
    sys.exit(main())
