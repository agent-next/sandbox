#!/usr/bin/env python3
"""go1-walk demo: train a Go1 to walk on a 4 GiB GPU slice, then judge it.

    python3 cookbook/go1-walk/run.py [--vram 4] [--iters N] [--keep]
        [--skip-train ARTIFACT_DIR] [--selftest]

One command: creates a VRAM-slice lease over the agent-next REST API,
ships env.py/train.py/the Go1 model (the lease has no network), trains a
PPO policy with batched MuJoCo-Warp (~minutes), then grades the fresh
checkpoint with the judge's own held-out-seed simulation -- the judge
never reads a number the artifact claims. The lease is always destroyed
afterwards and the delete is confirmed by a 404.

--selftest additionally grades examples/good plus every judge/mutants.py
mutant on the same lease and reports the kill rate.
--skip-train grades an existing artifact directory instead of training.

Standard library only. Needs SBX_API_KEY (or E2B_API_KEY) in the env.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "judge"))
import grade as G  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

SHIP_FILES = [
    ("env.py", "env.py"),
    ("train.py", "train.py"),
    ("_eval.py", "judge/_eval.py"),
    ("go1_meshless.xml", "model/go1_meshless.xml"),
    ("train_config.json", "examples/good/train_config.json"),
]

SETUP_JOB = """
import base64, os, sys
ROOT = os.path.expanduser('~/go1job')
os.makedirs(os.path.join(ROOT, 'model'), exist_ok=True)
os.chdir(ROOT)
sys.path.insert(0, ROOT)
FILES = __PAYLOAD__
for name, b64 in FILES.items():
    sub = 'model' if name.endswith('.xml') else ''
    d = os.path.join(ROOT, sub)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), 'wb') as fh:
        fh.write(base64.b64decode(b64))
for _m in ('env', 'train', '_eval'):
    sys.modules.pop(_m, None)
import subprocess
v = {}
for mod in ('warp', 'mujoco', 'mujoco_warp', 'torch', 'numpy'):
    v[mod] = getattr(__import__(mod), '__version__', '?')
out = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total',
                      '--format=csv,noheader'],
                     capture_output=True, text=True, timeout=10)
report['versions'] = v
report['gpu'] = out.stdout.strip()
report['files'] = sorted(FILES)
"""

TRAIN_JOB = """
import json, os, subprocess, sys, time
os.chdir(os.path.expanduser('~/go1job'))
t0 = time.time()
proc = subprocess.run([sys.executable, 'train.py', '--config',
                       'train_config.json', '--out', 'out'],
                      capture_output=True, text=True, timeout=2400)
report['rc'] = proc.returncode
report['stdout_tail'] = proc.stdout[-6000:]
report['stderr_tail'] = proc.stderr[-2000:]
report['train_wall_s'] = round(time.time() - t0, 1)
if proc.returncode == 0:
    report['summary'] = json.load(open('out/curve.json'))
    report['policy_sha256'] = __import__('hashlib').sha256(
        open('out/policy.npz', 'rb').read()).hexdigest()
"""

EVAL_JOB = """
import json, os, subprocess, sys, time
os.chdir(os.path.expanduser('~/go1job'))
t0 = time.time()
proc = subprocess.run([sys.executable, '_eval.py'] + ARGS,
                      capture_output=True, text=True, timeout=1200)
report['rc'] = proc.returncode
report['stdout_tail'] = proc.stdout[-3000:]
report['stderr_tail'] = proc.stderr[-2000:]
report['eval_wall_s'] = round(time.time() - t0, 1)
try:
    report['verdict'] = json.load(open('verdict_out.json'))
except Exception as exc:
    report['verdict'] = None
    report['verdict_error'] = str(exc)
