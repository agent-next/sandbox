# Second GPU sweep panel recut, 2026-10-15

## Baseline and changes

Owner-supplied baseline: Gemini visual/wow/clarity **8/8/9**, PASS;
Opus **8/6/7**, FAIL on wow. Those scores describe the previous video,
not this encode.

This recut addresses all eight Opus requests:

1. The finished result fills 0–2 s, then the measured **1 → 8,192**
   ladder is the next shot sequence, 2–12 s, instead of 14–24 s.
2. The GPU run used identical starts. The scale sequence now shows
   real CPU simulations with small, deterministic start perturbations,
   prominently labelled **“visual replay, perturbed starts”** and
   **“CPU render · not measured worlds”**. Native 3D grids grow from
   one to 256 visible worlds. Arm colours also vary for separation.
3. Every video label, including provenance, is at least 60 px, with
   at least 44 px cap height. Captions use fewer words.
4. All scale shots use the dark matte floor. The old white 2,048-world
   shot is gone; even the task's studio material is restrained slate.
5. Reach/drop/settle is one three-second shot, 12–15 s.
6. The video omits technical config identifiers and the word “judge”.
   Plain-language rejection labels replace the small technical footnotes.
7. The opening says **“CPU replay of GPU run”**. The comparison says
   **“CPU-rendered replays”**, with the GPU pose source explicitly
   labelled **“1-world recording”**.
8. All rejected configurations have red X marks; the six passing checks
   have a green check. Each group remains on screen for four seconds.

All pre-end-card shots are moving, real `mujoco.Renderer` output.
An animated cyan HUD line shows editorial shot progress, not performance.
Only 28–30 s is static. The storyboard was written before rendering.

## Provenance

The measured report, GPU log, good config, judge and measured numbers are
unchanged. Their source remains the acceptance run:

```text
python3 run.py --ref sbx/sweep-r4 --gpu --report-json media/data/report.json
```

- The reference task, opening and proof reconstruct all 801 CPU states
  through `judge/_sweep.py:cpu_reference`. Graded CPU oracle values and
  retained CPU states match within 1e-9.
- The comparison renders the 201 actual retained GPU samples without
  interpolation. They come from the first ladder point, one world.
  The GPU bar separately reports the measured 8,192-world aggregate
  throughput. It does not claim that these poses were recorded at 8,192.
  Both replay clocks match, at 6.25× slow motion.
- Retained GPU/CPU sample error is 0.00811055, within the judge's 0.05
  tolerance. The full measured parity value remains
  0.008110745441113454 rad, displayed as 0.00811.
- `render.py:visual_replay` separately runs 256 **unmeasured** CPU
  simulations with seed 0 and unchanged scene, controls, timestep and
  solver. Initial arm angles vary by at most 0.12 rad; box starts vary
  by at most 0.025 m horizontally, 0.08 m vertically and 0.35 rad in
  orientation. Initial velocities remain zero.
- `data/visual-replay.json` records these bounds and the full trajectory
  hash, explicitly `measured: false`. No visual variant contributes to
  a performance number, parity claim or passing physics verdict.
- Each displayed instance uses its own simulated pose and orientation,
  with only display translation and arm colour added. Tests compare
  native render geometry against each world's actual `mj_forward`
  transforms. No pose interpolation or hand-drawn physics is used.
- Solid dimensions, mass, friction, contacts, joints and solver settings
  remain checked unchanged. The collision plane's drawing extent and
  render-only shadow coverage support the grid without changing physics.
- Sweep rates are fixed receipt values, never count-up pseudo-data.
  Sweep motion is 2.5× slow; reference task 3.75×; proof 5×.

## Validation

Five new regression tests pass on the new renderer and were run against
the previous committed renderer. All five fail there on descriptive
assertions, with no import errors or skips. They cover the early sweep,
real deterministic visual variants, per-world native geometry, large
plain-language video labels and status marks, and HUD animation.

Negative controls also reject altered CPU/GPU poses, parity samples,
friction, solid dimensions, surviving mutants, hashes and clipped text.
The generated `video-gate.json` must exactly match a fresh gate run.

```text
bash cookbook/gpu-sim-sweep/media/make_media.sh
exit=0
CPU reference: 801 states; graded oracle matches within 1e-9
Recorded GPU trajectory: 201 samples; max error 0.00811055 <= 0.05
MuJoCo Renderer: 1054 frames; poses checked within 1e-9 against
CPU reference / retained GPU / labelled visual-replay data
MANIFEST: files, sizes, source and output SHA256 verified
Ran 19 tests in 60.541s
OK
make_media: done
```

The requested gate command was also run separately, using `python3`:

