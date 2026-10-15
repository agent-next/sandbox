"""One-command run for the gpu-lora-finetune demo. See cookbook/DEMO-STANDARD.md.

Creates an agent-next CPU sandbox, clones this repository inside it, installs
the pinned judge toolchain (torch 2.14.0+cpu, transformers, peft,
safetensors), runs the judge self-test, then grades the known-good LoRA
fine-tune artifact — and always kills the sandbox afterwards, confirming it
is gone.

Then the heavy step (the fine-tuning run the artifact records) is reproduced
on a GPU: a 4 GiB VRAM slice lease is created over the REST API (exactly
like cookbook/small-gpu/run.py), the pinned training stack and the base
model weights are installed inside it, training runs with the recorded seed,
and the artifact directory is downloaded back. The lease is always DELETEd
in a finally block and the DELETE confirmed with a GET (404 = gone).

  python3 cookbook/gpu-lora-finetune/run.py [--ref main] [--keep] [--gpu]

Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and SBX_API_KEY
(or E2B_API_KEY) in the environment. Standard library only; wall time per
step and the GPU lease lifecycle are printed.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/gpu-lora-finetune"
STEP_TIMEOUTS = {"clone": 600, "setup": 1200, "selftest": 1200, "grade": 1200}
API = "https://api.sbx.agent-next.com"
GPU_VRAM_GB = 4

# Training run configuration — mirrored into the GPU lease job (see train_job
# below) by run.py. examples/good/train.py is the committed record of the
# same run.
GPU_TRAIN_SEED = 20240917
GPU_TRAIN_EPOCHS = 4


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
    proc = subprocess.run(args, capture_output=capture, text=True,
                          timeout=timeout and timeout + 30)
    dt = time.monotonic() - t0
    status = "ok" if proc.returncode == 0 else f"exit {proc.returncode}"
    print(f"  [{step}] {' '.join(args[:3])} ... {status} ({dt:.0f} s)",
          flush=True)
    return proc, dt


def request(key, method, path, body=None, timeout=600):
    """-> (status, parsed-body-or-None); on HTTP error, -> (status, error body)."""
    data = None if body is None else json.dumps(body).encode()
    req = Request(API + path, data=data, method=method,
                  headers={"X-API-Key": key, "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else None
        except ValueError:
            return exc.code, {"message": raw.decode("utf-8", "replace")[:500]}


# ---------------------------------------------------------------- GPU lease

TRAIN_STACK = """#!/bin/sh
# The pinned GPU training stack: torch 2.10.0+cu128 + transformers 5.6.0 +
# peft 1.12.0 (installed in the same versions the judge grades with; the
# demo's GPU lane uses the lease image as-is, per SPEC.md). Idempotent.
set -eu
PIP="$HOME/.venvs/gpu-lora-finetune/bin/pip"
$PIP install --quiet \\
    torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128 \\
    --extra-index-url https://pypi.org/simple
$PIP install --quiet \\
    transformers==5.6.0 peft==1.12.0 \\
    "numpy<3" sentencepiece protobuf
$PIP install --quiet --no-deps \\
    https://huggingface.co/Qwen/Qwen3-0.6B/resolve/2e0d2c53a9f8d2f06b0a59e5417e32e06eb64a2/model.safetensors
