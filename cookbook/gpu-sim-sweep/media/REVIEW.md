# 3D media review, 2026-10-15

## What was rendered

`bash cookbook/gpu-sim-sweep/media/make_media.sh` uses MuJoCo 3.8.1's
`mujoco.Renderer` on EGL, with an OSMesa fallback probe. The scene has a
textured checker floor, gradient skybox, two lights and enabled shadows.
Only visual attributes change; the model's geometry, inertia, contacts,
actuators, initial state and timestep are checked against the judge model.
The CPU reference starts at `MjData(model)` with zero velocity and
`ctrl = ARM_TARGET`, exactly as the judge does.

The media environment is Python 3.12.3, MuJoCo 3.8.1, NumPy 2.3.1,
Pillow 11.3.0 and ffmpeg 6.1.1. Media dependencies are pinned in
`requirements.txt`. Wheel downloads stalled during setup, so the local
environment was bootstrapped from installed/cached copies of those exact
versions; `pip check` passed. The media NumPy version differs from the
judge's pinned 1.26.4, but every reconstructed CPU state and the graded
CPU oracle still match at 1e-9. The MuJoCo physics version is unchanged.

Source measurements are the separate 2026-10-15 acceptance run:
`python3 run.py --ref sbx/sweep-r4 --gpu --report-json media/data/report.json`,
seed 0. Its public, sanitized report and console output are retained.
No lease was created for rendering.

The acceptance report retains GPU samples, not a CPU trajectory. Therefore:

- `judge/_sweep.py:cpu_reference` regenerates all 801 CPU states from the
  exact good config; the graded CPU oracle must match within 1e-9.
- The renderer reconstructs the reference again and checks every retained
  CPU state, then checks every rendered qpos against it within 1e-9.
- The retained 201 float32 GPU samples match the reconstructed reference
  within the judge's 0.05 parity tolerance (observed 0.00811055). They are
  not claimed equal to CPU states at 1e-9.
- The original GPU sample convention is preserved: CPU step i versus
  GPU step i+1, because the GPU runner records after its compile step.
- The separately measured full parity error on the proof card remains
  0.008110745441113454 rad, as reported by the acceptance judge.

## Images opened at original pixel scale

Both original PNGs were opened. Their left/right halves were also opened
as 1200-pixel-wide, unscaled crops, so every original pixel and caption
could be inspected without the viewer downsampling a 2400-pixel image.

**result.png, 2400×1950, 200 dpi:** four real 3D views at simulation
0.000, 0.200, 0.400 and 0.800 s. Initially the cyan capsule-link arm stands
upright beside eight coloured boxes suspended at staggered heights over
the dark table. At 0.200 s the arm has bent and the boxes have fallen;
some low boxes are contacting the table while higher boxes remain airborne.
At 0.400 and 0.800 s all eight boxes are on the table and the arm moves
into its final joint-target pose. The floor texture, specular surfaces,
perspective and cast shadows make the actual 3D geometry visible.

Each tile labels the graded CPU arm error, 0.0607 rad versus the
0.15 rad oracle, and the final box centre height, 0.315 m versus
0.255 < z < 0.525 m. PASS is explicitly for the 0.800 s read-back,
not a claim that the initial airborne frame already satisfies the oracle.
The bottom Pillow ladder reads 134 / 10,785 / 77,008 / 248,064 / 686,725
steps/s. The throughput pass line reads
686,725 > 4 × 26,574 = 106,296 steps/s, 25.8× CPU.

**loop.png, 2400×1600, 200 dpi:** the left side shows a labelled recorded
config-fixing replay: solver_iter_1 gives 5/6 gates, low_capacity 4/6,
and good 6/6 PASS. These are real acceptance grades, not a fabricated
chronological agent session. Orange failure bars and the green final
pass bar are legible. The six final gates are individually listed.
The right side shows 8/8 = 100% kills, the ≥90% pass line, zero survivors,
and each mutant's actual killing gates. No cell or label is clipped.

## Full-size video frames opened

Frames were extracted with `ffmpeg -ss T -i demo.mp4 -frames:v 1` and
opened individually at 1920×1080. The inspected encode has the same
SHA256 as the final committed encode listed below.

