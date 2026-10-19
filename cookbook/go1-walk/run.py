#!/usr/bin/env python3
"""One command: fresh 4 GiB lease, PPO, real self-test, independent grade.

Python 3.10+, standard library only. The networkless GPU image is pinned
and all source/model data is shipped through REST exec payloads.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "judge"))
import grade as G
from selftest import checked_verdict, selftest_on_lease

SHIP = {"env.py": HERE / "env.py", "train.py": HERE / "train.py",
        "_eval.py": HERE / "judge/_eval.py",
        "go1_meshless.xml": HERE / "model/go1_meshless.xml"}

SETUP = """
import base64, os, subprocess, sys
root = os.path.expanduser('~/go1job')
os.makedirs(os.path.join(root, 'model'), exist_ok=True)
for name, value in __PAYLOAD__.items():
    path = os.path.join(root, 'model' if name.endswith('.xml') else '', name)
    open(path, 'wb').write(base64.b64decode(value))
p = subprocess.run([sys.executable, '-c',
    "import _eval, json; v,b = _eval.check_stack(); "
    "print(json.dumps(v)); assert not b, b"],
    cwd=root, capture_output=True, text=True, timeout=120)
report['rc'] = p.returncode
report['stdout'] = p.stdout
report['stderr'] = p.stderr
report['gpu'] = subprocess.run(
    ['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'],
    capture_output=True, text=True, timeout=10).stdout.strip()
"""

TRAIN = """
import json, os, subprocess, sys
root = os.path.expanduser('~/go1job')
args = [sys.executable, 'train.py', '--config', 'train_config.json',
        '--out', 'out', '--progress', 'out/progress.json', '--max-wall-s', '__CHUNK_S__']
if __RESUME__:
    args += ['--resume', 'out/state.pt']
p = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=560)
report['rc'] = p.returncode
report['stdout'] = p.stdout[-6000:]
report['stderr'] = p.stderr[-3000:]
if p.returncode == 0:
    report['status'] = json.load(open(os.path.join(root, 'out/progress.json')))
