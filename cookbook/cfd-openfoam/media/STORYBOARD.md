# STORYBOARD — cfd-openfoam demo.mp4 (27.5 s, 1920x1080, 30 fps)

Planned before the cut; judged against it. Every shot before the end card
is moving solver output — the |U| field of the real icoFoam cavity run
(judge --trace, seed 42) with glowing tracer particles advected through the
interpolated U field, or the scrolling log of this run's own judge calls.
Numbers on screen come from media/judge_runs/replay/verdicts|mutants via
media/clips/data.json — nothing invented.

Transitions: every boundary is a hard cut plus a 2-frame orange accent
flash (the palette's ORANGE) — a stinger transition. The dark-ink dips of
the first cut scored below the scene-detection threshold because the
footage is itself dark; the bright accent flash scores >= 0.9 going in.

Field clips render at 640x360 and are cover-fit into the 1080p frame: soft
glow tracers over the smooth field keep the crf 18 encode under 8 MiB —
hundreds of hard-edged particles do not fit the bitrate budget.

| Slot | Time | Frame contents | Footage (source) | Overlay |
| --- | --- | --- | --- | --- |
| hook | 0–2 s | converged cavity field, particles streaming, slow push-in, fills frame | `clips/hook.mp4` — |U| at t=30 s, 60 RK2 glow tracers, camera push 0.56→0.50 | kicker: "lid-driven cavity · Re=100 · OpenFOAM 1912 · icoFoam" |
| input→output | 2–8 s | the six case files slide in while the field spins up from rest behind them | `clips/develop.mp4` — |U| t=0→30 s interpolated between the 60 saved snapshots, 45 tracers | input file list (0/U, 0/p, transportProperties, blockMeshDict, controlDict, fvSolution); "output" tag |
| escalate: close-up | 8–12.5 s | camera dives into the top corner vortex and sweeps the lid | `clips/closeup.mp4` — |U| t=18→30 s, viewport (0.50,0.70,0.24)→(0.42,0.84,0.155)→(0.58,0.74,0.19), 50 tracers, full bleed | caption "camera inside the flow" |
| escalate: agent run | 12.5–17.5 s | this build's real judge log scrolls (stride-sampled: the whole run, compressed), the developing field as PiP | `clips/agent.mp4` — agent_run.log (15 grade.sh runs + mutants.py) strided to ~1.1 new rows/frame; |U| PiP t=0→30 | "agent sandbox run · sped up" SpeedTag Nx (summed verdict wall_seconds / 5 s); headline |
| proof (HUD) | 17.5–22.5 s | JUDGE: PASS badge, gate rows sliding in, HUD chips, counting mutant readout | `clips/proof.mp4` — |U| t=25.5→30 s, drift, 60 tracers | chips: L2 0.0043/0.02, orders 2.15/1.91, Ghia u 0.0033 v 0.0073, kills 10/10; residual gauge; CountUp 10/10 |
| verdict | 22.5–25 s | "judge: PASS" lands over the still-moving field | `clips/verdict.mp4` — |U| t=30 s pull-back, 60 tracers | verdict banner |
| end card | 25–27.5 s | static end card — the only still frame | `clips/endcard_still.jpg` backdrop at 26 % over gradient | `$ python3 cookbook/cfd-openfoam/run.py` + measured numbers line |

Cuts at 2, 8, 12.5, 17.5, 22.5, 25 s → 6 detected cuts ≈ 2.2 cuts/10 s
(gate ≥ 0.8). End card static from first frame (gate: last 2 s still).

## Pipeline (all in make_media.sh)

1. `judge/mutants.py` + `judge/grade.sh` on the 3 bad cavities, good cavity
   + poiseuille (`--trace`), 10 mutants — stdout tee'd to
   `judge_runs/agent_run.log` (the terminal clip's content).
2. `make_figures.py` → result.png, loop.png.
3. `video/render_clips.py` → clips/*.mp4 + endcard_still.jpg (numpy/PIL
   frames; ffmpeg encodes only).
4. `video/write_data.py` → clips/data.json (Remotion props from verdicts).
5. `npm ci` + `npx remotion render --sequence --public-dir=../clips
   --props=../clips/data.json` → PNG master frames.
6. ffmpeg: master crf 0 (gitignored) → demo.mp4 crf 18 +faststart.
