#!/usr/bin/env python3
"""gpu-llm-batch-eval demo: one command, one disposable sandbox, one verdict.

Creates an agent-next sandbox, clones this repository inside it, installs
the pinned judge toolchain, runs the judge self-test, then grades the
known-good bundle — and always kills the sandbox afterwards, confirming it
is gone.

    python3 cookbook/gpu-llm-batch-eval/run.py [--ref main] [--keep] [--gpu]

Needs the `sbx` CLI (pip install
"git+https://github.com/agent-next/sandbox#subdirectory=cli") and
SBX_API_KEY (or E2B_API_KEY) in the environment.

The judge is CPU-only by construction: it reads the bundle the artifact
wrote and does string and float work, so the grading sandbox needs no GPU
and no network. `--gpu` adds a GPU lane that runs the *generation* on an
RTX 5090 VRAM slice lease over the REST API, exactly like
cookbook/small-gpu/run.py:

    POST /sandboxes {"accel": {"vram_gb": N, "reserve": "exec"}}
    PUT  /sandboxes/{id}/files/{name}     # raw bytes, workdir-relative
    POST /sandboxes/{id}/exec {"code": <python>, "timeout_s": N}
    DELETE /sandboxes/{id}; GET -> 404 or phase "dead"

The lease has Python 3.13 + torch cu128 but no network, so the pinned
weights and the pinned problems are downloaded and sha256-checked in *this*
CPU sandbox first, uploaded through the files API, and the resulting bundle
is downloaded back. The lease is deleted in a `finally` block and the
deletion confirmed with a GET; a lease whose cleanup cannot be confirmed
makes the script exit non-zero naming the id.

Standard library only. Wall time per step and the lease lifecycle are
printed.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = "https://github.com/agent-next/sandbox"
DEMO_DIR = "cookbook/gpu-llm-batch-eval"
API = "https://api.sbx.agent-next.com"

# sbx exec's default timeout is 60 s; setup installs a CUDA-class wheel set
# and the self-test grades 12 bundles, so every step needs more.
STEP_TIMEOUTS = {"clone": 300, "setup": 2400, "selftest": 1800, "grade": 900}

GPU_VRAM_GB = 24          # an RTX 5090 slice; 0.5B bf16 needs well under 2 GiB
GPU_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
GPU_MODEL_COMMIT = "7ae557604adf67be50417f59c2c2f167def9a775"
GPU_MODEL_FILES = ["config.json", "generation_config.json", "merges.txt",
                   "model.safetensors", "tokenizer.json",
                   "tokenizer_config.json", "vocab.json"]
HF_BASE = f"https://huggingface.co/{GPU_MODEL}/resolve/{GPU_MODEL_COMMIT}"
# The files API caps one upload at 512 MiB, so model.safetensors (~0.9 GiB)
# travels as chunks that the lease reassembles (and sha256-checks) itself.
UPLOAD_CHUNK = 400 * 1024 * 1024


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


def request(key, method, path, body=None, raw=None, timeout=900):
    """-> (status, parsed-body-or-None). `raw` sends bytes with no JSON."""
    if raw is not None:
        data, ctype = raw, "application/octet-stream"
    elif body is None:
        data, ctype = None, "application/json"
    else:
        data, ctype = json.dumps(body).encode(), "application/json"
    req = Request(API + path, data=data, method=method,
                  headers={"X-API-Key": key, "Content-Type": ctype})
    try:
        with urlopen(req, timeout=timeout) as r:
            payload = r.read()
            try:
                return r.status, json.loads(payload) if payload else None
            except ValueError:
                return r.status, payload
    except HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload) if payload else None
        except ValueError:
            return exc.code, {"message": payload.decode("utf-8", "replace")[:300]}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify_lease_id(sid):
    """Only gateway-generated gl-* ids may be interpolated into request paths."""
    if not isinstance(sid, str) or not sid.startswith("gl-") or not all(
            c.isascii() and (c.isalnum() or c == "-") for c in sid):
        die(f"lease create returned an unexpected id {sid!r}; it was NOT "
            "destroyed automatically — list your sandboxes and delete it")


def gpu_reattach_job(model_sha, n_parts):
    """First lease exec: reassemble the chunked weights and sha256-check them."""
    return f"""
import hashlib, os, glob

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

parts = sorted(glob.glob('model/model.safetensors.part*'))
assert len(parts) == {n_parts}, 'expected {n_parts} weight chunks, got %d' % len(parts)
with open('model/model.safetensors', 'wb') as out:
    for p in parts:
        with open(p, 'rb') as fh:
            for b in iter(lambda: fh.read(1 << 20), b''):
                out.write(b)
