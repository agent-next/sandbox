#!/usr/bin/env python3
"""Judge driver for the gpu-kernel demo. Invoked by grade.sh; see SPEC.md.

Grades a copied artifact (the artifact under test never touches judge/):
  gate 1 structure      — size, byte-compile, API surface, no delegation names
  gate 2 device-compile — triton.compile to sm_80 and sm_90 cubins, no GPU
  gate 3 correctness    — oracle comparisons over shapes/seeds/distributions
  gate 4 speed          — reported (CUDA full mode only); gates only with
                          --speed-target

Prints one JSON verdict on stdout; exit 0 only if every gated pass rule holds.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

VENV_DIR = os.path.join(os.path.expanduser("~"), ".venvs", "gpu-kernel")
sys.path.insert(0, VENV_DIR)

DELEGATION_NAMES = (
    "torch.softmax", "torch.nn.functional.softmax", "F.softmax",
    "log_softmax", "torch.special.softmax",
)

MAX_BYTES = 64 * 1024

# correctness cases: (rows, cols, distribution, seed)
FULL_CASES = [
    (4096, 4096, "randn", 0),
    (4096, 4096, "randn64", 1),
    (4096, 4096, "big", 2),
    (128, 4093, "randn", 3),
    (128, 4093, "last_max", 4),
    (37, 65, "randn", 5),
    (3, 1, "randn", 6),
    (1, 4096, "randn", 7),
    (1000, 1000, "zeros", 8),
    (64, 512, "shift", 9),
]
CPU_CASES = [
    (64, 4096, "randn", 0),
    (64, 4096, "randn64", 1),
    (7, 4093, "randn", 2),
    (7, 4093, "last_max", 3),
    (37, 65, "randn", 4),
    (3, 1, "randn", 5),
    (1, 1024, "randn", 6),
    (8, 512, "zeros", 7),
    (8, 512, "const3", 8),
    (64, 512, "shift", 9),
]

SPEED_SHAPE = (4096, 4096)
SPEED_WARMUP, SPEED_RUNS = 3, 9

ATOL, RTOL = 1e-6, 1e-5
ROWSUM_TOL = 1e-4
SHIFT_TOL = 1e-5


def die(msg):
    print(json.dumps({"error": msg}))
    sys.exit(2)


def check_shas(judge_dir):
    """sha256 of every judge/ source file, before and after the run.

    __pycache__ is excluded: importing the judge legitimately writes .pyc
    files, and they are not judge source.
    """
    digests = {}
    for root, dirs, files in os.walk(judge_dir):
        dirs.sort()
        if os.path.basename(root) == "__pycache__":
            dirs[:] = []
            continue
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            path = os.path.join(root, name)
            with open(path, "rb") as fh:
                digests[os.path.relpath(path, judge_dir)] = \
                    hashlib.sha256(fh.read()).hexdigest()
    return digests


def make_input(dist, rows, cols, seed):
    g = torch.Generator().manual_seed(seed)
    if dist == "randn":
        return torch.randn(rows, cols, generator=g)
    if dist == "randn64":
        return torch.randn(rows, cols, generator=g) * 64.0
    if dist == "big":
        return torch.randn(rows, cols, generator=g) + 5000.0
    if dist == "zeros":
        return torch.zeros(rows, cols)
    if dist == "const3":
        return torch.full((rows, cols), 3.0)
    if dist == "last_max":
        x = torch.randn(rows, cols, generator=g)
        x[:, -1] = x.max(dim=1).values + 50.0
        return x
    if dist == "shift":          # plain input; the judge adds the 777.0 shift
        return torch.randn(rows, cols, generator=g)
    raise ValueError(dist)


class LaunchCounter:
    """Wraps a jitted kernel so `KERNEL[grid](...)` counts launches."""

    def __init__(self, fn):
        self.fn = fn
        self.count = 0

    def __getitem__(self, grid):
        self.count += 1
        return self.fn[grid]


def load_artifact(path):
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError("artifact exceeds 64 KiB")
    with open(path, "rb") as fh:
        source = fh.read()
    compile(source, path, "exec")          # gate 1 byte-compile, no import
    text = source.decode("utf-8", "replace")
    for bad in DELEGATION_NAMES:
        if bad in text:
            raise ValueError(f"artifact text contains {bad!r} (softmax delegation)")
    spec = importlib.util.spec_from_file_location(
        "artifact_under_test", os.path.abspath(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, text


def gate_structure(mod, text):
    problems = []
    jit_type = type(mod.KERNEL).__name__
    if jit_type not in ("JITFunction", "InterpretedFunction"):
        problems.append(f"KERNEL is {jit_type}, not a triton.jit function")
    if not callable(getattr(mod, "softmax", None)):
        problems.append("softmax is not callable")
    for dictname in ("SIGNATURE", "CONSTEXPRS"):
        d = getattr(mod, dictname, None)
        if not isinstance(d, dict):
            problems.append(f"{dictname} is not a dict")
    if not problems:
        want = list(mod.KERNEL.arg_names)
        if list(mod.SIGNATURE) != want:
            problems.append(f"SIGNATURE keys {list(mod.SIGNATURE)} != kernel args {want}")
        extra = [k for k in mod.CONSTEXPRS if k not in want]
        if extra:
            problems.append(f"CONSTEXPRS keys {extra} are not kernel args")
    return problems


def gate_device_compile(mod):
    import triton
    from triton.compiler import ASTSource
    from triton.backends.compiler import GPUTarget
    problems = []
    for cc in (80, 90):
        try:
            src = ASTSource(fn=mod.KERNEL,
                            signature=dict(mod.SIGNATURE),
                            constexprs=dict(mod.CONSTEXPRS))
            compiled = triton.compile(src, target=GPUTarget("cuda", cc, 32))
            if not compiled.asm.get("cubin"):
                problems.append(f"sm_{cc}: compile produced no cubin")
        except Exception as exc:
            problems.append(f"sm_{cc}: {type(exc).__name__}: {exc}"[:300])
    return problems


def run_cases(mod, cases, device):
    """Run every correctness case; return per-case results and worst errors."""
    results = []
    worst = {"max_abs": 0.0, "rowsum": 0.0, "shift": 0.0}
    for rows, cols, dist, seed in cases:
        x = make_input(dist, rows, cols, seed).to(device)
        x_before = x.clone()
        counter = LaunchCounter(mod.KERNEL)
        mod.KERNEL = counter
        try:
            out = mod.softmax(x)
        finally:
            mod.KERNEL = counter.fn
        case = {"shape": [rows, cols], "dist": dist, "seed": seed}
        ref = torch.softmax(x, dim=1)
        err = float((out - ref).abs().max().item())
        case["max_abs_err"] = err
        case["finite01"] = bool(torch.isfinite(out).all().item()
                                and out.le(1.0).all().item()
                                and out.ge(0.0).all().item())
        case["allclose"] = bool(torch.allclose(out, ref, rtol=RTOL, atol=ATOL))
        rowsum = float((out.sum(dim=1) - 1.0).abs().max().item())
        case["rowsum_err"] = rowsum
        case["rowsum_ok"] = rowsum <= ROWSUM_TOL
        case["input_intact"] = bool(torch.equal(x, x_before))
        case["launched"] = counter.count >= 1
        if not case["finite01"] or not case["allclose"]:
            case["ok"] = False
        elif not case["rowsum_ok"] or not case["input_intact"] or not case["launched"]:
            case["ok"] = False
        else:
            case["ok"] = True
        worst["max_abs"] = max(worst["max_abs"], err)
        worst["rowsum"] = max(worst["rowsum"], rowsum)
        results.append(case)
        # shift-invariance case: run once per shape family, on the shift dist
        if dist == "shift":
            x2 = x + 777.0
            out2 = mod.softmax(x2)
            shift_err = float((out2 - out).abs().max().item())
            case["shift_err"] = shift_err
            case["shift_ok"] = shift_err <= SHIFT_TOL and case["ok"]
            worst["shift"] = max(worst["shift"], shift_err)
            if not case["shift_ok"]:
                case["ok"] = False
    return results, worst


def gate_speed(softmax_fn, device):
    """Median-of-9 CUDA-event timing of artifact vs torch eager."""
    x = torch.randn(*SPEED_SHAPE, device=device)
    for _ in range(SPEED_WARMUP):
        softmax_fn(x)
    torch.cuda.synchronize()

    def median_ms(fn):
        times = []
        for _ in range(SPEED_RUNS):
            start = torch.cuda.Event(enable_timing=True)
            end = torch.cuda.Event(enable_timing=True)
            start.record()
            fn(x)
            end.record()
            torch.cuda.synchronize()
            times.append(start.elapsed_time(end))
        times.sort()
        return times[len(times) // 2]

    kernel_ms = median_ms(softmax_fn)
    eager_ms = median_ms(lambda t: torch.softmax(t, dim=1))
    return {"kernel_ms": kernel_ms, "eager_ms": eager_ms,
            "speedup": eager_ms / kernel_ms}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--cpu-check", action="store_true")
    ap.add_argument("--speed-target", type=float)
    ap.add_argument("--judge-dir")
    args = ap.parse_args()

    # TRITON_INTERPRET must be set before triton is first imported (torch
    # imports it). A forced --cpu-check sets it immediately; auto mode probes
    # CUDA in a throwaway subprocess so this process stays triton-free until
    # the environment is right.
    if args.cpu_check:
        mode = "cpu-check"
    else:
        probe = subprocess.run(
            [sys.executable, "-c", "import torch; print(int(torch.cuda.is_available()))"],
            capture_output=True, text=True, timeout=600)
        mode = ("full" if probe.returncode == 0 and probe.stdout.strip() == "1"
                else "cpu-check")
    if mode == "cpu-check":
        os.environ["TRITON_INTERPRET"] = "1"
    global torch
    import torch

    judge_dir = os.path.abspath(args.judge_dir or
                                os.path.join(os.path.dirname(__file__)))
    sha_before = check_shas(judge_dir)

    tmp = tempfile.mkdtemp(prefix="gpu-kernel-artifact-")
    art_path = os.path.join(tmp, "kernel.py")
    shutil.copy(args.artifact, art_path)

    verdict = {"artifact": os.path.basename(args.artifact), "mode": mode,
               "seed": args.seed, "gates": {}, "timing": {}, "cases": []}
    rc = 0
    try:
        try:
            mod, text = load_artifact(art_path)
        except Exception as exc:
            verdict["gates"]["structure"] = {"pass": False,
                                             "problems": [str(exc)[:300]]}
            rc = 1
        else:
            verdict["gates"]["structure"] = {
                "pass": True, "problems": gate_structure(mod, text)}
            if verdict["gates"]["structure"]["problems"]:
                verdict["gates"]["structure"]["pass"] = False
                rc = 1

        if rc == 0:
            # TRITON_INTERPRET must be set before triton is first imported;
            # the artifact import above already imported triton, so gate 2
            # runs in a fresh subprocess in cpu-check mode (full mode compiles
            # for the local device and needs no interpreter).
            if mode == "full":
                problems = gate_device_compile(mod)
                verdict["gates"]["device-compile"] = {
                    "pass": not problems, "problems": problems}
                if problems:
                    rc = 1
            else:
                compiled = subprocess_compile(art_path, judge_dir)
                verdict["gates"]["device-compile"] = compiled
                if not compiled["pass"]:
                    rc = 1

        if rc == 0:
            device = "cuda" if mode == "full" else "cpu"
            cases = FULL_CASES if mode == "full" else CPU_CASES
            if args.seed:
                cases = [(r, c, d, s + args.seed) for r, c, d, s in cases]
            results, worst = run_cases(mod, cases, device)
            verdict["cases"] = results
            ok = all(c["ok"] for c in results)
            verdict["gates"]["correctness"] = {
                "pass": ok, "cases": len(results),
                "failed": [f"{c['shape']}/{c['dist']}" for c in results if not c["ok"]],
                "worst": worst}
            if not ok:
                rc = 1

        if rc == 0 and mode == "full":
            speed = gate_speed(mod.softmax, "cuda")
            verdict["timing"] = speed
            if args.speed_target is not None:
                verdict["gates"]["speed"] = {
                    "pass": speed["speedup"] >= args.speed_target,
                    "target": args.speed_target,
                    "speedup": speed["speedup"]}
                if not verdict["gates"]["speed"]["pass"]:
                    rc = 1

        sha_after = check_shas(judge_dir)
        verdict["judge_intact"] = sha_before == sha_after
        if not verdict["judge_intact"]:
            rc = 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    sys.exit(rc)


def subprocess_compile(art_path, judge_dir):
    """Run gate 2 in a fresh interpreter (TRITON_INTERPRET unset by parent)."""
    env = {k: v for k, v in os.environ.items() if k != "TRITON_INTERPRET"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        "import sys, json;"
        "sys.path.insert(0, sys.argv[1]);"
        "import importlib.util;"
        "spec = importlib.util.spec_from_file_location('au', sys.argv[2]);"
        "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod);"
        "sys.path.insert(0, sys.argv[3]);"
        "import _grade;"
        "probs = _grade.gate_device_compile(mod);"
        "print(json.dumps({'pass': not probs, 'problems': probs}))"
    )
    try:
        r = subprocess.run(
            [sys.executable, "-c", code, VENV_DIR, art_path, judge_dir],
            capture_output=True, text=True, env=env, timeout=300)
        last = r.stdout.strip().splitlines()
        if r.returncode == 0 and last:
            return json.loads(last[-1])
        return {"pass": False, "problems": [r.stderr.strip()[-300:]]}
    except Exception as exc:
        return {"pass": False, "problems": [f"subprocess: {exc}"]}


if __name__ == "__main__":
    main()
