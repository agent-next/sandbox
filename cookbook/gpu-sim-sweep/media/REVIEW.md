# 3D media review, 2026-10-15

## Video-gate recut

The reviewed static cut failed the newly merged cookbook gate:
`scene_cuts_per_10s = 0.7692 < 0.8` and
`motion_fraction = 0.0403 < 0.2`. The replacement keeps the same measured
numbers and physics, but adds native 3D camera orbits, opposite-angle
contact close-ups, one/2×2/4×4 animated replays, and a moving proof shot
with the eight actual mutant kills. Only 24–26 s is static.
`STORYBOARD.md` was updated before cutting the replacement.

Every image of the simulation comes from MuJoCo 3.8.1's
`mujoco.Renderer`, using EGL (the script also probes an OSMesa fallback).
The checker floor, gradient skybox, lights and shadows are real scene
rendering. Camera orbits are not pans or zooms over still images.
The simulator first writes ten lossless shot clips, then ffmpeg
concatenates them into the git-ignored CRF 0 master and encodes the web
copy with CRF 18, preset slow, yuv420p and faststart. A 2.1 Mbit/s VBV
ceiling keeps the moving scene under 8 MB. The first uncapped recut
failed the size check at 17,093,306 bytes; it is not the committed encode.

The source remains the 2026-10-15 acceptance run:
`python3 run.py --ref sbx/sweep-r4 --gpu --report-json media/data/report.json`,
seed 0. No lease was created and no throughput measurement was changed.
The environment is Python 3.12.3, MuJoCo 3.8.1, NumPy 2.3.1,
Pillow 11.3.0 and ffmpeg 6.1.1; `pip check` passes.

## State provenance

- The exact good config, model, timestep, initial state and controls are
  reconstructed through `judge/_sweep.py:cpu_reference`, not a new physics
  implementation. All 801 retained CPU states and the graded CPU oracle
  match a fresh reference within 1e-9.
- Every rendered qpos is asserted against that data within 1e-9, including
  orbit views, contact close-ups and the reference frame reused in tiles.
  Scene dressing is checked not to change geometry, masses, contacts,
  actuators or solver settings.
- All GPU worlds start identically. The tiles honestly reuse the same
  animated CPU reference world; they are not separate GPU recordings or
  randomized trajectories. The on-screen count-up reveals measured ladder
  endpoints, not a live performance meter.
- The 201 retained float32 GPU samples match at the judge's 0.05 tolerance
  (observed error 0.00811055), not at 1e-9. The original convention is
  preserved: CPU step i versus GPU step i+1, recorded after compilation.
  The full measured parity error on screen remains 0.008110745441113454 rad.

## Images opened

Both complete PNGs were opened, along with their unscaled 1200-pixel-wide
left/right crops for inspection at original pixel scale. Both figures
remain byte-identical to the approved version.

- **result.png (2400×1950, 200 dpi):** four native 3D views at 0.000,
  0.200, 0.400 and 0.800 s. The cyan arm bends while eight coloured boxes
  fall onto the dark table. Perspective, lighting and cast shadows are
  visible. Each tile compares the graded arm error 0.0607 rad with
  < 0.15 rad and the final box centre 0.315 m with
  0.255 < z < 0.525 m. The final read-back is explicitly labelled, not
  attributed to the airborne initial pose. The measured ladder remains
  134 / 10,785 / 77,008 / 248,064 / 686,725 steps/s; the pass line is
  686,725 > 4 × 26,574 = 106,296 steps/s, 25.8× CPU.
- **loop.png (2400×1600, 200 dpi):** the labelled config-fixing replay
  shows the real solver_iter_1, low_capacity and good grades at
  5/6, 4/6 and 6/6 gates. The right side shows 8/8 kills, the ≥90% pass
  line, zero survivors and each mutant's actual killing gates.
  It is a Pillow evidence table, not a fabricated live agent trace.

### Final web-video frames opened at 1920×1080

Each frame was extracted from the final H.264 web encode with
`ffmpeg -ss T -i demo.mp4 -frames:v 1` and opened individually.
These are new inspections of the final encode, not the earlier static cut.