"""


def checked_exec(lease, code, timeout, step):
    result = lease.exec(code, timeout)
    rep = result.get("report") or {}
    if result.get("ok") is not True or rep.get("rc") != 0:
        raise RuntimeError(f"{step} failed: {rep.get('stderr') or result.get('stderr')}")
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vram", type=int, default=4)
    ap.add_argument("--config", type=Path, default=HERE / "examples/good/train_config.json")
    ap.add_argument("--iters", type=int)
    ap.add_argument("--chunk-s", type=int, default=90)
    ap.add_argument("--backup-checkpoints", action="store_true",
                    help="also download a policy after every training chunk")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--skip-train", type=Path, metavar="ARTIFACT_DIR")
    ap.add_argument("--selftest", action="store_true", help="self-test is already the default")
    ap.add_argument("--no-selftest", action="store_true", help="exploration only, not a complete demo run")
    ap.add_argument("--seeds", default="101,202,303")
    ap.add_argument("--trace", action="store_true", help="download exact judge-scored states")
    ap.add_argument("--outdir", type=Path, default=HERE / "out")
    a = ap.parse_args()
    if a.iters is not None and a.iters < 1:
        ap.error("--iters must be positive")
    if a.vram < 1 or a.vram > 32:
        ap.error("--vram must be in 1..32")
    if not 1 <= a.chunk_s <= 420:
        ap.error("--chunk-s must be in 1..420")
    key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
    if not key:
        G.die("export SBX_API_KEY (or E2B_API_KEY)")
    a.outdir.mkdir(parents=True, exist_ok=True)
    a.outdir = a.outdir.resolve()
    artifact = a.skip_train.resolve() if a.skip_train else a.outdir
    if not a.no_selftest:
        required = ["reward-flipped.npz"] if not a.skip_train else [
            "policy.npz", "step0.npz", "short.npz", "reward-flipped.npz"]
        for name in required:
            directory = artifact if a.skip_train else HERE / "examples/good"
            if not (directory / name).is_file():
                ap.error(f"self-test requires {directory.name}/{name}; "
                         "regenerate the documented known-good artifact first")
    cfg = json.loads(a.config.read_text())
    if a.iters:
        cfg["iters"] = a.iters
    if not a.skip_train:
        (a.outdir / "train_config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    total0 = time.monotonic()
    timing = {"grade_completed": False}
    lease = G.Lease(key, a.vram)
    sid = None
    rc = 1
    try:
        t = time.monotonic()
        lease.__enter__()
        sid = lease.id
        timing["create_s"] = round(time.monotonic() - t, 3)
        print(f"create: {sid}, {a.vram} GiB, {timing['create_s']} s", flush=True)
        payload = {n: base64.b64encode(p.read_bytes()).decode() for n, p in SHIP.items()}
        payload["train_config.json"] = base64.b64encode(json.dumps(cfg).encode()).decode()
        t = time.monotonic()
        rep = checked_exec(lease, SETUP.replace("__PAYLOAD__", repr(payload)), 180, "setup")
        timing["setup_s"] = round(time.monotonic() - t, 3)
        print(f"setup: rc=0, {timing['setup_s']} s; gpu={rep['gpu']}; "
              f"stack={rep['stdout'].strip()}", flush=True)
        if not a.skip_train:
            t = time.monotonic()
            for chunk in range(1, 401):
                code = TRAIN.replace("__RESUME__", str(chunk > 1)).replace("__CHUNK_S__", str(a.chunk_s))
                rep = checked_exec(lease, code,
                                   600, f"training chunk {chunk}")
                st = rep["status"]
                print(f"training chunk {chunk}: rc=0 it={st['it']} "
                      f"reward={st['mean_reward']} train_wall={st['train_wall_s']} s "
                      f"kernel_warmup={st['kernel_warmup_s']} s "
                      f"torch_peak_reserved={st['torch_peak_reserved_bytes']} bytes "
                      f"walk_evals={st['walk_evals']}", flush=True)
                (a.outdir / "progress.json").write_text(json.dumps(st, indent=2) + "\n")
                if a.backup_checkpoints:
                    (a.outdir / "policy.npz").write_bytes(
                        lease.fetch_file("~/go1job/out/policy.npz"))
                if st["finished"]:
                    break
            else:
                raise RuntimeError("training did not finish within 400 chunks")
            timing["train_roundtrip_s"] = round(time.monotonic() - t, 3)
            for name in ("policy.npz", "step0.npz", "short.npz", "curve.json"):
                data = lease.fetch_file(f"~/go1job/out/{name}")
                if not data:
                    raise RuntimeError(f"missing training output {name}")
                (a.outdir / name).write_bytes(data)
            summary = json.loads((a.outdir / "curve.json").read_text())
            print("training: " + json.dumps({k: v for k, v in summary.items()
                                             if k != "curve"}, sort_keys=True), flush=True)
            # This is a separately trained, real reward-sign counterfactual.
            negative = HERE / "examples/good/reward-flipped.npz"
            if not a.no_selftest:
                (a.outdir / negative.name).write_bytes(negative.read_bytes())
        if not a.no_selftest:
            t = time.monotonic()
            test = selftest_on_lease(lease, str(artifact),
                                    str(a.outdir / "selftest.json"), a.seeds)
            timing["selftest_s"] = round(time.monotonic() - t, 3)
            if not test["ok"]:
                raise RuntimeError("self-test failed")
        t = time.monotonic()
        rep = G.grade_on_lease(lease, str(artifact), a.seeds, 64, 500, 1.0,
                               trace=a.trace)
        verdict = checked_verdict(rep)
        timing["grade_completed"] = True
        timing["grade_s"] = round(time.monotonic() - t, 3)
        (a.outdir / "verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
        print("grade: rc=" + str(rep["rc"]) + f", {timing['grade_s']} s", flush=True)
        print(json.dumps(verdict, sort_keys=True), flush=True)
        if a.trace:
            for seed in a.seeds.split(","):
                data = lease.fetch_file(f"~/go1judge/traces/seed-{int(seed)}.npz")
                (a.outdir / f"seed-{int(seed)}.npz").write_bytes(data)
        rc = 0 if verdict["ok"] else 1
    finally:
        t = time.monotonic()
        if a.keep and sid:
            print(f"--keep: {sid}; delete via the API when finished", flush=True)
            lease.id = None
        lease.delete()
        timing["cleanup_s"] = round(time.monotonic() - t, 3)
        timing["total_s"] = round(time.monotonic() - total0, 3)
        (a.outdir / "timing.json").write_text(json.dumps(timing, indent=2) + "\n")
        (a.outdir / "lease-events.json").write_text(json.dumps(lease.events, indent=2) + "\n")
        print(f"total: {timing['total_s']} s; rc={rc}", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
