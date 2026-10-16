# Storyboard — `media/demo.mp4` (40.0 s, 1920×1080, 30 fps)

Cut in Remotion (`media/video/`, pinned `remotion@4.0.530`) from the real
motion clips `media/clips/*.mp4`. The clips are drawn frame-by-frame by
`media/make_clips.py` from `media/data/*.json`, which `make_data.py`
writes from *this run's* judge outputs — nothing is a still, nothing is
invented. ffmpeg only encodes.

| slot | time | fills the frame | source | overlay (Remotion HUD) |
|---|---|---|---|---|
| hook | 0–2.0 s | `clips/bode.mp4` mid-flight: all three sweeps drawn, the measurement cursor still scanning, the camera panning the plot | `data/sweep_good.json` (judge AC sweeps) | kinetic headline “AN AGENT DESIGNS A FILTER.” springs in word-by-word |
| input→output | 2–10 s | `clips/scope.mp4`: a dual-trace oscilloscope in roll mode — CH1 sine in cyan, CH2 filtered out in green, both channels scrolling every frame; three real `ngspice tran` segments 300 Hz → 1.4 kHz → 16 kHz (hard jumps inside the clip), V/div and TIME/div labels honest; the 16 kHz segment shows the settled mV-scale residual | `data/transient.json` (real `.tran` of the graded netlist, `V1 → SIN`, settled tail) | caption chips slide in: “input → output · a 1 V sine through the filter”, then “16 kHz in → the output is on the mV scale” |
| escalate | 10–14.3 s | `clips/term.mp4`: the judge’s own terminal output from this run — `selftest.sh` kills 9/9 mutants, `grade.sh` prints the verdict JSON — scrolling inside a terminal window, labelled `REPLAY · 8× speed` | `data/runlog.txt` (captured `tee` of the real commands in `make_media.sh`) | caption chip “the judge run in the sandbox, replayed” |
| escalate | 14.3–26 s | `clips/bode.mp4` from the top: the spec mask, then the nominal |v(out)| sweep drawing itself left-to-right with a pen dot, translucent fill and live `f= / |v(out)|=` readout, the closed-form oracle over it, the 1 MHz-GBW macro-model and a `GBW dev ≤ 0.150 dB` callout, then the measurement cursor sweeps the decades; a camera pans the plot while a measurement scan band sweeps continuously | `data/sweep_good.json` | caption chips: “the AC sweep draws itself against the spec mask”, “closed-form oracle + 1 MHz-GBW macro-model agree” |
| escalate | 26–34 s | `clips/mc.mp4`: all 100 seeded Monte-Carlo sweeps (R ±5 % / C ±10 %) streaming in over the relaxed mask while the `run n/100 · pass n` counter ticks; camera pan + scan band as in the bode shot | `data/mc_curves.json` (the judge’s own seeded perturbation sequence re-run) | caption chip “R ±5 % · C ±10 % — 100 seeded runs”; in-clip `100/100 PASS — ≥90 % gate met` banner |
| proof | 34–37.5 s | `clips/scope.mp4` still playing underneath (16 kHz residual rolling) | — | PASS badge springs in top-right; six gate rows (`mask`, `analytic`, `series`, `montecarlo`, `self-test`, `sweep`) slide in staggered carrying the verdict’s own numbers; judge chip top-left |
| end card | 37.5–40 s | static: `python3 run.py` in a bordered card, `cookbook/spice-filter · agent-next/sandbox`, `ngspice-39 · seed 20261014` | `data/video_props.json` | — |

Transitions: every hard cut rides a 3-frame bright flash (`CutFlash`) and
every clip plays under a slow sinusoidal camera drift (`CameraClip`), so
no two consecutive frames are identical before the end card.

Rules kept: no text-only frames, no still plots, no Ken-Burns — every
shot before the end card is a real moving clip; captions and the verdict
ride on top as HUD. Numbers: ripple 0.096 dB, stopband −56.14 dB, GBW
dev 0.150 dB, MC 100/100, kill rate 9/9 — all from `data/video_props.json`.
