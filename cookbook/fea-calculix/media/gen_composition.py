#!/usr/bin/env python3
"""Generate media/video/index.html -- the HyperFrames composition -- from
this run's real judge outputs, and stage the clips it composes.

Every number written into the composition is read here from
  data/verdicts/good.json          (judge/grade.sh examples/good --seed 42)
  data/verdicts/overload-10x.json  (the killed mutant)
  data/selftest.txt                (kill rate line)
  work/run_logs/timing.json        (measured wall seconds of this run's
                                    setup/selftest/grade -- sets the "Nx"
                                    replay badge together with terminal.mp4's
                                    length)
Nothing is typed by hand; if a file is missing or a gate flipped, this
script fails instead of shipping a number the run didn't produce.

Also copies media/clips/*.mp4 -> media/video/assets/clips/ (the
HyperFrames project root is media/video/, so footage must live under it;
assets/clips/ is git-ignored -- clips/ is the canonical git-ignored home).
"""
import json
import os
import re
import shutil
import sys

MEDIA = os.path.dirname(os.path.abspath(__file__))
VIDEO = os.path.join(MEDIA, "video")
CLIPS = os.path.join(MEDIA, "clips")
DST = os.path.join(VIDEO, "assets", "clips")

FPS = 30
W, H = 1920, 1080
BG = "#0d1117"
FG = "#e6edf3"
DIM = "#8b949e"
ACCENT = "#58a6ff"
GREEN = "#3fb950"
RED = "#f85149"
MONO = "ui-monospace, 'DejaVu Sans Mono', monospace"
SANS = "'DejaVu Sans', sans-serif"

# ---- timeline (seconds) ----------------------------------------------------
T_HERO_END = 1.9
T_RAMP_END = 8.9
T_CLOSE_END = 14.4
T_TERM_END = 18.9
T_OVER_END = 23.9
T_PROOF_END = 28.4
T_END = 30.9          # 2.5 s static end card


def ease(t):
    return t * t * (3 - 2 * t)


def counter_steps(el, fmt, v0, v1, t0, t1, every=1.0 / 30):
    """GSAP set() steps so the rendered number counts up under scrubbing."""
    out = []
    n = max(2, int((t1 - t0) / every))
    for i in range(n + 1):
        t = t0 + (t1 - t0) * i / n
        v = v0 + (v1 - v0) * ease(i / n)
        out.append(f'  tl.set("{el}", {{textContent: {json.dumps(fmt(v))}}},'
                   f' {t:.3f});')
    return "\n".join(out)


def fmt_n(v):
    return f"{v:,.0f} N".replace(",", " ")


