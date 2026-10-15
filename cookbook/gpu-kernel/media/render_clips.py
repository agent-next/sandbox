#!/usr/bin/env python3
"""Turn the recorded judge-run capture (clips/cast.jsonl) into 30 fps motion
clips (clips/terminal.mp4) with a headless browser.

This is a screen recording of the run that record_clips.py performed: the
page replays the captured output lines at their captured timestamps (so
relative pacing is the run's own), sped up by --speed. The on-screen clock
and progress bar show the run's real elapsed time. ffmpeg only encodes the
frames this script captured — it builds no visuals.

    python3 render_clips.py [--speed 90]

Writes clips/terminal.mp4 (30 fps, 1920x1080, CRF 18) and prints the
real speed-up factor (total run seconds / clip seconds) for the "Nx speed"
label.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CLIPS = os.path.join(HERE, "clips")
CAST = os.path.join(CLIPS, "cast.jsonl")
OUT = os.path.join(CLIPS, "terminal.mp4")
FRAMES = os.path.join(CLIPS, ".termframes")

W, H, FPS = 1920, 1080, 30
MAX_LINES = 24

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;padding:0;background:#0d1117;width:1920px;height:1080px;
 overflow:hidden;font-family:'DejaVu Sans Mono',Menlo,Consolas,monospace}
#term{position:absolute;left:56px;right:470px;top:96px;bottom:150px;
 font-size:31px;line-height:42px;color:#e6edf3;white-space:pre}
#clock{position:absolute;right:64px;top:96px;font-size:44px;color:#79c0ff;
 text-align:right;line-height:60px}
#phase{position:absolute;right:64px;top:170px;font-size:30px;color:#8b949e;
 text-align:right}
#prompt{position:absolute;left:56px;top:34px;font-size:33px;color:#8b949e}
#bar{position:absolute;left:56px;right:64px;bottom:88px;height:26px;
 background:#161b22;border-radius:13px;overflow:hidden}
#fill{position:absolute;left:0;top:0;bottom:0;background:#388bfd;width:0%}
#barlabel{position:absolute;left:56px;bottom:132px;font-size:28px;color:#8b949e}
.g{color:#56d364}.r{color:#ff7b72}.b{color:#79c0ff}.d{color:#8b949e}
</style></head><body>
<div id="prompt"></div><div id="term"></div>
<div id="clock"></div><div id="phase"></div>
<div id="barlabel"></div><div id="bar"><div id="fill"></div></div>
<script>
const EVENTS = __EVENTS__;
const TOTAL = __TOTAL__;
const PROMPTS = __PROMPTS__;
function esc(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;")}
function cls(line){
 if(/FAIL|SURVIVED|error|Error|Traceback/i.test(line))return "r";
 if(/PASS|killed|ok|determinism: OK/.test(line))return "g";
 if(/^selftest:|^setup.sh:|Collecting|Installing|Downloading|Using cached/.test(line))return "b";
 if(/^\\$/.test(line))return "d";
 return "";}
window.render = (t) => {
  const shown = [];
  let prompt = PROMPTS[0] ? PROMPTS[0].cmd : "";
  for (const e of EVENTS){
    if (e.t <= t) shown.push(e.data);
    else break;
  }
  for (const p of PROMPTS) if (p.t <= t) prompt = p.cmd;
  document.getElementById("prompt").textContent = prompt;
  const tail = shown.slice(-__MAX_LINES__);
  document.getElementById("term").innerHTML =
    tail.map(l => `<span class="${cls(l)}">${esc(l)}</span>`).join("\\n");
  document.getElementById("clock").innerHTML =
    `t = ${t.toFixed(1)} s<br><span style="font-size:30px;color:#8b949e">` +
    `${__SPEED__}&times; speed</span>`;
  const phase = t < __T1__ ? "setup" : (t < __T2__ ? "selftest" : "grade");
  document.getElementById("phase").textContent = "phase: " + phase;
  document.getElementById("barlabel").textContent =
    "run progress (real elapsed " + t.toFixed(0) + " / " + TOTAL.toFixed(0) + " s)";
  document.getElementById("fill").style.width = (100*t/TOTAL) + "%";
};
</script></body></html>"""


def die(msg):
    print(f"render_clips.py: {msg}", file=sys.stderr)
    raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser()
    # the recorded run is ~940 s; 90x compresses it to ~10.5 s of footage in
    # which every phase (setup, 11 mutant kills, determinism, grade) still
    # appears
    ap.add_argument("--speed", type=float, default=90.0)
    args = ap.parse_args()
    if not os.path.isfile(CAST):
        die("missing clips/cast.jsonl; run record_clips.py first")
    events = []
    with open(CAST) as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    if len(events) < 20:
        die(f"cast.jsonl has only {len(events)} events; not enough run output")

    total = events[-1]["t"]
    # record_clips.py writes each phase's real command line into the cast as a
    # "$ ..." prompt; the phases are exactly those three commands
    prompts = [{"t": e["t"], "cmd": e["data"]}
               for e in events if e["data"].startswith("$ ")]
    t1 = next((p["t"] for p in prompts if "selftest.sh" in p["cmd"]), None)
    t2 = next((p["t"] for p in prompts if "grade.sh" in p["cmd"]), None)
    if len(prompts) < 3 or t1 is None or t2 is None:
        die("cast.jsonl does not show all three phases (setup/selftest/grade)")

    clip_s = total / args.speed
    frames = int(clip_s * FPS)
    html = (PAGE.replace("__EVENTS__", json.dumps(events))
                .replace("__TOTAL__", f"{total:.1f}")
                .replace("__PROMPTS__", json.dumps(prompts))
                .replace("__MAX_LINES__", str(MAX_LINES))
                .replace("__SPEED__", str(int(args.speed))
                         if args.speed == int(args.speed)
                         else str(args.speed))
                .replace("__T1__", f"{t1:.1f}").replace("__T2__", f"{t2:.1f}"))

    if os.path.isdir(FRAMES):
        shutil.rmtree(FRAMES)
    os.makedirs(FRAMES)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-device-scale-factor=1"])
        page = browser.new_page(viewport={"width": W, "height": H})
        page.set_content(html)
        page.wait_for_timeout(300)
        for i in range(frames):
            t = (i + 1) * args.speed / FPS
            page.evaluate(f"render({t:.4f})")
            page.screenshot(path=os.path.join(FRAMES, f"f{i:05d}.png"),
                            clip={"x": 0, "y": 0, "width": W, "height": H})
        browser.close()

    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
         "-i", os.path.join(FRAMES, "f%05d.png"),
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", OUT],
        capture_output=True, text=True)
    shutil.rmtree(FRAMES, ignore_errors=True)
    if proc.returncode != 0:
        die(f"ffmpeg encode failed: {proc.stderr.strip()[-400:]}")
    print(f"render_clips.py: wrote {OUT} ({frames} frames @ {FPS} fps, "
          f"{clip_s:.1f} s, {args.speed:g}x speed, run was {total:.0f} s)")


if __name__ == "__main__":
    main()