got = sha('model/model.safetensors')
assert got == {model_sha!r}, 'reassembled weights sha256 mismatch: ' + got
for p in parts:
    os.remove(p)
report['weights_sha256'] = got
report['weights_bytes'] = os.path.getsize('model/model.safetensors')
"""


def gpu_exec_job(problems_sha, device="cuda"):
    """Second lease exec: load local weights, generate, write the bundle.

    Paths are workdir-relative: uploads stream into the lease workdir, and
    downloads read <workdir>/out, so the bundle lands in out/bundle.json.
    """
    return f"""
import hashlib, json, os, time, sys
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

report['device_name'] = torch.cuda.get_device_name(0)
report['torch'] = torch.__version__
report['transformers'] = transformers.__version__
report['python'] = sys.version.split()[0]

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

got_problems = sha('problems.json')
assert got_problems == {problems_sha!r}, 'problems.json sha256 mismatch: ' + got_problems
report['problems_sha256'] = got_problems
report['weights_sha256'] = sha('model/model.safetensors')

rows = json.load(open('problems.json'))['problems']
tok = AutoTokenizer.from_pretrained('model', local_files_only=True)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token
tok.padding_side = 'left'
model = AutoModelForCausalLM.from_pretrained(
    'model', dtype=torch.bfloat16, local_files_only=True).to('cuda').eval()

SUF = ("\\nSolve the problem step by step. End your answer with the line "
       "'Final answer: <number>'.")
prompts = [tok.apply_chat_template([{{'role': 'user', 'content': r['question'] + SUF}}],
                                   tokenize=False, add_generation_prompt=True)
           for r in rows]