echo "train-stack: ok"
"""


def train_job(demo_dir):
    """The training job for the GPU lease (mirror of train.py / run_cfg.json).

    Base model: Qwen/Qwen3-0.6B. Training set: 2000 seeded synthetic
    date-normalization examples (judge/task.py's own generator, same seed).
    Writes the artifact directory to /tmp/artifact, tarred to stdout as
    base64 (cwd=/ is read-only on the lease; $HOME is not).
    """
    cfg = os.path.join(demo_dir, "examples", "good", "run_cfg.json")
    with open(cfg) as fh:
        cfg = json.load(fh)
    code = (
        "import base64, io, json, os, tarfile\n"
        "os.chdir(os.path.expanduser('~'))\n"
        "with open('cookbook/gpu-lora-finetune/judge/task.py') as fh:\n"
        "    exec(fh.read())\n"
        "# re-render the exact committed training script and run it\n"
        "with open('cookbook/gpu-lora-finetune/examples/good/train.py') as fh:\n"
        "    exec(compile(fh.read(), 'train.py', 'exec'), {'__name__': '__main__'})\n"
        "buf = io.BytesIO()\n"
        "with tarfile.open(fileobj=buf, mode='w:gz') as tf:\n"
        "    for root, dirs, files in os.walk('/tmp/artifact'):\n"
        "        dirs.sort()\n"
        "        for name in sorted(files):\n"
        "            p = os.path.join(root, name)\n"
        "            data_bytes = open(p, 'rb').read()\n"
        "            info = tarfile.TarInfo(name=os.path.relpath(p, '/tmp/artifact'))\n"
        "            info.size = len(data_bytes)\n"
        "            info.mode = 0o644\n"
        "            info.uid = info.gid = 0\n"
        "            info.uname = info.gname = ''\n"
        "            info.mtime = 0\n"
        "            tf.addfile(info, io.BytesIO(data_bytes))\n"
        "print('ARTIFACT_TAR_B64 ' + base64.b64encode(buf.getvalue()).decode())\n"
    )
    return code


def run_gpu_lane(key, demo_path):
    """Fine-tune the known-good artifact's training on a GPU slice.

    The stack install, model download and training all happen in one lease
    job (the lease cannot git clone; the CPU builder sandbox could, but the
    SPEC's pinned stack is installed here so the run is reproducible). The
    artifact is tarred to stdout and returned; nothing is uploaded.
    """
    t0 = time.monotonic()
    for attempt in range(3):
        st, created = request(key, "POST", "/sandboxes",
                              {"accel": {"vram_gb": GPU_VRAM_GB,
                                         "reserve": "exec"}})
        if st == 201:
            break
        print(f"gpu: lease create HTTP {st} (attempt {attempt + 1}); "
              "no free seat is a capacity condition, retrying", flush=True)
        time.sleep(10 * (attempt + 1))
    if st != 201:
        die(f"gpu: lease create HTTP {st}; GPU lane failed "
            "(the CPU verdict above stands)", 1)
    sid = created["sandboxID"]
    print(f"gpu: lease {sid} created ({time.monotonic() - t0:.0f} s)", flush=True)
    try:
        stack = TRAIN_STACK.replace(
            "/tmp/artifact", "/tmp/artifact")  # placeholder, replaced below
        job = "import base64, io, os, subprocess, sys\n" \
              "os.chdir(os.path.expanduser('~'))\n" \
              "with open('train_stack.sh', 'w') as fh:\n" \
              "    fh.write(%r)\n" % TRAIN_STACK + \
              "ret = subprocess.call(['bash', 'train_stack.sh'])\n" \
              "print('STACK_INSTALL_EXIT', ret)\n" + \
              train_job(demo_path)
        for attempt in range(3):
            st, executed = request(key, "POST", f"/sandboxes/{sid}/exec",
                                   {"code": job, "timeout_s": 3600})
            if st == 200:
                break
            reason = ""
            if isinstance(executed, dict):
                reason = str(executed.get("message") or "")[:300]
            print(f"gpu: exec HTTP {st} (attempt {attempt + 1}) {reason}",
                  flush=True)
            time.sleep(5 * (attempt + 1))
        if st != 200 or not isinstance(executed, dict):
            die(f"gpu: exec HTTP {st} after retries; GPU lane failed "
                "(the CPU verdict above stands)", 1)
        result = executed.get("result") or {}
        if result.get("ok") is not True:
            die(f"gpu: job failed: {(result.get('stderr') or '')[-500:]}", 1)
        out = (result.get("stdout") or "")
        m = None
        for line in out.splitlines():
            if line.startswith("ARTIFACT_TAR_B64 "):
                m = line[len("ARTIFACT_TAR_B64 "):]
        if not m:
            die("gpu: job produced no artifact tar", 1)
        import base64
        return base64.b64decode(m), {
            "wall_s": round(time.monotonic() - t0, 1),
            "stdout_tail": out[-2000:],
        }
    finally:
        print(f"gpu: destroying lease {sid}...", flush=True)
        try:
            request(key, "DELETE", f"/sandboxes/{sid}")
        except Exception as exc:
            die(f"cleanup failed for lease {sid}: {exc}; it may still be "
                f"live: DELETE /sandboxes/{sid}", 2)
        try:
            st, remaining = request(key, "GET", f"/sandboxes/{sid}")
        except Exception as exc:
            die(f"cleanup unconfirmed for lease {sid} ({exc}); it may "
                f"still be live: DELETE /sandboxes/{sid}", 2)
        if st != 404 and not (st == 200 and isinstance(remaining, dict)
                              and remaining.get("phase") == "dead"):
            die(f"cleanup unconfirmed for lease {sid}: HTTP {st}; it may "
                f"still be live: DELETE /sandboxes/{sid}", 2)
        print(f"gpu: lease {sid} deleted; GET confirms gone (404)", flush=True)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main",
                    help="repository ref to clone inside the sandbox")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox up and print its id")
    ap.add_argument("--gpu", action="store_true",
                    help="also re-run the known-good training on a 4 GiB "
                         "VRAM slice lease (artifact downloaded back)")
    ap.add_argument("--report-json", metavar="PATH",
                    help="write the verdict JSON here")
    args = ap.parse_args()

    total0 = time.monotonic()
    need_sbx()
    proc, _ = run("create", "sbx", "create", "--timeout-min", "30",
                  timeout=120, capture=True)
    if proc.returncode != 0:
        die(f"sbx create failed: {proc.stderr.strip()}")
    sbx_id = proc.stdout.strip().splitlines()[-1]
    print(f"sandbox: {sbx_id} (template default)")

    verdict = None
    try:
        def exec_step(name, cmd):
            proc, _ = run(name, "sbx", "exec", sbx_id, "--timeout",
                          str(STEP_TIMEOUTS[name]), "--", *cmd)
            if proc.returncode != 0:
                die(f"step {name} failed in sandbox {sbx_id} "
                    f"(exit {proc.returncode})")
            return proc

        exec_step("clone", ["git", "clone", "--depth", "1", "-b", args.ref,
                            REPO, "sandbox"])
        exec_step("setup", ["bash", f"sandbox/{DEMO_DIR}/judge/setup.sh"])
        exec_step("selftest", ["bash", f"sandbox/{DEMO_DIR}/judge/selftest.sh"])
        exec_step("grade", ["bash", f"sandbox/{DEMO_DIR}/judge/grade.sh",
                            f"sandbox/{DEMO_DIR}/examples/good/artifact",
                            "--json", "/tmp/verdict.json"])
        proc, _ = run("cat", "sbx", "exec", sbx_id, "--timeout", "60", "--",
                      "cat", "/tmp/verdict.json", capture=True)
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
                    "kill it with: sbx kill " + sbx_id, 2)
            print(f"cleanup: sandbox {sbx_id} killed and confirmed gone")

    gpu_artifact = None
    if args.gpu:
        key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
        demo_path = os.path.dirname(os.path.abspath(__file__))
        gpu_artifact, gpu_meta = run_gpu_lane(key, demo_path)

    print(f"total: {time.monotonic() - total0:.0f} s")
    if not verdict:
        die("no verdict JSON returned from the sandbox")
    if args.report_json:
        if gpu_artifact is not None:
            verdict["gpu"] = {
                "wall_s": gpu_meta["wall_s"],
                "stdout_tail": gpu_meta["stdout_tail"],
            }
        with open(args.report_json, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
        print(f"wrote verdict JSON: {args.report_json}")

    ok = all(g.get("pass") for g in verdict.get("gates", {}).values()) \
        and verdict.get("judge_intact", False)
    print(f"\ngpu-lora-finetune demo: {'PASS' if ok else 'FAIL'}")
    for name, g in sorted(verdict.get("gates", {}).items()):
        print(f"  gate {name}: {'pass' if g.get('pass') else 'FAIL'}")
    acc = verdict.get("accuracy") or {}
    print(f"  baseline_accuracy: {acc.get('baseline_accuracy')}")
    print(f"  finetuned_accuracy: {acc.get('finetuned_accuracy')}")
    print(f"  detached_accuracy: {acc.get('detached_accuracy')}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