| Video time | What is visibly present |
|---|---|
| 0 s | Finished bent arm and eight landed coloured boxes, real checker floor and shadows. Hook: 686,725 steps/s, physics PASS, 25.8× CPU. No title-only frame. |
| 3 s | The arm is moving away from its upright initial pose; boxes are airborne above the table at different heights. CPU reference replay label, simulation time and 7.5× slow label are readable. |
| 5 s | The arm is bent low; the eight boxes are landing/landed on the table. Their square tops and vertical sides remain visible, with cast shadows. The oracle caption stays in the lower margin. |
| 9 s | A real closer camera view of falling boxes and table contact. Some boxes are on the table and higher boxes remain above it. The arm is partly outside this deliberate contact close-up. Caption identifies 3.75× slow CPU replay. |
| 12.5 s | A 4×4 grid of identical real replay tiles, with arm and settled boxes in each. nworld 1 endpoint: 134 steps/s. Caption explicitly says identical initial states and repeated tiles. |
| 16.5 s | The same honestly repeated 3D scene grid; nworld 512 endpoint is 77,008 steps/s. The endpoint is labelled measured; count-up is labelled a reveal, not a live meter. |
| 20.5 s | Sixteen real scene tiles and the nworld 8192 endpoint, 686,725 steps/s. There is no fabricated per-world variety or claim that these are separate GPU trajectory recordings. |
| 23 s | Closing proof over the finished rendered scene: 686,725 vs 26,574 CPU steps/s, 25.8×, floor 4×, 8/8 killed, parity 0.00811 < 0.05 rad, and the 4 GiB RTX 5090 slice label. |
| 25 s | Held closing rendered frame and the one-line `python3 run.py --gpu` launch command. The arm and all eight boxes remain visible, with captions outside their motion area. |

The simulation shots are native 3D renders, not motion plots, stick figures
or hand-drawn substitutes. `loop.png` intentionally uses a Pillow evidence
table/bar layout; it does not pretend to render physics.

## VERIFY

“Clean” here means deleting all generated PNG/video/manifest/CPU replay
products and the lossless master before each build. The measured input
report and installed dependency cache are retained.

Two consecutive final-code clean builds, plus a third diagnostic rebuild:

```
make_media.sh clean build 1: rc=0
make_media.sh clean build 2: rc=0
make_media.sh diagnostic clean build 3: rc=0
CPU reference: 801 states; graded oracle matches within 1e-9
Recorded GPU trajectory: 201 samples; max error 0.00811055 <= 0.05
MuJoCo Renderer: 784 frames verified against CPU qpos data within 1e-9
MANIFEST: files, sizes, source and output SHA256 verified
Ran 8 tests
OK
```

Both PNGs, the model XML, replay metadata and CPU qpos array were
byte-identical across these builds. Video SHA256 was:

```
build 1: 7c68858d353af5bbd26afd0055ec3608969a8bd718bd41576798b7a0f226260a
build 2: 553d6e6f7331277c56b58c76d4e691cf799e8f842449f9d31af2064cab184501
build 3: 7c68858d353af5bbd26afd0055ec3608969a8bd718bd41576798b7a0f226260a
```

**Video is not guaranteed byte-identical.** Comparing the decoded lossless
masters of builds 2 and 3 found 263 changed colour channels in 122 of 780
frames, maximum 8-bit channel delta 3, maximum per-frame mean absolute
delta 0.0000020898 on the 0–255 scale. This is tiny raster/colour variation,
not trajectory drift: the CPU data are byte-identical and every frame's
state assertions pass. The web files differ by 81 bytes; the manifest
correctly follows the actual video hash. A single-thread lossless encode
did not eliminate the variation. No stronger determinism claim is made.

The new source-ban test was also run against the original generators
from f077723 in a temporary directory. It failed on
`AssertionError: Forbidden plotting import`, not an import error or skip.
The current media tests all pass. Negative controls reject altered CPU
poses, altered GPU trajectory samples, physics-changing scene dressing,
surviving mutants, missing files, incorrect hashes and clipped text.

`git grep` for the forbidden plotting package returns no matches in the
demo. Public-path/diagnostic hygiene and `git diff --check` were checked.
Full CLI CI and a new GPU lease grade were not run for this media-only
change; the supplied acceptance grade is the measurement source.
Independent reproduction and PR review remain pre-merge work.

### ffprobe, final encode

```
codec_name=h264
width=1920
height=1080
pix_fmt=yuv420p
r_frame_rate=30/1
nb_frames=780
duration=26.000000
size=5070585
```

The 5.07 MB web encode uses `-crf 18 -preset slow -pix_fmt yuv420p
-movflags +faststart`; the git-ignored lossless master uses `-crf 0`.
The tests check faststart atom order, resolution, frame count, size, codec,
pixel format and the lossless master's `qp=0` encoder record.

### Final committed file hashes

```
f7af1df44a84eea658dab3ffe7523a2a4991ff28c5bf6c96066f553a4fe4048f  result.png
32bd45cbe367fcaf6716dc60f72d70c7c27a4cb7815aa7d0d8e0bb2bf3c91e44  loop.png
7c68858d353af5bbd26afd0055ec3608969a8bd718bd41576798b7a0f226260a  demo.mp4
2f31e202d678d227eceb49882d896700d64e6873b5d074df2b1408847424b802  MANIFEST.json
```