| Time | What is visibly present |
|---|---|
| 0 s | Finished bent cyan arm and eight landed coloured boxes, checker floor and shadows; hook says 686,725 steps/s, physics PASS and 25.8× CPU. The camera orbits this real pose during the opening shot. |
| 3 s | Arm bending away from upright, boxes at different falling heights; full-scene perspective has changed. CPU reference and 7.5× slow labels are visible. |
| 5.5 s | Low bent arm and landed boxes, seen from farther around the scene; dt, solver and final-read-back oracle captions remain outside the action. |
| 8.5 s | Elevated opposite-angle close-up of the table and falling boxes. The arm is partly outside this deliberate contact view. Replay is labelled 3.75× slow. |
| 11.5 s | One animated reference view in the protected scene area; nworld 1 and the 134 steps/s measured endpoint are labelled. |
| 13.5 s | Four complete animated reference tiles from another angle; nworld 64 endpoint is 10,785 steps/s. No tile is covered by the caption bands. |
| 16.5 s | Sixteen wide replay tiles with bent arms and landed boxes; nworld 512 endpoint is 77,008 steps/s. |
| 18.5 s | Sixteen elevated contact close-ups, with all eight boxes on each table; nworld 2048 endpoint is 248,064 steps/s. |
| 20.5 s | Sixteen wide scene views from the next camera angle; nworld 8192 endpoint is 686,725 steps/s. |
| 21 s | Proof HUD and all eight actual mutant names marked KILLED; the replay restarts with an upright arm and airborne boxes. The entire scene sits below the matrix, so the HUD does not obscure it. |
| 22.5 s | Proof HUD over the continuing orbit/replay, now with the arm bent and boxes landed; CPU 26,574, 25.8×, floor 4×, parity 0.00811 < 0.05 rad and the 4 GiB slice remain visible. |
| 25 s | Static finished native 3D scene and the launch command `python3 run.py --gpu`. |

The source frames are native simulator output, not plots, stick figures or
drawn geometry. Caption bands do not cover the tiled action or proof view.

## Verification

The added media gate regression test was first run against the original
committed video. It failed on an assertion naming the two failed checks,
not an import error or skip. After the recut, the final build reports:

```text
make_media.sh rc=0
CPU reference: 801 states; graded oracle matches within 1e-9
Recorded GPU trajectory: 201 samples; max error 0.00811055 <= 0.05
MuJoCo Renderer: 784 frames verified against CPU qpos data within 1e-9
MANIFEST: files, sizes, source and output SHA256 verified
Ran 11 tests in 7.337s
OK
```

The tests additionally prove that camera movement changes the view without
changing qpos, tiles animate the reference and leave HUD margins clear,
and altered poses, parity samples, physics dressing, mutant results,
hashes and clipped labels are rejected.

```text
$ python -m pytest -q cookbook/tools/test_video_gate.py --color=no
....................                                                     [100%]
20 passed in 160.24s (0:02:40)
```

Final `video_gate.py` verdict: `passed: true`, `failed: []`.

| Check | Measured | Required |
|---|---:|---:|
| scene_cuts_per_10s | 1.1538 (3 detected cuts) | ≥ 0.8 |
| motion_fraction | 0.8679 | ≥ 0.2 |
| endcard_static | 0.0015 | ≤ 0.5 |
| size_mib | 6.1713 | ≤ 8 |
| first_frame_luma_mean | 197.1802 | ≥ 20 |
| first_frame_luma_std | 50.2443 | ≥ 12 |
| first_frame_not_solid | 236 | ≥ 8 |

The gate also passes codec, pixel format, resolution, aspect ratio,
duration, frame rate and faststart (`moov@32`, `mdat@10292`).
`test_result.py`: 41 passed. All 104 tracked JSON files parse; marketplace
paths and manifest required fields pass. `git diff --check` passes.
The forbidden plotting-package `git grep` has no matches in this demo.

### ffprobe, final encode

```text
codec_name=h264
width=1920
height=1080
pix_fmt=yuv420p
r_frame_rate=30/1
nb_frames=780
duration=26.000000
size=6471097
```

Final video SHA256:
`e5d616c2d80f1e4adc632046f3898148367c74ea0a12aefbb9cf6dc0256cf6d0`.
`MANIFEST.json` records all output and generator hashes. Raster/encode
bytes are not promised identical across machines; the CPU trajectory
and per-frame state assertions are the reproducibility guarantee.

Not run for this media-only fix: fresh GPU lease grading, CLI Python
3.10/3.13 CI matrix, or the two-model blind review panel. This inspection
does not substitute for that panel. No gate threshold or known-fail
baseline was changed. Temporary review frames and test scratch were
removed; the required ignored simulator clips and lossless master remain.