```text
python3 cookbook/tools/video_gate.py cookbook/gpu-sim-sweep/media/demo.mp4
exit=0
```

Full output: [`video-gate.json`](video-gate.json), **`"passed": true,
"failed": []`**. All 16 checks pass:

| Check | Measured | Required |
|---|---:|---:|
| Width × height | 1920 × 1080 | ≥ 1920 × 1080 |
| Display aspect | 1.7778 | 16:9 ± 1% |
| Duration | 30.0 s | 25–60 s |
| Frame rate | 30.0 | 29.969–30.001 |
| Codec / pixel format | H.264 / yuv420p | H.264 / yuv420p |
| Size | 6.3222 MiB, 6,629,359 bytes | < 8 MB |
| Faststart | moov@32, mdat@11704 | moov before mdat |
| First-frame mean luma | 85.5265 | ≥ 20 |
| First-frame luma standard deviation | 60.6890 | ≥ 12 |
| First-frame luma range | 248 | ≥ 8 |
| Scene cuts / 10 s | 1.3333, four detected cuts | ≥ 0.8 |
| Motion fraction | 0.6019 | ≥ 0.2 |
| End-card mean difference | 0.0014 | ≤ 0.5 |
| Audio | absent | optional |

The web file contains 900 frames. The master and eleven simulator clips
are lossless CRF 0 and remain git-ignored. Source/output hashes, including
the visual-replay provenance and gate verdict, are refreshed in
`MANIFEST.json`. Final inspected video SHA256:
`0a734a5f8cc1e389ae5a17d3b8de2b2781454d4a68fc9d23d7061e172acf065a`.

### Final H.264 encode: every one-second frame opened

Extracted frames 0, 30, …, 870 with
`ffmpeg -vf "select='not(mod(n,30))'" -fps_mode vfr`.
Opened all **30 individual 1920×1080 images**, not just a contact sheet:

| Seconds opened | Visual inspection |
|---|---|
| 0, 1 | Finished cyan arm and eight landed coloured boxes. Result and 25.8× payoff visible immediately; native camera angle changes. Large CPU-replay provenance. |
| 2, 3 | One visual world starts with upright arm and airborne, rotated boxes, then bends and lands. Perturbed-start / not-measured-worlds labels remain large. |
| 4, 5 | Four worlds from the opposite diagonal. Different arm colours and starting poses; real shadows and differently tilted boxes. Fixed 64-world measured rate is distinct from replay. |
| 6, 7 | Sixteen spatial worlds, upright/falling then bent/landed. Large 512-world measured caption and explicit visual-replay disclosure. |
| 8, 9 | Sixty-four worlds, overhead diagonal orbit. 2,048-world shot has a dark slate floor, no blown-out white background. |
| 10, 11 | 256 worlds fill the perspective grid, with varied colours and poses. 8,192-world endpoint and 686,725 steps/s remain fixed, not an animated measurement. |
| 12, 13, 14 | Three-second reference task: upright arm and falling boxes, then bent arm, then all eight boxes on the table. Slate studio material; large 3.75× slow label. |
| 15, 16 | Matched-clock CPU/GPU state replays, upright arms and falling boxes. One-world GPU pose source is explicit; common-scale bars and both measured rates are legible. |
| 17, 18, 19 | Same comparison through settling and continued native orbit. Bars remain fixed, neither replay is throughput-scaled. Both 6.25× slow labels stay visible. |
| 20, 21, 22, 23 | First four plain-language rejection rows with red X marks, no small technical identifiers. Moving arm/boxes on the right; green 6/6 check and measured parity bound below. |
| 24, 25, 26, 27 | Remaining four rejection rows, opposite-angle real replay, red X marks and green passing-check marker. Large captions do not clip. |
| 28, 29 | Same static finished render and launch command; the sole end card lasts two seconds. |

The animated HUD line stays at the top edge, clear of comparison labels.
Inspection scratch is removed after recording this table. The unchanged
shared-gate test suite and CLI matrix were not rerun: the changed media
suite exercises the shared gate against this exact final encode.

## Deviations log

- **Permitted visualization alternative:** distinct measured starts did
  not exist. Only the clearly labelled scale shots use new, perturbed
  CPU simulations. They are not presented as measured GPU worlds.
- **No new GPU lease or benchmark:** this is a media recut of the existing
  acceptance report, not a new engineering measurement.
- **Blind panel pending:** no fresh Gemini/Opus review was run here.
  Mechanical PASS and visual inspection do not establish panel scores.
  No new `REVIEW.json` or claimed panel PASS is fabricated.
- **Python command:** this environment has `python3`, not `python`;
  the equivalent gate command uses Python 3.
- One draft render was stopped to move the animated HUD progress line
  away from the comparison labels. The final full build is run afresh.