"""


def payload_b64():
    payload = {}
    for name, rel in SHIP_FILES:
        with open(os.path.join(HERE, rel), "rb") as fh:
            payload[name] = base64.b64encode(fh.read()).decode()
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vram", type=int, default=4)
    ap.add_argument("--iters", type=int, default=None,
                    help="override train_config.json iters (quick smoke)")
    ap.add_argument("--keep", action="store_true",
                    help="leave the lease up and print its id")
    ap.add_argument("--skip-train", metavar="ARTIFACT_DIR",
                    help="grade an existing local artifact instead of "
                         "training a new one")
    ap.add_argument("--selftest", action="store_true",
                    help="after grading, also grade good+mutants and print "
                         "the kill rate")
    ap.add_argument("--seeds", default="101,202,303")
    a = ap.parse_args()

    key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
    if not key:
        G.die("no API key: export SBX_API_KEY (or E2B_API_KEY)")

    total0 = time.monotonic()
    lease = G.Lease(key, a.vram)
    sid = None
    try:
        lease.__enter__()
        sid = lease.id
        print(f"[{time.monotonic()-total0:6.1f}s] created {sid} "
              f"({a.vram} GiB VRAM slice)", flush=True)

        t = time.monotonic()
        payload = payload_b64()
        if a.iters is not None:
            cfg = json.loads(base64.b64decode(
                payload["train_config.json"]))
            cfg["iters"] = a.iters
            payload["train_config.json"] = base64.b64encode(
                json.dumps(cfg).encode()).decode()
        code = SETUP_JOB.replace("__PAYLOAD__", repr(payload))
        res = lease.exec(code, 300)
        rep = res.get("report") or {}
        if res.get("ok") is not True:
            G.die(f"setup failed: {(res.get('stderr') or '')[-400:]}")
        print(f"[{time.monotonic()-total0:6.1f}s] shipped payload; "
              f"gpu={rep.get('gpu')} stack={rep.get('versions')}",
              flush=True)

        if a.skip_train:
            policy = open(os.path.join(a.skip_train, "policy.npz"),
                          "rb").read()
            up = ("import base64\n"
                  "open('~/go1job/policy_eval.npz'.replace('~',"
                  " __import__('os').path.expanduser('~')), 'wb')"
                  f".write(base64.b64decode({base64.b64encode(policy).decode()!r}))\n"
                  "report['shipped_policy'] = len(base64.b64decode("
                  f"{base64.b64encode(policy).decode()!r}))")
            res = lease.exec(up, 120)
            eval_args = ["--policy", "policy_eval.npz"]
        else:
            t = time.monotonic()
            res = lease.exec(TRAIN_JOB, 2500)
            rep = res.get("report") or {}
            print(f"[{time.monotonic()-total0:6.1f}s] training done "
                  f"(job wall {rep.get('train_wall_s')} s)", flush=True)
            if res.get("ok") is not True or rep.get("rc") != 0:
                G.die("training failed: "
                      + (rep.get("stderr_tail") or "")[-600:])
            s = rep.get("summary") or {}
            print(f"  env_steps={s.get('env_steps')} "
                  f"steps/s={s.get('steps_per_s')} "
                  f"iters={s.get('iters')}", flush=True)
            for e in s.get("walk_evals") or []:
                print(f"  walk check it {e['it']}: "
                      f"{e['forward_mps']} m/s upright {e['upright']}",
                      flush=True)
            eval_args = ["--policy", "out/policy.npz"]

        eval_args += ["--json", "verdict_out.json", "--seeds", a.seeds]
        code = EVAL_JOB.replace("ARGS", repr(eval_args))
        res = lease.exec(code, 1200)
        rep = res.get("report") or {}
        verdict = rep.get("verdict")
        if verdict is None:
            G.die("no verdict: " + json.dumps(rep, indent=1)[:1000])
        ok = verdict.get("ok") is True
        print(f"[{time.monotonic()-total0:6.1f}s] verdict: "
              f"{'PASS' if ok else 'FAIL'}", flush=True)
        for n, g in sorted((verdict.get("gates") or {}).items()):
            print(f"  {n}: {'pass' if g.get('pass') else 'FAIL'} "
                  f"({g.get('rule')}; measured {g.get('value')})",
                  flush=True)

        if a.selftest:
            print("selftest: grading good + mutants on the same lease",
                  flush=True)
            import subprocess as sp
            import tempfile
            tmp = tempfile.mkdtemp(prefix="go1-mut-")
            names = sp.run([sys.executable,
                            os.path.join(HERE, "judge", "mutants.py"),
                            os.path.join(HERE, "examples", "good"), tmp],
                           check=True, capture_output=True,
                           text=True).stdout.split()
            killed = 0
            for n in names:
                mdir = os.path.join(tmp, n)
                aj = os.path.join(mdir, "args.json")
                ms = 1.0
                if os.path.exists(aj):
                    ea = json.load(open(aj)).get("extra_args") or []
                    if "--mass-scale" in ea:
                        ms = float(ea[ea.index("--mass-scale") + 1])
                pol = open(os.path.join(mdir, "policy.npz"), "rb").read()
                b64 = base64.b64encode(pol).decode()
                lease.exec(
                    "import base64, os\n"
                    f"open(os.path.expanduser('~/go1job/mut.npz'), 'wb')"
                    f".write(base64.b64decode({b64!r}))\n"
                    "report['ok'] = True", 120)
                code = EVAL_JOB.replace(
                    "ARGS", repr(["--policy", "mut.npz", "--json",
                                  "verdict_out.json", "--seeds", a.seeds,
                                  "--mass-scale", str(ms)]))
                rep = (lease.exec(code, 1200).get("report") or {})
                v = rep.get("verdict")
                failed = [k for k, g in ((v or {}).get("gates") or {})
                          .items() if g.get("pass") is False]
                if failed:
                    killed += 1
                print(f"  mutant {n}: {'KILLED' if failed else 'SURVIVED'}"
                      f" ({', '.join(failed)})", flush=True)
            print(f"selftest kill rate: {killed}/{len(names)}", flush=True)

        print(f"total: {time.monotonic() - total0:.0f} s", flush=True)
        rc = 0 if ok else 1
    finally:
        if a.keep and sid:
            print(f"--keep: lease {sid} left running; delete it via the API",
                  flush=True)
            lease.id = None
        lease.__exit__(None, None, None)

    raise SystemExit(rc)


if __name__ == "__main__":
    main()
