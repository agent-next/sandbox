#!/usr/bin/env python3
"""Record the real gpu-kernel judge run in this sandbox for the demo video.

This is the demo's documented local path (README.md: "To try the judge
locally on a CPU-only Linux box"): setup.sh -> selftest.sh -> grade.sh.
Every byte shown in the video is real output of these commands, captured
with timestamps; nothing is scripted or typed by hand.

Writes into media/clips/ (gitignored):

  cast.jsonl     one JSON event per output chunk: {"t": s, "data": text}
  timings.jsonl  real per-iteration ms of the good kernel and torch eager
                 per correctness case (TRITON_INTERPRET=1, like --cpu-check)
  row.json       one real input row and its softmax, from the real kernel
  racedata.json  per-mutant wall seconds parsed from the selftest capture
                 and the good-kernel verdict of this run

Exit is non-zero (naming the missing piece) unless the judge PASSes the
known-good kernel and kills every mutant — the same rule run.py applies.
"""

import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DEMO = os.path.join(HERE, "..")
JUDGE = os.path.join(DEMO, "judge")
CLIPS = os.path.join(HERE, "clips")
VENV_PY = os.path.join(os.path.expanduser("~"), ".venvs", "gpu-kernel", "bin", "python")

MUTANT_RE = re.compile(r"selftest: mutant ([\w.]+): (killed|SURVIVED)")


def die(msg):
    print(f"record_clips.py: {msg}", file=sys.stderr)
    raise SystemExit(1)


def record(argv, cast, t0, cwd=REPO):
    """Run argv for real, streaming its output into cast with timestamps.

    t0 is the whole recording's clock, so every phase lands on one shared
    timeline; the command itself is written into the cast as a "$ ..." prompt
    line so the replay shows what really ran, in order.
    """
    cast.write(json.dumps({"t": round(time.monotonic() - t0, 3),
                           "data": "$ " + " ".join(argv)}) + "\n")
    proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    lines = []
    for line in proc.stdout:
        now = time.monotonic() - t0
        line = line.rstrip("\n")
        cast.write(json.dumps({"t": round(now, 3), "data": line}) + "\n")
        lines.append((now, line))
    rc = proc.wait()
    return rc, time.monotonic() - t0, lines


def time_iterations():
    """Time the real kernel and torch eager, per case, per iteration."""
    code = r"""
import json, os, sys, time
os.environ["TRITON_INTERPRET"] = "1"      # exactly the judge's --cpu-check
sys.path.insert(0, %r)
import importlib.util
spec = importlib.util.spec_from_file_location(
    "good", os.path.join(%r, "examples", "good", "kernel.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
import _grade
import torch
_grade.torch = torch   # _grade binds torch inside main(); bind it here too

with open(%r, "w") as sink:
    for i, (rows, cols, dist, seed) in enumerate(_grade.CPU_CASES):
        x = _grade.make_input(dist, rows, cols, seed)
        iters = 4 if cols >= 1024 else 8
        for j in range(iters):
            t0 = time.perf_counter(); mod.softmax(x); k = time.perf_counter() - t0
            t0 = time.perf_counter(); torch.softmax(x, dim=1); e = time.perf_counter() - t0
            rec = {"case": i, "shape": [rows, cols], "dist": dist, "seed": seed,
                   "iter": j, "kernel_ms": round(k * 1e3, 4),
                   "eager_ms": round(e * 1e3, 4)}
            sink.write(json.dumps(rec) + "\n"); sink.flush()
            print(f"case {i} ({rows}x{cols}/{dist}) iter {j}: "
                  f"kernel {rec['kernel_ms']:.2f} ms eager {rec['eager_ms']:.3f} ms",
                  flush=True)
    # one real row for the input->output shot
    x = _grade.make_input("randn", 37, 65, 5)
    y = mod.softmax(x)
    json.dump({"in": x[0].tolist(), "out": y[0].tolist()},
              open(%r, "w"))
print("timing driver done")
""" % (JUDGE, DEMO, os.path.join(CLIPS, "timings.jsonl"),
       os.path.join(CLIPS, "row.json"))
    rc = subprocess.call([VENV_PY, "-c", code], cwd=REPO)
    if rc != 0:
        die("timing driver failed")


def main():
    os.makedirs(CLIPS, exist_ok=True)
    for tool in ("ffmpeg",):
        if not subprocess.run(["sh", "-c", f"command -v {tool}"],
                              capture_output=True).stdout:
            die(f"{tool} not found on PATH")
    if not os.path.isfile(VENV_PY):
        die("judge venv missing; run bash cookbook/gpu-kernel/judge/setup.sh")

    cast_path = os.path.join(CLIPS, "cast.jsonl")
    t0 = time.monotonic()
    with open(cast_path, "w") as cast:
        # argv strings are what the replay shows on screen, so run the phases
        # from the demo dir where the real commands are short enough to fit
        print("record_clips.py: recording judge/setup.sh", flush=True)
        rc, dt_setup, _ = record(["bash", "judge/setup.sh"], cast, t0, cwd=DEMO)
        if rc != 0:
            die(f"setup.sh exit {rc}")

        print("record_clips.py: recording judge/selftest.sh "
              "(grades 11 mutants for real; takes a while)", flush=True)
        rc, dt_self, self_lines = record(
            ["bash", "judge/selftest.sh"], cast, t0, cwd=DEMO)
        if rc != 0:
            die(f"selftest.sh exit {rc}")

        print("record_clips.py: recording judge/grade.sh on the good kernel",
              flush=True)
        verdict = os.path.join(CLIPS, "verdict.json")
        rc, dt_grade, _ = record(
            ["bash", "judge/grade.sh", "examples/good/kernel.py",
             "--json", "media/clips/verdict.json"],
            cast, t0, cwd=DEMO)
        if rc != 0:
            die(f"grade.sh exit {rc}")

    print("record_clips.py: timing the kernel per case, per iteration",
          flush=True)
    time_iterations()

    # real per-mutant wall seconds, from the captured selftest timestamps
    marks = [(t, m.group(1), m.group(2))
             for t, line in self_lines if (m := MUTANT_RE.search(line))]
    mutants = []
    for k, (t, name, outcome) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else dt_self
        mutants.append({"name": name, "killed": outcome == "killed",
                        "wall_s": round(end - t, 1)})

    with open(verdict) as fh:
        v = json.load(fh)
    gates_ok = all(g.get("pass") for g in v["gates"].values()) and v["judge_intact"]
    killed = sum(1 for m in mutants if m["killed"])

    racedata = {
        "wall": {"setup_s": round(dt_setup, 1), "selftest_s": round(dt_self, 1),
                 "grade_s": round(dt_grade, 1)},
        "mutants": mutants,
        "verdict": {"mode": v["mode"], "gates": {k: g["pass"]
                                                 for k, g in v["gates"].items()},
                    "judge_intact": v["judge_intact"],
                    "worst": v["gates"]["correctness"]["worst"],
                    "cases": v["gates"]["correctness"]["cases"]},
    }
    with open(os.path.join(CLIPS, "racedata.json"), "w") as fh:
        json.dump(racedata, fh, indent=2)

    if not gates_ok:
        die("this run's verdict did not pass every gate")
    if killed != len(mutants) or not mutants:
        die(f"selftest kill rate {killed}/{len(mutants)}; not recording a "
            "broken judge")
    print(f"record_clips.py: ok — verdict PASS, {killed}/{len(mutants)} "
          f"mutants killed, selftest {dt_self:.0f} s")


if __name__ == "__main__":
    main()