def main():
    good = json.load(open(os.path.join(MEDIA, "data", "verdicts",
                                       "good.json")))
    ov = json.load(open(os.path.join(MEDIA, "data", "verdicts",
                                     "overload-10x.json")))
    if good["verdict"] != "PASS":
        sys.exit("good.json verdict is not PASS -- refusing to compose")
    if ov["verdict"] != "FAIL":
        sys.exit("overload-10x.json verdict is not FAIL")
    gm, om = good["metrics"], ov["metrics"]

    st = open(os.path.join(MEDIA, "data", "selftest.txt")).read()
    mk = re.search(r"kill rate: (\d+)/(\d+)", st)
    if not mk:
        sys.exit("kill-rate line not found in selftest.txt")
    kills, mutants = mk.group(1), mk.group(2)

    timing = json.load(open(os.path.join(MEDIA, "work", "run_logs",
                                         "timing.json")))
    real_s = sum(float(timing[k + "_s"]) for k in
                 ("setup", "selftest", "grade"))
    term_s = T_TERM_END - T_CLOSE_END
    nx = round(real_s / term_s)

    # stage the clips inside the project root
    os.makedirs(DST, exist_ok=True)
    for c in ("hero", "ramp", "closeup", "terminal", "overload", "proof"):
        src = os.path.join(CLIPS, c + ".mp4")
        if not os.path.exists(src):
            sys.exit(f"missing clip {src} -- run render_clips.py first")
        shutil.copy2(src, os.path.join(DST, c + ".mp4"))

    sig = gm["sigma_mpa"]          # 138.241
    de = gm["delta_mm"]            # 7.7221
    allow = 250.0 / 1.5            # spec: 166.7 MPa
    load_n = 1000                  # spec tip load (SPEC.md)
    ov_sig, ov_de = om["sigma_mpa"], om["delta_mm"]

    # percentages verbatim from the judge's own gate detail strings
    vd = good["gates"]["verification"]["detail"]
    mv = re.search(r"\(([+-][0-9.]+)%.*?\(([+-][0-9.]+)%", vd)
    if not mv:
        sys.exit("could not parse verification detail: " + vd)
    ver_delta_pct, ver_sigma_pct = mv.group(1), mv.group(2)
    cd = good["gates"]["convergence"]["detail"]
    mc = re.search(r"deflection change ([0-9.]+)%, stress change "
                   r"([0-9.]+)%", cd)
    if not mc:
        sys.exit("could not parse convergence detail: " + cd)
    con_delta_pct, con_sigma_pct = mc.group(1), mc.group(2)

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>fea-calculix demo</title>
<script src="assets/gsap.min.js"></script>
<style>
  body, html {{ margin:0; padding:0; width:{W}px; height:{H}px;
    overflow:hidden; background:{BG}; }}
  #root {{ position:relative; width:{W}px; height:{H}px; overflow:hidden;
    font-family:{SANS}; color:{FG}; }}
  .clip {{ position:absolute; }}
  .fill {{ top:0; left:0; width:{W}px; height:{H}px; object-fit:cover; }}
  .tag {{ position:absolute; top:34px; left:44px; font:600 22px {MONO};
    color:{DIM}; letter-spacing:2px; }}
  .tag b {{ color:{FG}; }}
  .cap {{ position:absolute; left:60px; bottom:140px; font:800 64px {SANS};
    color:{FG}; text-shadow:0 4px 24px rgba(0,0,0,.8); }}
  .cap .word {{ display:inline-block; }}
  .hud {{ position:absolute; left:60px; bottom:52px; font:500 30px {MONO};
    color:{FG}; background:rgba(1,4,9,.72); border:1px solid #30363d;
    border-radius:12px; padding:14px 22px; }}
  .hud .lab {{ color:{DIM}; }}
  .hud .ok {{ color:{GREEN}; }}
  #badge {{ position:absolute; top:110px; right:70px; width:640px;
    background:rgba(1,4,9,.85); border:2px solid {GREEN}; border-radius:18px;
    padding:26px 30px; font-family:{MONO}; }}
  #badge .pass {{ font:800 54px {MONO}; color:{GREEN}; }}
  #badge .row {{ font:500 25px {MONO}; color:{FG}; margin-top:12px;
    display:flex; justify-content:space-between; gap:18px; }}
  #badge .row .v {{ color:{ACCENT}; }}
  #badge .row .st {{ color:{GREEN}; }}
  #endcard {{ position:absolute; inset:0; background:{BG};
    display:flex; flex-direction:column; align-items:center;
    justify-content:center; gap:34px; }}
  #endcard .t1 {{ font:800 84px {SANS}; color:{FG}; }}
  #endcard .t2 {{ font:600 44px {MONO}; color:{BG}; background:{GREEN};
    padding:18px 44px; border-radius:14px; }}
  #endcard .t3 {{ font:400 26px {MONO}; color:{DIM}; }}
