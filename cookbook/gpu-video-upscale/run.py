#!/usr/bin/env python3
"""gpu-video-upscale demo: one command, one disposable sandbox, one verdict.

Creates an agent-next sandbox, clones this repository inside it, installs
the pinned judge toolchain (downloading and sha256-verifying the 67 MB
Real-ESRGAN x4plus checkpoint), runs the judge self-test, then grades the
known-good artifact — and always kills the sandbox afterwards.

    python3 cookbook/gpu-video-upscale/run.py [--ref main] [--keep] [--gpu]

Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

--gpu additionally runs the demo's heavy step for real: an 8 GiB VRAM
slice lease is created over the REST API (the cookbook/small-gpu/run.py
pattern), the pinned weights, the clip and the artifact are uploaded from
this machine in chunks (the lease has no internet), 150 frames of 1080p
run through the network on the GPU, PSNR/SSIM against the judge's own
bicubic baseline are measured on-device, and the lease is destroyed in a
finally block and confirmed gone. The gates themselves are always decided
by the CPU judge, so anyone can grade an artifact.

Standard library only. Wall time is printed per step.
"""

import argparse
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/gpu-video-upscale"
# sbx exec's default timeout is 60 s; every step below needs more. setup
# downloads the 67 MB checkpoint plus the pinned torch CPU closure;
# selftest grades the good artifact and 8 mutants, each a full judge run.
STEP_TIMEOUTS = {
    "clone": 300,
    "setup": 2400,
    "selftest": 2400,
    "grade": 1200,
}

API = "https://api.sbx.agent-next.com"
PSNR_MARGIN_DB = 1.0


