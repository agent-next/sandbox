#!/usr/bin/env python3
"""Standard-library-only workstation runner; all rendering happens remotely."""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import time
import tarfile
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

API = "https://api.sbx.agent-next.com"
HERE = Path(__file__).resolve().parent
MUTRACER_URL = "https://registry.npmjs.org/@meimu/mutracer/-/mutracer-0.1.1.tgz"
MUTRACER_SHA256 = "a84ec7913ae95e49b1172ea0cba45f20179f4a5d0cce08768d4812348e3e7b4a"
MUTRACER_SHA512 = "iSqsI9GppKGPfDM7ntmZp5JZZjsIubh+aHVvyW516qTf2Hp64FPNzQwZIkF1LOA6aEk2JAisHBFAnpKUINyBBA=="
NUMPY_SHA256 = "fd83c01228a688733f1ded5201c678f0c53ecc1006ffbc404db9f7a899ac6249"
WHEEL = "numpy-2.2.6-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
CREATE_ATTEMPTS = 3
CREATE_MAX_WAIT_S = 30
DOWNLOAD_STALL_TIMEOUT_S = 120


def download(url):
    with urlopen(url, timeout=120) as response:
        return response.read()


def dependencies():
    cache = Path.home() / ".cache/render-pathtrace"
    cache.mkdir(parents=True, exist_ok=True)
    print("fetching pinned MuTracer 0.1.1", flush=True)
    cached_archive = cache / "mutracer-0.1.1.tgz"
    archive = cached_archive.read_bytes() if cached_archive.exists() else download(MUTRACER_URL)
    assert hashlib.sha256(archive).hexdigest() == MUTRACER_SHA256, "MuTracer SHA-256"
    assert base64.b64encode(hashlib.sha512(archive).digest()).decode() == MUTRACER_SHA512, \
        "MuTracer npm integrity"
    cached_archive.write_bytes(archive)
    return {"mutracer-0.1.1.tgz": archive}


def numpy_wheel():
    """Only for GPU images that predate the baked-in NumPy 2.2.6."""
    cache = Path.home() / ".cache/render-pathtrace"
    print("fetching pinned NumPy 2.2.6 wheel", flush=True)
    cached_wheel = cache / WHEEL
    if cached_wheel.exists():
        data = cached_wheel.read_bytes()
    else:
        metadata = json.loads(download("https://pypi.org/pypi/numpy/2.2.6/json"))
        wheel = next(row for row in metadata["urls"] if row["filename"] == WHEEL)
        data = download(wheel["url"])
    assert hashlib.sha256(data).hexdigest() == NUMPY_SHA256, "NumPy SHA-256"
    cached_wheel.write_bytes(data)
    return data