</style></head>
<body>
<div id="root" data-composition-id="root" data-width="{W}" data-height="{H}"
     data-start="0" data-duration="{T_END}">

  <!-- 0-1.9 hero: finished result, moving, fills the frame -->
  <video id="v-hero" class="clip fill" src="assets/clips/hero.mp4" muted
         playsinline data-start="0" data-duration="{T_HERO_END}"
         data-playback-rate="1.35"
         style="filter:saturate(1.15)"></video>

  <!-- 1.9-8.9 ramp: input -> output, load 0 -> {fmt_n(load_n)} -->
  <video id="v-ramp" class="clip fill" src="assets/clips/ramp.mp4" muted
         playsinline data-start="{T_HERO_END}" data-media-start="1.0"
         data-duration="{T_RAMP_END - T_HERO_END}"
         style="filter:brightness(1.35) saturate(1.1)"></video>

  <!-- 8.9-14.4 closeup: camera dives onto the clamped wall -->
  <video id="v-close" class="clip fill" src="assets/clips/closeup.mp4" muted
         playsinline data-start="{T_RAMP_END}"
         data-duration="{T_CLOSE_END - T_RAMP_END}" data-playback-rate="1.3"
         style="filter:saturate(1.3) contrast(1.08)"></video>

  <!-- 14.4-18.9 terminal: real console replay, over still-moving footage -->
  <video id="v-bgterm" class="clip fill" src="assets/clips/ramp.mp4" muted
         playsinline data-start="{T_CLOSE_END}" data-media-start="8.0"
         data-duration="{T_TERM_END - T_CLOSE_END}" data-playback-rate="1.25"
         style="filter:brightness(.28) saturate(.6)"></video>
  <video id="v-term" class="clip" src="assets/clips/terminal.mp4" muted playsinline
         data-start="{T_CLOSE_END}"
         data-duration="{T_TERM_END - T_CLOSE_END}"
         style="position:absolute; left:50%; top:50%; width:1420px;
                height:799px; transform:translate(-50%,-50%);
                border-radius:14px; box-shadow:0 30px 90px rgba(0,0,0,.7);
                border:1px solid #30363d; object-fit:cover"></video>

  <!-- 18.9-23.9 overload: the mutant's own field under 10x load -->
  <video id="v-over" class="clip fill" src="assets/clips/overload.mp4" muted
         playsinline data-start="{T_TERM_END}"
         data-duration="{T_OVER_END - T_TERM_END}" data-playback-rate="1.35"
         style="filter:brightness(1.45) saturate(1.6)"></video>

  <!-- 23.9-28.4 proof: HUD + PASS over still-playing footage -->
  <video id="v-proof" class="clip fill" src="assets/clips/proof.mp4" muted
         playsinline data-start="{T_OVER_END}"
         data-duration="{T_PROOF_END - T_OVER_END}" data-playback-rate="1.4"
         style="filter:brightness(1.7) saturate(1.2)"></video>

  <div class="clip tag" data-start="0" data-duration="{T_PROOF_END}">
    <b>fea-calculix</b> &middot; real sandbox run
  </div>

  <!-- kinetic headline over the hero -->
  <div class="clip cap" id="cap-hero" data-start="0" data-duration="{T_HERO_END}">
    <span class="word">1000&nbsp;N</span> <span class="word">on</span>
    <span class="word">a</span> <span class="word">1&nbsp;m</span>
    <span class="word">cantilever.</span>
  </div>

  <!-- ramp HUD: load + deflection counters -->
  <div class="clip hud" id="hud-ramp" data-start="{T_HERO_END}"
       data-duration="{T_RAMP_END - T_HERO_END}">
    <span class="lab">load</span> <span id="ct-load">0 N</span><br>
    <span class="lab">tip &delta;</span> <span id="ct-delta">0.00 mm</span>
    <span class="lab">&nbsp;&nbsp;limit</span> 10.00 mm
  </div>
  <div class="clip cap" id="cap-ramp" data-start="{T_HERO_END}"
       data-duration="3.2">
    <span class="word">beam.inp</span> <span class="word">&rarr;</span>
    <span class="word">ccx</span> <span class="word">field</span>
  </div>

  <!-- closeup HUD: wall stress counter -->
  <div class="clip hud" id="hud-close" data-start="{T_RAMP_END}"
       data-duration="{T_CLOSE_END - T_RAMP_END}">
    <span class="lab">&sigma;<sub>wall</sub></span>
    <span id="ct-sigma">0.0 MPa</span>
    <span class="lab">&nbsp;&nbsp;allowable</span> {allow:.1f} MPa
  </div>
  <div class="clip cap" id="cap-close" data-start="{T_RAMP_END}"
       data-duration="3.0">
    <span class="word">the</span> <span class="word">stress</span>
    <span class="word">the</span> <span class="word">judge</span>
    <span class="word">measures</span>
  </div>

  <!-- terminal caption -->
  <div class="clip cap" id="cap-term" data-start="{T_CLOSE_END}"
       data-duration="2.6" style="left:60px; bottom:60px; font-size:44px">
    <span class="word">the</span> <span class="word">sandbox</span>
    <span class="word">run,</span> <span class="word">replayed</span>
    <span class="word">{nx}&times;</span>
  </div>

  <!-- overload HUD -->
  <div class="clip hud" id="hud-over" data-start="{T_TERM_END}"
       data-duration="{T_OVER_END - T_TERM_END}"
       style="border-color:{RED}">
    <span class="lab">10&times; overload</span>
    <span id="ct-ovsig">0 MPa</span><br>
    <span class="lab">tip &delta;</span> <span id="ct-ovde">0.0 mm</span>
    <span style="color:{RED}">&nbsp;&nbsp;judge: {ov["verdict"]}</span>
  </div>
  <div class="clip cap" id="cap-over" data-start="{T_TERM_END}"
       data-duration="3.0">
    <span class="word">push</span> <span class="word">it</span>
    <span class="word">10&times;</span> <span class="word">&mdash;</span>
    <span class="word">still</span> <span class="word">caught</span>
  </div>

  <!-- proof: PASS badge + gate rows over the still-playing field -->
  <div id="badge" class="clip" data-start="{T_OVER_END}"
       data-duration="{T_PROOF_END - T_OVER_END}">
    <div class="pass">{good["verdict"]}</div>
    <div class="row" id="br1"><span>verification vs Euler&ndash;Bernoulli</span>
      <span class="v">{ver_delta_pct}% / {ver_sigma_pct.replace("-", "&minus;")}%</span>
      <span class="st">&#10003;</span></div>
    <div class="row" id="br2"><span>mesh convergence 4&rarr;2 mm</span>
      <span class="v">{con_delta_pct}% / {con_sigma_pct}%</span>
      <span class="st">&#10003;</span></div>
    <div class="row" id="br3"><span>&sigma; {sig:.1f} &le; {allow:.1f} MPa
      &middot; &delta; {de:.2f} &le; 10.00 mm</span>
      <span class="v"></span><span class="st">&#10003;</span></div>
    <div class="row" id="br4"><span>self-test: mutants killed</span>
      <span class="v">{kills}/{mutants}</span>
      <span class="st">&#10003;</span></div>
  </div>

  <!-- static end card: last 2.5 s -->
  <div id="endcard" class="clip" data-start="{T_PROOF_END}"
       data-duration="{T_END - T_PROOF_END}">
    <div class="t1">cantilever beam &mdash; {good["verdict"]}</div>
    <div class="t2">python3 run.py</div>
    <div class="t3">cookbook/fea-calculix &middot; CalculiX ccx + gmsh in a
      disposable sandbox</div>
  </div>

  <!-- single-frame flash cuts at the hard joins (33 ms each) -->
  <div id="flash" class="clip fill" data-start="0" data-duration="{T_END}"
       style="background:{FG}; opacity:0; pointer-events:none"></div>