def die(msg, code=1):
    print(f"run.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def need_sbx():
    if not shutil.which("sbx"):
        die("sbx CLI not found: pip install "
            "'git+https://github.com/agent-next/sandbox#subdirectory=cli'")
    if not (os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")):
        die("no API key: export SBX_API_KEY (or E2B_API_KEY)")


def run(step, *args, timeout=None, capture=False):
    t0 = time.monotonic()
    proc = subprocess.run(
        args, capture_output=capture, text=True,
        timeout=timeout and timeout + 30)
    dt = time.monotonic() - t0
    status = "ok" if proc.returncode == 0 else f"exit {proc.returncode}"
    print(f"  [{step}] {' '.join(args[:3])} ... {status} "
          f"({dt:.0f} s)", flush=True)
    return proc, dt


def request(key, method, path, body=None, timeout=900):
    """Make an HTTP request to the agent-next sandbox API."""
    data = None if body is None else json.dumps(body).encode()
    req = Request(API + path, data=data, method=method,
                  headers={"X-API-Key": key, "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        return exc.code, None


# ---------------------------------------------------------------- verdict --

def verdict_ok(verdict):
    gates = verdict.get("gates", {})
    return (bool(gates)
            and all(g.get("pass") for g in gates.values())
            and verdict.get("judge_intact", False))


def print_verdict(verdict):
    gates = verdict.get("gates", {})
    ok = verdict_ok(verdict)
    print(f"\ngpu-video-upscale demo: {'PASS' if ok else 'FAIL'}")
    for name, g in sorted(gates.items()):
        note = ""
        if name == "correctness" and isinstance(g, dict):
            frames = g.get("frames") or []
            note = f" ({len(frames)} frames, crop {g.get('crop')})"
        print(f"  gate {name}: {'pass' if g.get('pass') else 'FAIL'}{note}")
    corr = gates.get("correctness") or {}
    for f in corr.get("frames") or []:
        if "error" in f:
            print(f"  frame {f['index']:4d}: ERROR {f['error']}")
            continue
        pm = f.get("psnr_model")
        pm_s = "inf" if pm is None else f"{pm:.2f}"
        print(f"  frame {f['index']:4d}: psnr {pm_s} dB vs bicubic "
              f"{f.get('psnr_bicubic', float('nan')):.2f} dB "
              f"({f.get('psnr_margin', 0):+.2f} dB), "
              f"ssim {f.get('ssim_model', 0):.4f} vs "
              f"{f.get('ssim_bicubic', 0):.4f} "
              f"({f.get('ssim_margin', 0):+.4f})")
    worst = corr.get("worst") or {}
    if worst.get("psnr_margin") is not None:
        print(f"  worst psnr margin {worst['psnr_margin']:+.2f} dB "
              f"(need >= +{PSNR_MARGIN_DB:.2f} on every frame)")
    if worst.get("ssim_margin") is not None:
        print(f"  worst ssim margin {worst['ssim_margin']:+.4f}")
    return ok


# -------------------------------------------------------------- CPU judge --

def run_cpu_path(args):
    create = ["sbx", "create", "--timeout-min", "30"]
    proc, _ = run("create", *create, timeout=120, capture=True)
    if proc.returncode != 0:
        die(f"sbx create failed: {proc.stderr.strip()}")
    sbx_id = proc.stdout.strip().splitlines()[-1]
    print(f"sandbox: {sbx_id} (template default)")

    verdict = None
    try:
        def exec_step(name, cmd):
            proc, _ = run(name, "sbx", "exec", sbx_id,
                          "--timeout", str(STEP_TIMEOUTS[name]), "--", *cmd)
            if proc.returncode != 0:
                die(f"step {name} failed in sandbox {sbx_id} "
                    f"(exit {proc.returncode})")
            return proc

        exec_step("clone", [
            "git", "clone", "--depth", "1", "-b", args.ref, REPO, "sandbox"])
        exec_step("setup", [
            "bash", f"sandbox/{DEMO_DIR}/judge/setup.sh"])
        exec_step("selftest", [
            "bash", f"sandbox/{DEMO_DIR}/judge/selftest.sh"])
        exec_step("grade", [
            "bash", f"sandbox/{DEMO_DIR}/judge/grade.sh",
            f"sandbox/{DEMO_DIR}/examples/good/upscale.py",
            "--json", "/tmp/verdict.json"])

        # pull the verdict back for the local summary
        proc, _ = run("cat", "sbx", "exec", sbx_id, "--timeout", "60",
                      "--", "cat", "/tmp/verdict.json", capture=True)
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                verdict = json.loads(proc.stdout)
            except json.JSONDecodeError:
                pass
    finally:
        if args.keep:
            print(f"run.py: --keep: sandbox {sbx_id} left running; "
                  "kill it with: sbx kill " + sbx_id)
        else:
            run("kill", "sbx", "kill", sbx_id, timeout=120)
            proc, _ = run("list", "sbx", "list", timeout=60, capture=True)
            if sbx_id in (proc.stdout or ""):
                die(f"cleanup not confirmed: sandbox {sbx_id} still live; "
                    "kill it with: sbx kill " + sbx_id)
            print(f"cleanup: sandbox {sbx_id} killed and confirmed gone")

    if verdict is None:
        die("no verdict JSON returned from the sandbox")
    return verdict


# ----------------------------------------------------------------- GPU lane --

GPU_JOB = r"""
import base64, importlib.util as ilu, io, json, os, tarfile, tempfile, time

root = tempfile.mkdtemp(prefix='gvu-')
tarfile.open('/tmp/gvu_payload.tar.gz').extractall(root)
os.chdir(root)

import torch
assert torch.cuda.is_available(), 'CUDA unavailable on the GPU lease'

# the judge's own metric/downscale helpers, so the GPU lane measures with
# the same definitions the CPU gates use
spec = ilu.spec_from_file_location('judge_grade',
                                   os.path.join(root, 'judge', '_grade.py'))
judge = ilu.module_from_spec(spec)
spec.loader.exec_module(judge)

spec = ilu.spec_from_file_location('artifact',
                                   os.path.join(root, 'upscale.py'))
art = ilu.module_from_spec(spec)
spec.loader.exec_module(art)
if hasattr(art, 'WEIGHTS_PATH'):
    art.WEIGHTS_PATH = os.path.join(root, 'RealESRGAN_x4plus.pth')
model = art.build_model().to('cuda')

CLIP = os.path.join(root, 'original.mp4')
geom = judge.clip_geometry(CLIP)
total = geom[2]
N = 150                      # 2.5 s at 60 fps
# the per-frame quality rows are measured on a wider sample than the
# timed stretch: frames 299/599 prove the margin holds beyond the
# measured window
QUALITY_IDX = [0, 75, 149, 299, 599]
report['clip'] = dict(w=geom[0], h=geom[1], total=total, frames_used=N)


def decode(i):
    # Frame i as (1,3,H,W) float32 [0,1]: one frame at a time in RAM.
    return judge.decode_frames(CLIP, [i], geom)


def quality_row(i, orig, out, bic):
    row = dict(index=i,
               psnr_model=judge.psnr(out, orig),
               psnr_bicubic=judge.psnr(bic, orig),
               ssim_model=judge.ssim(out, orig),
               ssim_bicubic=judge.ssim(bic, orig))
    row['psnr_margin'] = (None if row['psnr_model'] is None else
                          round(row['psnr_model'] - row['psnr_bicubic'], 4))
    row['ssim_margin'] = round(row['ssim_model'] - row['ssim_bicubic'], 5)
    return row


# ---- the heavy step: N frames of 1080p through the network -------------
torch.cuda.reset_peak_memory_stats()
rows = {}
quality_wall = 0.0
t0 = time.monotonic()
with torch.no_grad():
    for i in range(N):
        orig = decode(i).to('cuda')
        low = judge.downscale(orig)                 # (1,3,270,480)
        if i in QUALITY_IDX:
            tq = time.monotonic()
            out = art.upscale_frames(model, low)
            quality_wall += time.monotonic() - tq
            rows[i] = quality_row(i, orig, out,
                                  judge.bicubic_baseline(low))
        else:
            art.upscale_frames(model, low)
    torch.cuda.synchronize()
wall = time.monotonic() - t0
report['gpu'] = dict(
    device=torch.cuda.get_device_name(0),
    torch=torch.__version__,
    frames=N, wall_s=round(wall, 2),
    fps=round(N / wall, 2),
    vram_gb=round(torch.cuda.max_memory_allocated() / 2**30, 2),
)

# wider sample beyond the timed stretch (still real frames of the clip)
with torch.no_grad():
    for i in (299, 599):
        if i in rows:
            continue
        orig = decode(i).to('cuda')
        low = judge.downscale(orig)
        rows[i] = quality_row(i, orig, art.upscale_frames(model, low),
                              judge.bicubic_baseline(low))
report['quality'] = [rows[i] for i in sorted(rows)]
worst = min((r['psnr_margin'] for r in report['quality']
             if r['psnr_margin'] is not None), default=None)
report['worst_psnr_margin'] = worst

# ---- measured crops (orig / bicubic / model) for the demo figures ------
# 272x480 centre crops (272 = 4*68 keeps the x4 geometry exact); small
# enough to travel back inside the report JSON
import numpy as np
crops_b64 = {}
try:
    from PIL import Image
    for tag, i in (('f149', 149), ('f299', 299)):
        orig = decode(i)
        low = judge.downscale(orig)
        with torch.no_grad():
            out = art.upscale_frames(model, low).cpu()
        bic = judge.bicubic_baseline(low).cpu()
        for name, img in (('orig', orig), ('bicubic', bic), ('model', out)):
            q = judge.quant8(img)[0, :, 404:676, 720:1200]
            arr = (q.permute(1, 2, 0).numpy() * 255).astype(np.uint8)
            buf = io.BytesIO()
            Image.fromarray(arr).save(buf, format='PNG', optimize=True)
            crops_b64[f'{tag}_{name}'] = base64.b64encode(
                buf.getvalue()).decode('ascii')
except ImportError:
    report['crops_note'] = 'PIL unavailable on the lease; no crops'
report['crops_b64'] = crops_b64
print('gpu job done')
"""

CHUNK = 4 * 1024 * 1024  # base64 bytes per upload exec


def gpu_upload(key, sid, payload_b64):
    """Upload the base64 payload to the lease in chunks.

    The lease has no internet, so everything it needs is shipped from here.
    One exec per ~4 MiB of base64 keeps each request body small enough for
    the exec endpoint; the payload is assembled by appending.
    """
    total = (len(payload_b64) + CHUNK - 1) // CHUNK
    print(f"uploading {len(payload_b64) / 2**20:.0f} MiB (base64) "
          f"in {total} chunks...", flush=True)
    t0 = time.monotonic()
    for i in range(total):
        part = payload_b64[i * CHUNK:(i + 1) * CHUNK]
        code = ("open('/tmp/gvu_payload.b64', 'ab')"
                f".write({part!r}.encode('ascii'))")
        st, executed = request(key, "POST", f"/sandboxes/{sid}/exec",
                               {"code": code, "timeout_s": 120})
        ok = (st == 200 and isinstance(executed, dict)
              and (executed.get("result") or {}).get("ok") is True)
        if not ok:
            raise RuntimeError(f"upload chunk {i + 1}/{total}: HTTP {st}")
        if (i + 1) % 5 == 0 or i + 1 == total:
            print(f"  chunk {i + 1}/{total}", flush=True)
    print(f"upload done in {time.monotonic() - t0:.0f} s", flush=True)
    st, executed = request(key, "POST", f"/sandboxes/{sid}/exec", {
        "code": ("import base64\n"
                 "open('/tmp/gvu_payload.tar.gz', 'wb').write("
                 "base64.b64decode(open('/tmp/gvu_payload.b64').read()))\n"
                 "import os; print(os.path.getsize"
                 "('/tmp/gvu_payload.tar.gz'))"),
        "timeout_s": 300,
    })
    ok = (st == 200 and isinstance(executed, dict)
          and (executed.get("result") or {}).get("ok") is True)
    if not ok:
        raise RuntimeError(f"payload decode: HTTP {st}")
    print(executed.get("result", {}).get("stdout", "").strip() + " bytes on lease")


def pack_payload(demo_path):
    """judge/, the artifact, the clip and the pinned weights as tar.gz bytes."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        tf.add(os.path.join(demo_path, "judge"), arcname="judge")
        tf.add(os.path.join(demo_path, "examples", "good", "upscale.py"),
               arcname="upscale.py")
        tf.add(os.path.join(demo_path, "data", "clip", "original.mp4"),
               arcname="original.mp4")
        weights = os.path.join(demo_path, "data", "weights",
                               "RealESRGAN_x4plus.pth")
        if not os.path.isfile(weights):
            raise RuntimeError(
                f"pinned weights not found at {weights}; run "
                "judge/setup.sh once on this machine first (it downloads "
                "and verifies them)")
        tf.add(weights, arcname="RealESRGAN_x4plus.pth")
    return buf.getvalue()


def destroy_and_confirm(key, sid):
    """DELETE the lease and confirm it is gone; returns an error string or
    None. Never raises, so it can run while another error is in flight
    without hiding it."""
    print(f"destroying {sid}...", flush=True)
    try:
        request(key, "DELETE", f"/sandboxes/{sid}")
    except Exception as exc:
        print(f"run.py: DELETE {sid} raised {exc}; verifying anyway", file=sys.stderr)
    try:
        st, remaining = request(key, "GET", f"/sandboxes/{sid}")
    except Exception as exc:
        return (f"cleanup unconfirmed for {sid} ({exc}); run "
                "sandbox_kill for this id")
    if st != 404 and not (
        st == 200 and isinstance(remaining, dict)
        and remaining.get("phase") == "dead"
    ):
        return (f"cleanup unconfirmed for {sid}: HTTP {st}; run "
                "sandbox_kill for this id")
    print(f"destroyed {sid}; verified absent or dead", flush=True)
    return None


def run_gpu_lane(key, demo_path):
    """The heavy step on an 8 GiB VRAM slice lease (cookbook/small-gpu pattern).

    Returns the lease's report dict. The lease is always destroyed and its
    disappearance confirmed; a cleanup failure keeps the identity of any
    in-flight error and adds its own. Only ids this run created are ever
    deleted.
    """
    import hashlib
    weights = os.path.join(demo_path, "data", "weights",
                           "RealESRGAN_x4plus.pth")
    if os.path.isfile(weights):
        digest = hashlib.sha256(open(weights, "rb").read()).hexdigest()
        want = "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"
        if digest != want:
            die(f"local weights sha256 {digest} != pinned; run "
                "judge/setup.sh to re-download")
    elif not os.path.isdir(os.path.join(demo_path, "judge")):
        die("demo tree incomplete; run from a checkout of this repository")

    print("create GPU lease (8 GiB VRAM slice)...", flush=True)
    st, created = request(key, "POST", "/sandboxes",
                          {"accel": {"vram_gb": 8, "reserve": "exec"}})
    if st != 201:
        die(f"GPU create: HTTP {st}; check GPU access, credit and capacity")
    sid = created["sandboxID"]
    if not isinstance(sid, str) or not sid.startswith("gl-") or not all(
        c.isascii() and (c.isalnum() or c == "-") for c in sid
    ):
        die(f"GPU create returned an unexpected lease id {sid!r}; it was not "
            "destroyed automatically, delete it with sandbox_kill")
    print(f"created {sid} (8 GiB VRAM slice)", flush=True)

    report, body_error = None, None
    try:
        payload = base64.b64encode(pack_payload(demo_path)).decode("ascii")
        gpu_upload(key, sid, payload)
        print("exec GPU inference job (150 frames)...", flush=True)
        st, executed = request(key, "POST", f"/sandboxes/{sid}/exec",
                               {"code": GPU_JOB, "timeout_s": 1800})
        if st != 200 or not isinstance(executed, dict):
            die(f"GPU exec: HTTP {st}")
        result = executed.get("result") or {}
        if result.get("ok") is not True:
            stderr = result.get("stderr", "")
            die(f"GPU job failed: {stderr[-800:]}")
        report = result.get("report") or {}
        if not report:
            die("GPU job returned no report")
    except BaseException as exc:
        body_error = exc

    cleanup_error = destroy_and_confirm(key, sid)
    if body_error is not None:
        if cleanup_error:
            print(f"run.py: {cleanup_error}", file=sys.stderr)
        raise body_error
    if cleanup_error:
        die(cleanup_error)

    gpu = report.get("gpu", {})
    print(f"\nGPU lane: {gpu.get('device')} ({gpu.get('torch')}), "
          f"{gpu.get('frames')} frames in {gpu.get('wall_s')} s "
          f"= {gpu.get('fps')} frames/s, "
          f"{gpu.get('vram_gb')} GiB peak VRAM")
    for r in report.get("quality", []):
        pm = r.get("psnr_model")
        pm_s = "inf" if pm is None else f"{pm:.2f}"
        print(f"  frame {r['index']:4d}: psnr {pm_s} dB vs bicubic "
              f"{r.get('psnr_bicubic', float('nan')):.2f} dB "
              f"({r.get('psnr_margin', 0):+.2f} dB), "
              f"ssim margin {r.get('ssim_margin', 0):+.4f}")
    worst = report.get("worst_psnr_margin")
    if worst is None:
        die("GPU lane measured no psnr margins")
    if worst < PSNR_MARGIN_DB:
        die(f"GPU lane: worst psnr margin {worst:+.2f} dB < "
            f"{PSNR_MARGIN_DB:.2f} dB")
    print(f"  worst psnr margin {worst:+.2f} dB (>= +{PSNR_MARGIN_DB:.2f})")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main",
                    help="repository ref to clone inside the sandbox")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox up and print its id")
    ap.add_argument("--gpu", action="store_true",
                    help="also run the heavy inference step on an 8 GiB "
                         "VRAM slice lease via the REST API (GPU access "
                         "required on your key)")
    ap.add_argument("--crops-out", metavar="DIR",
                    help="with --gpu: write the measured comparison crops "
                         "(PNG, orig/bicubic/model) downloaded from the "
                         "lease into DIR")
    args = ap.parse_args()
    if args.crops_out and not args.gpu:
        die("--crops-out only applies to the --gpu path")

    total0 = time.monotonic()
    need_sbx()
    verdict = run_cpu_path(args)
    ok = print_verdict(verdict)
    print(f"\ntotal: {time.monotonic() - total0:.0f} s")

    if args.gpu:
        key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
        gpu0 = time.monotonic()
        report = run_gpu_lane(key, os.path.dirname(os.path.abspath(__file__)))
        print(f"gpu lane total: {time.monotonic() - gpu0:.0f} s")
        crops = report.get("crops_b64") or {}
        if args.crops_out and crops:
            os.makedirs(args.crops_out, exist_ok=True)
            for name, b64 in crops.items():
                path = os.path.join(args.crops_out, name + ".png")
                with open(path, "wb") as fh:
                    fh.write(base64.b64decode(b64))
                print(f"wrote {path}")

    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