BATCH, MAXNEW = 8, 256
gens = [None] * len(rows)
n_new_total = 0
torch.cuda.reset_peak_memory_stats()
t0 = time.monotonic()
for start in range(0, len(rows), BATCH):
    chunk = list(range(start, min(start + BATCH, len(rows))))
    enc = tok([prompts[i] for i in chunk], return_tensors='pt', padding=True).to('cuda')
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=MAXNEW, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    new = out[:, enc['input_ids'].shape[1]:]
    lens = (new != tok.pad_token_id).sum(dim=1).tolist()
    for j, i in enumerate(chunk):
        n_new_total += int(lens[j])
        ids = new[j][:int(lens[j])]
        gens[i] = {{'i': rows[i]['i'], 'question': rows[i]['question'],
                    'generation': tok.decode(ids, skip_special_tokens=True),
                    'max_new_tokens': int(lens[j])}}
    print('gpu batch', start // BATCH + 1, flush=True)
wall = time.monotonic() - t0
torch.cuda.synchronize()
report['peak_vram_bytes'] = torch.cuda.max_memory_allocated()
report['generated_tokens'] = n_new_total
report['wall_time_s'] = round(wall, 3)
report['throughput_tok_s'] = round(n_new_total / wall, 3)

bundle = {{
    'model': {GPU_MODEL!r},
    'model_commit': {GPU_MODEL_COMMIT!r},
    'problems_sha256': got_problems,
    'n_problems': len(rows),
    'batch_size': BATCH,
    'max_new_tokens': MAXNEW,
    'temperature': 0.0,
    'greedy': True,
    'dtype': 'bfloat16',
    'device': {device!r},
    'generated_tokens': n_new_total,
    'wall_time_s': round(wall, 3),
    'throughput_tok_s': round(n_new_total / wall, 3),
    'reported_accuracy': None,   # filled below with the artifact's extractor
    'generations': gens,
}}
import re
FINAL = re.compile(r"final\\s*answer\\s*[:\\-]?\\s*\\**\\s*([-+]?[\\d,]+(?:\\.\\d+)?)", re.I)
ANY = re.compile(r"[-+]?\\d[\\d,]*(?:\\.\\d+)?")
def extract(text):
    hits = FINAL.findall(text or '') or ANY.findall(text or '')
    if not hits:
        return None
    raw = hits[-1].replace(',', '')
    try:
        v = float(raw)
    except ValueError:
        return None
    return str(int(v)) if v == int(v) else repr(round(v, 6))
correct = 0
for g, r in zip(gens, rows):
    g['extracted_answer'] = extract(g['generation'])
    if g['extracted_answer'] == r['gold']:
        correct += 1
bundle['reported_accuracy'] = round(correct / len(rows), 6)
report['reported_accuracy'] = bundle['reported_accuracy']
os.makedirs('out', exist_ok=True)
json.dump(bundle, open('out/bundle.json', 'w'), indent=1, sort_keys=True)
report['bundle_bytes'] = os.path.getsize('out/bundle.json')
"""


def load_model_pins(demo_path):
    """judge/MODEL.txt: '<sha256>  <name>' per pinned model file."""
    pins = {}
    path = os.path.join(demo_path, "judge", "MODEL.txt")
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            digest, name = line.split(None, 1)
            pins[name.strip()] = digest
    return pins


def upload_bytes(key, sid, name, data, want_sha):
    """PUT one file through the lease files API and verify its sha256."""
    st, body = request(key, "PUT", f"/sandboxes/{sid}/files/{name}", raw=data)
    if st != 200 or not isinstance(body, dict) or body.get("sha256") != want_sha:
        die(f"gpu: upload {name} HTTP {st}: {body}")
    return body


def run_gpu_lane(key, demo_path, report_json=None):
    """Generate the good bundle on a GPU slice lease; upload in, download out."""
    import tempfile
    problems_path = os.path.join(demo_path, "judge", "problems.json")
    problems_bytes = open(problems_path, "rb").read()
    problems_sha = sha256_file(problems_path)
    pins = load_model_pins(demo_path)

    print(f"gpu: creating lease ({GPU_VRAM_GB} GiB VRAM slice)...", flush=True)
    t0 = time.monotonic()
    st, created = request(key, "POST", "/sandboxes",
                          {"accel": {"vram_gb": GPU_VRAM_GB,
                                     "reserve": "exec"}})
    if st != 201:
        die(f"gpu: lease create HTTP {st}; check GPU access, credit and "
            "capacity (the CPU verdict above is unaffected)")
    sid = created["sandboxID"]
    verify_lease_id(sid)
    print(f"gpu: lease {sid} created ({time.monotonic() - t0:.0f} s)", flush=True)

    tmpdir = tempfile.mkdtemp(prefix="llm-eval-gpu-")
    try:
        print("gpu: uploading pinned problems + weights via the files API...",
              flush=True)
        t0 = time.monotonic()
        upload_bytes(key, sid, "problems.json", problems_bytes, problems_sha)
        for name in GPU_MODEL_FILES:
            path = os.path.join(tmpdir, name)
            if not os.path.exists(path):
                subprocess.run(["curl", "-sSL", "-o", path,
                                f"{HF_BASE}/{name}"], check=True)
            local_sha = sha256_file(path)
            if local_sha != pins.get(name):
                die(f"gpu: {name} sha256 {local_sha} does not match the pin "
                    f"in judge/MODEL.txt ({pins.get(name)})")
            size = os.path.getsize(path)
            if name != "model.safetensors" or size <= UPLOAD_CHUNK:
                upload_bytes(key, sid, f"model/{name}",
                             open(path, "rb").read(), local_sha)
                print(f"gpu:   uploaded model/{name} ({size} bytes)", flush=True)
                continue
            # the weights exceed the per-upload cap: send them as chunks the
            # lease reassembles (and sha256-checks) itself
            n_parts = 0
            with open(path, "rb") as fh:
                while True:
                    chunk = fh.read(UPLOAD_CHUNK)
                    if not chunk:
                        break
                    part_sha = sha256_bytes(chunk)
                    upload_bytes(key, sid,
                                 f"model/{name}.part{n_parts}", chunk,
                                 part_sha)
                    n_parts += 1
                    print(f"gpu:   uploaded model/{name}.part{n_parts - 1} "
                          f"({len(chunk)} bytes)", flush=True)
            report = reassemble(key, sid, local_sha, n_parts)
            print(f"gpu:   reassembled model/{name} ({report['weights_bytes']} "
                  f"bytes, sha256 verified on the lease)", flush=True)
        print(f"gpu: upload round trip {time.monotonic() - t0:.0f} s", flush=True)

        print("gpu: running batched generation on the lease...", flush=True)
        t0 = time.monotonic()
        st, executed = request(key, "POST", f"/sandboxes/{sid}/exec",
                               {"code": gpu_exec_job(problems_sha),
                                "timeout_s": 3600})
        print(f"gpu: exec round trip {time.monotonic() - t0:.0f} s "
              f"(HTTP {st})", flush=True)
        if st != 200 or not isinstance(executed, dict):
            die(f"gpu: exec HTTP {st}; the CPU verdict above is unaffected")
        result = executed.get("result") or {}
        if result.get("ok") is not True:
            die(f"gpu: job failed: {result.get('stderr', '')[-800:]}")
        report = result.get("report") or {}

        st, bundle_bytes = request(key, "GET",
                                   f"/sandboxes/{sid}/files/bundle.json")
        if st != 200 or not isinstance(bundle_bytes, bytes):
            die(f"gpu: could not download bundle.json: HTTP {st}")
        out = os.path.join(demo_path, "examples", "good", "bundle.json")
        with open(out, "wb") as fh:
            fh.write(bundle_bytes)
        print(f"gpu: wrote {out} ({len(bundle_bytes)} bytes)", flush=True)
        if report_json:
            with open(report_json, "w") as fh:
                json.dump(report, fh, indent=2, sort_keys=True)
            print(f"gpu: wrote exec report {report_json}", flush=True)
        return report
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        print(f"gpu: destroying lease {sid}...", flush=True)
        try:
            request(key, "DELETE", f"/sandboxes/{sid}")
        except Exception:
            # a lost destroy reply may still mean the lease was released;
            # the GET below is what decides
            pass
        try:
            st, remaining = request(key, "GET", f"/sandboxes/{sid}")
        except Exception as exc:
            die(f"gpu: cleanup unconfirmed for lease {sid} ({exc}); it may "
                f"still be live — DELETE /sandboxes/{sid}", 2)
        if st != 404 and not (st == 200 and isinstance(remaining, dict)
                              and remaining.get("phase") == "dead"):
            die(f"gpu: cleanup unconfirmed for lease {sid}: HTTP {st}; it "
                f"may still be live — DELETE /sandboxes/{sid}", 2)
        print(f"gpu: lease {sid} deleted; GET confirms gone (404)", flush=True)


def reassemble(key, sid, want_sha, n_parts):
    """Run the chunk-reassembly exec; return its report."""
    st, executed = request(key, "POST", f"/sandboxes/{sid}/exec",
                           {"code": gpu_reattach_job(want_sha, n_parts),
                            "timeout_s": 900})
    if st != 200 or not isinstance(executed, dict):
        die(f"gpu: reassembly exec HTTP {st}")
    result = executed.get("result") or {}
    if result.get("ok") is not True:
        die(f"gpu: reassembly failed: {result.get('stderr', '')[-800:]}")
    return result.get("report") or {}


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main",
                    help="repository ref to clone inside the sandbox")
    ap.add_argument("--keep", action="store_true",
                    help="leave the sandbox up and print its id")
    ap.add_argument("--gpu", action="store_true",
                    help="also generate the good bundle on a "
                         f"{GPU_VRAM_GB} GiB VRAM slice lease (reported)")
    ap.add_argument("--report-json", metavar="PATH",
                    help="write the verdict JSON (and the GPU exec report) here")
    args = ap.parse_args()

    total0 = time.monotonic()

    if args.gpu:
        key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
        if not key:
            die("no API key: export SBX_API_KEY (or E2B_API_KEY)")
        report = run_gpu_lane(key, os.path.dirname(os.path.abspath(__file__)),
                              args.report_json)
        print(json.dumps(report, indent=2, sort_keys=True))
        print(f"total: {time.monotonic() - total0:.0f} s")
        return

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
                            f"sandbox/{DEMO_DIR}/examples/good/bundle.json",
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

    print(f"total: {time.monotonic() - total0:.0f} s")
    if not verdict:
        die("no verdict JSON returned from the sandbox")
    if args.report_json:
        with open(args.report_json, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
        print(f"wrote verdict JSON: {args.report_json}")

    gates = verdict.get("gates", {})
    ok = all(g.get("pass") for g in gates.values()) and \
        verdict.get("judge_intact", False)
    print(f"\ngpu-llm-batch-eval demo: {'PASS' if ok else 'FAIL'}")
    for name, g in sorted(gates.items()):
        print(f"  gate {name}: {'pass' if g.get('pass') else 'FAIL'}")
    acc = (gates.get("judge_accuracy") or {})
    tok = (gates.get("token_accounting") or {})
    if acc.get("judge_accuracy") is not None:
        print(f"  judge accuracy {acc['judge_accuracy']:.3f} "
              f"({acc['correct']}/{acc['n']}) vs reported "
              f"{acc['reported_accuracy']:.3f}")
    if tok.get("derived_tok_s"):
        print(f"  throughput {tok['derived_tok_s']:.1f} tok/s on "
              f"{tok.get('device')}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