<script>
const tl = gsap.timeline({{ paused: true }});

/* kinetic headline: words slide up in sequence, then out */
document.querySelectorAll("#cap-hero .word").forEach((w, i) => {{
  tl.fromTo(w, {{opacity: 0, y: 60}},
            {{opacity: 1, y: 0, duration: .34, ease: "power3.out"}},
            .25 + i * .13);
}});
tl.to("#cap-hero", {{opacity: 0, y: -40, duration: .3, ease: "power2.in"}},
      {T_HERO_END - 0.35});

/* per-segment captions: same kinetic slide-in */
function caption(sel, t0, hold) {{
  document.querySelectorAll(sel + " .word").forEach((w, i) => {{
    tl.fromTo(w, {{opacity: 0, y: 44}},
              {{opacity: 1, y: 0, duration: .3, ease: "power3.out"}},
              t0 + .15 + i * .09);
  }});
  tl.to(sel, {{opacity: 0, duration: .25, ease: "power2.in"}},
        t0 + hold);
}}
caption("#cap-ramp", {T_HERO_END}, 3.0);
caption("#cap-close", {T_RAMP_END}, 2.8);
caption("#cap-term", {T_CLOSE_END}, 2.4);
caption("#cap-over", {T_TERM_END}, 2.8);

/* HUD entrances: slide up, stay */
for (const [sel, t0] of [["#hud-ramp", {T_HERO_END}],
                         ["#hud-close", {T_RAMP_END}],
                         ["#hud-over", {T_TERM_END}]]) {{
  tl.fromTo(sel, {{opacity: 0, y: 60}},
            {{opacity: 1, y: 0, duration: .4, ease: "power3.out"}},
            t0 + .1);
}}

