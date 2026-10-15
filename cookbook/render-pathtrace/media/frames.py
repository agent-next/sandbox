#!/usr/bin/env python3
"""Workstation side of the convergence frames: one GPU `browser` lease, always deleted.

Reuses run.py's verified dependency download, upload, exec and cleanup helpers.
Usage: SBX_API_KEY=<your key> python3 media/frames.py OUTPUT_DIR [--seed 17]
"""
import argparse
import io
import json
import os
from pathlib import Path
import re
import sys
import tarfile
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import run  # noqa: E402


def source():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for folder in ("judge", "examples"):
            for path in sorted((HERE.parent / folder).rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    tar.add(path, arcname=path.relative_to(HERE.parent))
        tar.add(HERE / "render_frames.py", arcname="media/render_frames.py")
    return buffer.getvalue()


def job(seed, wheel):
    wheel_env = (f'os.environ["SBX_RENDER_NUMPY_WHEEL"] = str(out/{wheel!r})\n'
                 if wheel else "")
    return run.isolate(f"""
import json, os, pathlib, subprocess, tarfile
out = pathlib.Path(OUTPUT_DIR)
job = out / "job"
job.mkdir(exist_ok=True)
with tarfile.open(out / "source.tgz") as tar:
    tar.extractall(job, filter="data")
os.environ.update(SBX_RENDER_BACKEND="gpu", SBX_RENDER_ARCHIVE=str(out/"mutracer-0.1.1.tgz"),
    PYTHONPATH="/tmp/.local/share/render-pathtrace/deps", PYTHONDONTWRITEBYTECODE="1")
{wheel_env}report["steps"] = []
for label, command in (("setup", ["sh", "judge/setup.sh"]),
                       ("frames", ["/opt/browser/bin/python", "media/render_frames.py",
                                   str(out), "{seed}"])):
    result = subprocess.run(command, cwd=job, capture_output=True, text=True, timeout=1800)
    (out/(label + ".log")).write_text(result.stdout + result.stderr)
    report["steps"].append({{"step": label, "exit": result.returncode}})
    if result.returncode:
        break
(out/"job-result.json").write_text(json.dumps({{"result": {{"ok": True, "report": report}}}})+"\\n")
""")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    key = os.environ.get("SBX_API_KEY") or os.environ["E2B_API_KEY"]
    args.output.mkdir(parents=True, exist_ok=False)
    uploads = run.dependencies()
    uploads["source.tgz"] = source()
    sid = None
    try:
        created = run.json_request(key, "POST", "/sandboxes", {
            "accel": {"template": "browser", "vram_gb": 2, "reserve": "exec"}})
        sid = created.get("sandboxID")
        if not isinstance(sid, str) or not re.fullmatch(r"gl-[A-Za-z0-9-]+", sid):
            sid = None
            raise RuntimeError("invalid GPU lease id; inspect your inventory")
        print(f"create: sandbox={sid}", flush=True)
        probe = run.execute(key, sid, run.isolate(
            "try:\n    import numpy\n    report['image_numpy'] = numpy.__version__\n"
            "except ImportError:\n    report['image_numpy'] = None"))
        wheel = None
        if (probe.get("result") or {}).get("report", {}).get("image_numpy") != "2.2.6":
            wheel = run.WHEEL
            uploads[wheel] = run.numpy_wheel()
        for name, data in uploads.items():
            run.upload_part(key, sid, name, data)
            print(f"uploaded {name}: {len(data)} bytes", flush=True)
        result = run.execute(key, sid, job(args.seed, wheel)).get("result") or {}
        steps = result.get("report", {}).get("steps", [])
        print(json.dumps(steps), flush=True)
        files = run.json_request(key, "GET", f"/sandboxes/{sid}/files")["files"]
        for row in files:
            name = row["name"]
            path = run.safe_output(name)
            if len(path.parts) == 1 and (name.startswith("frame") or name.endswith(".log")):
                status, data = run.request(key, "GET",
                                           f"/sandboxes/{sid}/files/{quote(name, safe='')}")
                if status != 200:
                    raise RuntimeError(f"download {name}: HTTP {status}")
                (args.output / name).write_bytes(data)
        if result.get("ok") is not True or not steps or any(row["exit"] for row in steps):
            raise RuntimeError(f"frames job failed; see logs in {args.output}")
    finally:
        if sid:
            try:
                run.request(key, "DELETE", f"/sandboxes/{sid}")
            except Exception:
                print(f"DELETE reply lost for {sid}; confirming with GET", flush=True)
            try:
                status, _ = run.request(key, "GET", f"/sandboxes/{sid}")
            except Exception as exc:
                raise RuntimeError(f"cleanup unconfirmed for {sid}") from exc
            if status != 404:
                raise RuntimeError(f"cleanup unconfirmed for {sid}: GET HTTP {status}")
            print(f"cleanup confirmed: {sid}; GET 404", flush=True)


if __name__ == "__main__":
    main()