def request(key, method, path, body=None, timeout=3700):
    headers = {"X-API-Key": key}
    if isinstance(body, dict):
        body = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = Request(API + path, data=body, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def json_request(key, method, path, body=None):
    status, data = request(key, method, path, body)
    if status not in (200, 201):
        raise RuntimeError(f"{method} {path}: HTTP {status}")
    return json.loads(data)


def create_lease(key, body):
    """POST /sandboxes, honoring the gateway's 409 retry_after_s hint (#55)."""
    for attempt in range(CREATE_ATTEMPTS):
        status, data = request(key, "POST", "/sandboxes", body)
        if status in (200, 201):
            return json.loads(data)
        if status != 409:
            raise RuntimeError(f"POST /sandboxes: HTTP {status}")
        try:
            reply = json.loads(data)
        except ValueError:
            reply = None
        try:
            wait = float(reply.get("retry_after_s", 0)) if isinstance(reply, dict) else 0.0
        except (TypeError, ValueError):
            wait = 0.0
        hint = f"retry in {wait:g}s" if wait else "retry later"
        if attempt == CREATE_ATTEMPTS - 1:
            raise RuntimeError(f"POST /sandboxes: HTTP 409 after {CREATE_ATTEMPTS} attempts"
                               f" ({hint}); free a sandbox slot and rerun")
        wait = min(wait if wait > 0 else 1, CREATE_MAX_WAIT_S)
        print(f"create: HTTP 409 ({hint}); retrying in {wait:g}s", flush=True)
        time.sleep(wait)
    raise RuntimeError("unreachable")


def source_archive():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for folder in ("judge", "examples"):
            for path in sorted((HERE / folder).rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    tar.add(path, arcname=path.relative_to(HERE))
        for name in ("run.py", "test_runner.py"):
            path = HERE / name
            if path.exists():
                tar.add(path, arcname=name)
    return buffer.getvalue()


def isolate(code):
    # The worker reserves x as its state canary; job locals must not replace it.
    return f"exec({code!r}, {{'OUTPUT_DIR': OUTPUT_DIR, 'report': report}})"


def job_source(seed, wheel, skip_selftest=False, chunks=None):
    wheel_env = (f'os.environ["SBX_RENDER_NUMPY_WHEEL"] = str(out/{wheel!r})\n'
                 if wheel else "")
    code = f"""
import hashlib, json, os, pathlib, subprocess, tarfile, time
out = pathlib.Path(OUTPUT_DIR)
for name, count in {chunks or {}!r}.items():
    with (out/name).open("wb") as stream:
        for index in range(count):
            part = out/(name + ".part-%04d" % index)
            stream.write(part.read_bytes())
            part.unlink()
job = out / "job"
job.mkdir(exist_ok=True)
with tarfile.open(out / "source.tgz") as tar:
    tar.extractall(job, filter="data")
report["input_sha256"] = {{
    str(path.relative_to(job)): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(job.rglob("*")) if path.is_file()
}}
os.environ.update(SBX_RENDER_BACKEND="gpu",
    SBX_RENDER_ARCHIVE=str(out/"mutracer-0.1.1.tgz"),
    PYTHONPATH="/tmp/.local/share/render-pathtrace/deps",
    PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
{wheel_env}steps = [
    ("setup", ["sh", "judge/setup.sh"], 180),
    ("unit", ["/opt/browser/bin/python", "-m", "unittest", "discover", "-s", "judge", "-p", "test_contract.py"], 60),
    ("runner_unit", ["/opt/browser/bin/python", "-m", "unittest", "test_runner"], 60),
]
if not {skip_selftest!r}:
    steps.append(("selftest", ["sh", "judge/selftest.sh", "--backend", "gpu", "--seed", "{seed}"], 2400))
steps.append(("grade", ["sh", "judge/grade.sh", "examples/good/scene.json",
    "--backend", "gpu", "--seed", "{seed}", "--json", str(out/"verdict.json"),
    "--hdr-out", str(out/"studio.npy")], 630))
report["steps"] = []
for label, command, budget in steps:
    start = time.monotonic()
    result = subprocess.run(command, cwd=job, capture_output=True, text=True, timeout=budget)
    (out/(label+".log")).write_text(result.stdout + result.stderr)
    row = {{"step": label, "exit": result.returncode, "seconds": round(time.monotonic()-start, 3)}}
    report["steps"].append(row)
    print(json.dumps(row), flush=True)
    if label == "selftest" and result.stdout.strip():
        (out/"selftest.json").write_text(result.stdout.strip().splitlines()[-1]+"\\n")
    if label == "setup":
        versions = job/"judge/VERSIONS.txt"
        if versions.exists():
            (out/"VERSIONS.txt").write_bytes(versions.read_bytes())
    if result.returncode:
        break
(out/"steps.json").write_text(json.dumps(report["steps"], sort_keys=True)+"\\n")
(out/"job-result.json").write_text(json.dumps({{"result": {{"ok": True, "report": report}}}})+"\\n")
"""
    return isolate(code)


def execute(key, sid, code):
    """Never replay a possibly running exec after a dropped HTTP response."""
    started = time.monotonic()
    try:
        status, data = request(key, "POST", f"/sandboxes/{sid}/exec",
                               {"code": code, "timeout_s": 3500})
        if status == 200:
            return json.loads(data)
        if status not in (502, 503, 504, 524):
            try:
                detail = json.loads(data).get("message", "")
            except ValueError:
                detail = ""
            raise RuntimeError(f"GPU exec: HTTP {status}: {detail}")
    except (OSError, TimeoutError):
        pass
    print("exec reply lost; waiting for the existing job, not replaying it", flush=True)
    while time.monotonic() - started < 3550:
        status, data = request(key, "GET", f"/sandboxes/{sid}/files/job-result.json")
        if status == 200:
            return json.loads(data)
        state, _ = request(key, "GET", f"/sandboxes/{sid}")
        if state == 404:
            raise RuntimeError(f"GPU lease {sid} disappeared during execution")
        time.sleep(5)
    raise RuntimeError(f"GPU job result unavailable for {sid} after its deadline")


def safe_output(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name:
        raise RuntimeError("unsafe artifact name")
    return path


def upload_part(key, sid, name, data, via_exec=False):
    for attempt in range(5):
        try:
            if via_exec:
                encoded = base64.b64encode(data).decode()
                code = (f"from pathlib import Path\nimport base64\n"
                        f"report['uploaded_bytes'] = Path(OUTPUT_DIR, {name!r}).write_bytes("
                        f"base64.b64decode({encoded!r}))")
                status, raw = request(key, "POST", f"/sandboxes/{sid}/exec",
                                      {"code": isolate(code), "timeout_s": 60})
                if status == 200:
                    result = json.loads(raw).get("result") or {}
                    if result.get("ok") is True and result.get("report", {}).get("uploaded_bytes") == len(data):
                        return
            else:
                status, _ = request(key, "PUT",
                    f"/sandboxes/{sid}/files/out/{quote(name, safe='')}", data)
                if status in (200, 201):
                    return
            raise RuntimeError(f"upload {name}: HTTP {status}")
        except Exception:
            if attempt == 4:
                raise
            time.sleep(attempt + 1)


def gpu_run(args, key):
    if args.keep:
        raise RuntimeError("--keep is only available for the CPU diagnostic path")
    args.output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    uploads = dependencies()
    uploads["source.tgz"] = source_archive()
    print(f"dependencies: verified wall={time.monotonic()-start:.1f}s", flush=True)
    sid = None
    receipt = {"selftest_skipped": args.skip_selftest}
    try:
        created = create_lease(key, {"accel": {"template": "browser", "vram_gb": 2,
                                               "reserve": "exec"}})
        sid = created.get("sandboxID")
        if not isinstance(sid, str) or not re.fullmatch(r"gl-[A-Za-z0-9-]+", sid):
            sid = None
            raise RuntimeError("invalid GPU lease id; inspect your inventory")
        receipt["sandbox_id"] = sid
        print(f"create: sandbox={sid}", flush=True)
        # PUT names are workdir-relative; GET names are OUTPUT_DIR-relative.
        status, _ = request(key, "PUT", f"/sandboxes/{sid}/files/out/upload-probe", b"")
        if status not in (200, 201, 405):
            raise RuntimeError(f"upload capability probe: HTTP {status}")
        via_exec = status == 405
        receipt["upload_probe_status"] = status
        receipt["upload_method"] = "exec-base64" if via_exec else "PUT"
        print(f"upload method: {receipt['upload_method']} (PUT probe HTTP {status})", flush=True)
        probe = execute(key, sid, isolate(
            "try:\n    import numpy\n    report['image_numpy'] = numpy.__version__\n"
            "except ImportError:\n    report['image_numpy'] = None"))
        receipt["image_numpy"] = (probe.get("result") or {}).get("report", {}).get("image_numpy")
        wheel = None
        if receipt["image_numpy"] != "2.2.6":
            wheel = WHEEL
            uploads[WHEEL] = numpy_wheel()
        print(f"image NumPy: {receipt['image_numpy']}; wheel upload: {bool(wheel)}", flush=True)
        chunks = {}
        chunk_bytes = 1024 * 1024 if via_exec else 128 * 1024
        for name, data in uploads.items():
            count = (len(data) + chunk_bytes - 1) // chunk_bytes
            if count > 1:
                chunks[name] = count
            with ThreadPoolExecutor(max_workers=1 if via_exec else 4) as pool:
                futures = [
                    pool.submit(upload_part, key, sid,
                                name + f".part-{index:04d}" if count > 1 else name,
                                data[index*chunk_bytes:(index+1)*chunk_bytes], via_exec)
                    for index in range(count)
                ]
                for future in futures:
                    future.result()
            print(f"uploaded {name}: {len(data)} bytes in {count} parts", flush=True)
        print(f"upload: wall={time.monotonic()-start:.1f}s since start", flush=True)
        executed = execute(key, sid, job_source(args.seed, wheel, args.skip_selftest, chunks))
        receipt["exec"] = executed
        result = executed.get("result") or {}
        print(result.get("stdout", ""), end="", flush=True)
        files = json_request(key, "GET", f"/sandboxes/{sid}/files")["files"]
        allowed = {".json", ".log", ".npy", ".png", ".txt"}
        for row in files:
            name = row["name"]
            path = safe_output(name)
            if len(path.parts) != 1 or path.suffix not in allowed:
                continue
            for attempt in range(5):
                try:
                    status, data = request(key, "GET",
                        f"/sandboxes/{sid}/files/{quote(name, safe='')}",
                        timeout=DOWNLOAD_STALL_TIMEOUT_S)
                except (OSError, TimeoutError) as exc:
                    # a silent transfer must not hold a billing lease for hours (#55)
                    raise RuntimeError(
                        f"download {name}: stalled ({exc.__class__.__name__}) after"
                        f" {DOWNLOAD_STALL_TIMEOUT_S}s of silence; lease {sid} freed") from exc
                if status == 200:
                    break
                if status not in (404, 502, 503, 504) or attempt == 4:
                    raise RuntimeError(f"download {name}: HTTP {status}")
                time.sleep(attempt + 1)
            if "size" in row and len(data) != row["size"]:
                raise RuntimeError(f"download {name}: incomplete response")
            (args.output / name).write_bytes(data)
        verdict_path = args.output / "verdict.json"
        if verdict_path.exists():
            verdict = json.loads(verdict_path.read_text())
            print(json.dumps(verdict, sort_keys=True), flush=True)
        else:
            verdict = {"pass": False}
        steps = result.get("report", {}).get("steps", [])
        if result.get("ok") is not True or not steps or any(row["exit"] for row in steps):
            raise RuntimeError(f"GPU job failed; inspect logs in {args.output}")
        if not verdict.get("pass"):
            raise RuntimeError("grade did not pass")
        print(("GRADE PASS (development run; selftest skipped)" if args.skip_selftest else
               "PASS: selftest and five physical gates on NVIDIA WebGPU"), flush=True)
    finally:
        if sid:
            try:
                status, _ = request(key, "DELETE", f"/sandboxes/{sid}")
                receipt["delete_status"] = status
            except Exception:
                receipt["delete_status"] = "reply lost"
            try:
                status, _ = request(key, "GET", f"/sandboxes/{sid}")
                receipt["cleanup_get_status"] = status
                if status != 404:
                    raise RuntimeError(f"GET HTTP {status}")
                print(f"cleanup confirmed: {sid}; DELETE {receipt['delete_status']}; GET 404",
                      flush=True)
            except Exception as exc:
                raise RuntimeError(f"cleanup unconfirmed for {sid}") from exc
            finally:
                receipt["wall_seconds"] = round(time.monotonic()-start, 3)
                (args.output / "runner.json").write_text(json.dumps(receipt, indent=2)+"\n")
        print(f"total wall={time.monotonic()-start:.3f}s", flush=True)


def sbx(*args):
    result = subprocess.run(["sbx", *args], text=True, capture_output=True, timeout=150)
    if result.returncode:
        raise RuntimeError(f"sbx {args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def remote_step(sid, label, command, budget):
    start = time.monotonic()
    prefix = "/tmp/pathtrace-" + secrets.token_hex(6)
    job = (f"{command}; code=$?; printf '%s' \"$code\" > {prefix}.exit")
    launch = f"nohup sh -c {shlex.quote(job)} >{prefix}.log 2>&1 </dev/null &"
    sbx("exec", sid, "--timeout", "120", launch)
    probe = (
        "import json,pathlib; "
        f"p=pathlib.Path({prefix!r}); e=pathlib.Path(str(p)+'.exit'); "
        "print(json.dumps({'done':e.exists(),"
        "'code':int(e.read_text()) if e.exists() else None,"
        "'log':pathlib.Path(str(p)+'.log').read_text() if e.exists() else ''}))"
    )
    while time.monotonic() - start < budget:
        state = json.loads(sbx("exec", sid, "--timeout", "120",
                               "python3 -c " + shlex.quote(probe)))
        if state["done"]:
            print(state["log"], flush=True)
            print(f"{label}: exit={state['code']} wall={time.monotonic()-start:.1f}s",
                  flush=True)
            if state["code"]:
                raise RuntimeError(f"{label} failed in sandbox {sid}")
            return state["log"]
        time.sleep(3)
    raise RuntimeError(f"{label} exceeded {budget}s in sandbox {sid}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="main")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--backend", choices=("gpu", "cpu"), default="gpu")
    parser.add_argument("--output", type=Path,
                        default=HERE / ("outputs-" + time.strftime("%Y%m%d-%H%M%S")))
    parser.add_argument("--skip-selftest", action="store_true",
                        help="development only; not a full acceptance run")
    args = parser.parse_args()
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        parser.error("set SBX_API_KEY or E2B_API_KEY")
    if not 0 <= args.seed < 32000:
        parser.error("--seed must be in [0, 32000)")
    if args.backend == "gpu":
        try:
            gpu_run(args, os.environ.get("SBX_API_KEY") or os.environ["E2B_API_KEY"])
            return 0
        except (Exception, KeyboardInterrupt) as exc:
            message = str(exc)
            for name in ("SBX_API_KEY", "E2B_API_KEY"):
                if os.environ.get(name):
                    message = message.replace(os.environ[name], "[redacted]")
            print(message, file=sys.stderr)
            return 1
    if not shutil.which("sbx"):
        parser.error("install the sbx CLI first; see README.md")
    sid = None
    failed = False
    try:
        start = time.monotonic()
        sid = sbx("create", "--timeout-min", "30")
        if not sid or len(sid.split()) != 1:
            raise RuntimeError(f"invalid sandbox id: {sid!r}")
        print(f"create: sandbox={sid} wall={time.monotonic()-start:.1f}s", flush=True)
        remote_step(sid, "clone",
                    "git clone --depth 1 -b " + shlex.quote(args.ref)
                    + " https://github.com/agent-next/sandbox /tmp/pathtrace-repo", 180)
        directory = "/tmp/pathtrace-repo/cookbook/render-pathtrace"
        prefix = "cd " + directory + " && "
        remote_step(sid, "setup", prefix + "sh judge/setup.sh", 300)
        remote_step(sid, "selftest", prefix + f"sh judge/selftest.sh --seed {args.seed}", 2400)
        output = remote_step(sid, "grade", prefix +
                             f"sh judge/grade.sh examples/good/scene.json --seed {args.seed}",
                             630)
        verdict = json.loads(output.strip().splitlines()[-1])
        if not verdict["pass"]:
            raise RuntimeError("grade did not pass")
        print(f"PASS: five gates; backend={verdict['backend']}; "
              f"adapter={verdict['adapter']}", flush=True)
    except (Exception, KeyboardInterrupt) as exc:
        failed = True
        print(str(exc), file=sys.stderr)
    finally:
        if sid:
            if args.keep:
                print(f"Kept sandbox: {sid}", flush=True)
            else:
                try:
                    sbx("kill", sid)
                    inventory = sbx("list")
                    ids = {line.split()[0] for line in inventory.splitlines() if line.strip()}
                    if sid in ids:
                        raise RuntimeError("id still present in sbx list")
                    print(f"cleanup confirmed: {sid}", flush=True)
                except Exception as exc:
                    failed = True
                    print(f"cleanup unconfirmed for sandbox {sid}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