/* counting HUD numbers -- real values, stepped under the scrub head */
{counter_steps("#ct-load", fmt_n, 0, load_n, T_HERO_END + 0.5,
               T_RAMP_END - 0.6)}
{counter_steps("#ct-delta", lambda v: "%.2f mm" % v, 0, de,
               T_HERO_END + 0.5, T_RAMP_END - 0.6)}
{counter_steps("#ct-sigma", lambda v: "%.1f MPa" % v, 0, sig,
               T_RAMP_END + 0.4, T_CLOSE_END - 0.7)}
{counter_steps("#ct-ovsig", lambda v: f"{v:,.0f} MPa".replace(",", " "),
               0, ov_sig, T_TERM_END + 0.4, T_OVER_END - 0.8)}
{counter_steps("#ct-ovde", lambda v: "%.1f mm" % v, 0, ov_de,
               T_TERM_END + 0.4, T_OVER_END - 0.8)}

/* slow push-in on each clip: the shot keeps drifting, never frozen */
for (const [sel, t0, dur, s1] of [
    ["#v-hero", 0, {T_HERO_END}, 1.22],
    ["#v-ramp", {T_HERO_END}, {T_RAMP_END - T_HERO_END}, 1.16],
    ["#v-close", {T_RAMP_END}, {T_CLOSE_END - T_RAMP_END}, 1.15],
    ["#v-bgterm", {T_CLOSE_END}, {T_TERM_END - T_CLOSE_END}, 1.15],
    ["#v-over", {T_TERM_END}, {T_OVER_END - T_TERM_END}, 1.18],
    ["#v-proof", {T_OVER_END}, {T_PROOF_END - T_OVER_END}, 1.18]]) {{
  tl.fromTo(sel, {{scale: 1.0}}, {{scale: s1, duration: dur,
                                  ease: "none"}}, t0);
}}

/* terminal window pushes in over the dimmed, still-playing field */
tl.fromTo("#v-term", {{scale: .86, opacity: 0}},
          {{scale: 1, opacity: 1, duration: .45, ease: "power3.out"}},
          {T_CLOSE_END});
tl.to("#v-term", {{scale: 1.06, opacity: 0, duration: .3,
                  ease: "power2.in"}}, {T_TERM_END - 0.3});

/* PASS badge drops in; gate rows slide in one by one */
tl.fromTo("#badge", {{opacity: 0, y: -70}},
          {{opacity: 1, y: 0, duration: .5, ease: "power3.out"}},
          {T_OVER_END + 0.25});
["#br1", "#br2", "#br3", "#br4"].forEach((r, i) => {{
  tl.fromTo(r, {{opacity: 0, x: 90}},
            {{opacity: 1, x: 0, duration: .35, ease: "power3.out"}},
            {T_OVER_END} + 0.7 + i * 0.4);
}});

/* flash cuts: one bright frame over each hard join */
for (const t of [{T_RAMP_END}, {T_TERM_END}, {T_OVER_END},
                 {T_PROOF_END}]) {{
  tl.set("#flash", {{opacity: .85}}, t);
  tl.set("#flash", {{opacity: 0}}, t + 0.034);
}}

/* keep the top tag subtly alive */
tl.to(".tag", {{opacity: .55, duration: 1.2, ease: "sine.inOut",
                yoyo: true, repeat: -1}}, 0);

window.__timelines = window.__timelines || {{}};
window.__timelines["root"] = tl;
</script>
</div></body></html>
"""

    out = os.path.join(VIDEO, "index.html")
    with open(out, "w") as f:
        f.write(html)
    print(f"wrote {out} ({len(html)} bytes); terminal replay {nx}x "
          f"({real_s:.0f}s real / {term_s:.1f}s)")


if __name__ == "__main__":
    main()
