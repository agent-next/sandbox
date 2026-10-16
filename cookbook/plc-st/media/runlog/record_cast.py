#!/usr/bin/env python3
"""Record the plc-st pipeline (the exact steps run.py streams in its sandbox)
as an asciinema v2 cast with real output bytes and real wall-clock timing.

Steps, each with live-streamed output:
  git clone --depth 1 <this repo> sandbox && cd sandbox/cookbook/plc-st
  bash judge/setup.sh        (fresh: ~/.plc-st is removed first -- real build)
  bash judge/selftest.sh
  bash judge/grade.sh examples/good/tank_ctrl.st --json /tmp/plc-st-verdict.json
  cat /tmp/plc-st-verdict.json

Writes media/runlog/pipeline.cast (git-ignored).
"""
import json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(HERE + "/../../../..")
OUT = os.path.join(HERE, "pipeline.cast")
WORK = os.path.join(HERE, "work")
PLC = os.path.join(WORK, "sandbox/cookbook/plc-st")

steps = [
    ("clone", "git clone --depth 1 file://" + REPO + " sandbox && cd sandbox/cookbook/plc-st", WORK),
    ("fresh", "rm -rf ~/.plc-st", WORK),
    ("setup", "bash judge/setup.sh", PLC),
    ("selftest", "bash judge/selftest.sh", PLC),
    ("grade", "bash judge/grade.sh examples/good/tank_ctrl.st --json /tmp/plc-st-verdict.json", PLC),
    ("verdict", "cat /tmp/plc-st-verdict.json", PLC),
]

os.makedirs(WORK, exist_ok=True)
events = []
t0 = time.time()

HOME = os.path.expanduser("~")

def scrub(text: str) -> str:
    """Make the cast machine-independent (and publishable): no home paths and
    no local clone URL, only the repo-relative command the README documents."""
    text = text.replace(HOME, "$HOME")
    text = text.replace("file://$HOME/w", "https://github.com/agent-next/sandbox")
    return text

def emit(text: str):
    events.append([round(time.time() - t0, 3), "o", scrub(text).replace("\n", "\r\n")])

fails = 0
for label, cmd, cwd in steps:
    emit(f"$ {cmd}\n")
    p = subprocess.Popen(["bash", "-c", cmd], cwd=cwd,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, errors="replace", bufsize=1)
    assert p.stdout is not None
    for line in p.stdout:
        emit(line.rstrip("\n") + "\n")
    rc = p.wait()
    if rc != 0:
        emit(f"[exit {rc}]\n")
        fails += 1
        print(f"step {label} exit {rc}", file=sys.stderr)
    print(f"[recorded] {label}: {time.time()-t0:.1f}s cumulative", flush=True)

with open(OUT, "w") as f:
    f.write(json.dumps({"version": 2, "width": 120, "height": 34,
                        "env": {"SHELL": "/bin/bash"}}) + "\n")
    for e in events:
        f.write(json.dumps(e) + "\n")

if fails:
    sys.exit(f"{fails} step(s) failed")
print(f"wrote {OUT}: {len(events)} events, {events[-1][0]:.1f}s of wall time")
