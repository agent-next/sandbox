# GPU sweep media review, 2026-10-15

## Panel-driven craft recut

The first blind judge scored visual quality 7, wow 7, clarity 7, payoff
0.0 s, understandable muted true. Visual quality needs 8. This recut
addresses its three requested improvements without changing the judge,
graded config, gates, trajectories or measured numbers:

- Replace flat repeated tiles with one native 3D scene containing 1, 4,
  16 or 64 spatial instances, perspective, directional lighting, shadows
  and smooth camera orbits. The caption explicitly says **“same config,
  same start”**. It does not claim independent or randomized motion.
- Replace integrator jargon with the task and physical checks. Explain
  all eight rejected configs in plain English, on two moving proof shots;
  keep their technical identifiers small for traceability.
- Compare the CPU reference and actual retained GPU world-0 poses side
  by side. Static common-scale bars show **26,574 vs 686,725 steps/s**.
  Replay clocks match; this is aggregate throughput, not a fabricated
  single-world speed difference.

The 30-second cut starts on the finished real result, not a title card.
Dark hero/comparison shots contrast with light studio task/contact shots.
Matte checker materials give scale cues without distracting reflections.
Primary captions have at least 44-pixel cap height (60-pixel bold type);
the main headline is 68 pixels. Dark-backed gradients preserve contrast
over the light floor. Secondary source labels are smaller.
Only 28–30 s is static. `STORYBOARD.md` was updated before cutting.

**Panel status:** the lead must run both blind judges on this new encode.
This inspection is not a panel pass. No `REVIEW.json` was written.

## Honest state provenance

Source: the existing 2026-10-15 acceptance run, seed 0:

```text
python3 run.py --ref sbx/sweep-r4 --gpu --report-json media/data/report.json
```

No new lease or throughput measurement was needed for this media-only
change. The report, good config, judge and gate files are unchanged.

- `judge/_sweep.py:cpu_reference` reconstructs all 801 CPU poses with the
  exact good config, timestep, initial state and controls. The retained
  poses and graded CPU oracle match within 1e-9.
- Every render asserts qpos within 1e-9 against its CPU reference pose
  or exact retained GPU pose. GPU samples are not interpolated.
- The judge retains 201 GPU samples from the **first ladder point,
  one world**, not the 8,192-world run. The comparison explicitly labels
  “GPU 1-world recording”; the GPU bar separately labels its rate at
  8,192 worlds. Nearest samples share the CPU replay clock. The judge's
  convention, CPU step i versus GPU step i+1, remains unchanged.
- Retained GPU/CPU sample error is 0.00811055, within the judge's 0.05
  tolerance. The measured full parity number remains 0.008110745441113454
  rad, displayed as 0.00811, not claimed equal to CPU at 1e-9.
- All graded worlds start identically. Grid instances translate only
  MuJoCo display geometry, preserving every orientation and relative
  position. No new dynamics or variety is synthesized. Captions disclose
  how many instances are shown versus how many worlds were measured.
- The infinite collision plane's finite drawing extent is enlarged to
  support the grid. Its position, orientation and collision physics stay
  fixed. Solid geometry sizes, masses, friction, contacts, joints,
  actuators and solver settings are checked unchanged. Native shadow
  coverage expands with the grid, avoiding out-of-bounds shadow artifacts.
- Ladder values are fixed measured endpoints, never count-up pseudo-data.
  Every replay has its slow-motion factor on screen. The comparison uses
  6.25× slow motion on both sides, not throughput-scaled playback.

The simulator writes twelve lossless shot clips, then concatenates a
git-ignored CRF 0 master. The H.264 web copy uses CRF 18, preset slow,
yuv420p, faststart and a 1.9 Mbit/s ceiling. Figures are generated from
the same report; no plotting package is used.

## Final encode inspection

Fifteen frames were extracted from the **final H.264 web encode** with
`ffmpeg -ss T -i demo.mp4 -frames:v 1` and opened individually at
1920×1080, not only as a contact sheet:

| Time | What is visible |
|---|---|
| 0.0 s | Finished bent cyan arm and eight coloured boxes on the table, real cast shadows and matte checker floor. The large hook reads “25.8× CPU. Physics checks out.” and “686,725 steps/s · physics PASS”. Payoff is already present. |
| 2.3 s | Light studio wide shot. Arm is bending from upright; boxes remain at different falling heights. Large task/result captions sit on dark gradients outside the main action; CPU reference and 5× slow labels are visible. |
| 4.5 s | Later in the same replay, arm low and boxes settled. The native camera angle has changed, and shadows give the real geometry depth. No integrator jargon occupies the headline. |
| 6.3 s | Elevated opposite-angle close-up of the table with airborne boxes. “All eight boxes land. None fall through.” explains the physical check. The arm is partly outside this deliberate contact close-up. |
| 8.4 s | All eight coloured boxes rest on the table in the contact shot. The measured 0.315 m box centre and required > 0.255 m bound are readable against a dark-backed footer, with 3.75× slow and final-check labels. |
| 9.5 s | Two real camera renders: CPU baseline left, GPU rollout right, both early in the fall. Amber CPU bar is short; cyan GPU bar fills the common scale. 26,574 and 686,725 steps/s are large. “GPU 1-world recording” and rate at 8,192 worlds distinguish pose source from measured throughput. |
| 12.0 s | Both replays have bent arms and landed boxes with matching orbit angles. The same-clock motion visibly agrees; the measured bars stay fixed rather than pretending to be live meters. |
| 14.5 s | One real reference scene during the replay. The ladder begins at 1 world and 134 steps/s, with the identical-start disclosure and 2.5× slow label. |
| 16.5 s | Four spatially separated arm/table instances on a continuous lit floor, viewed diagonally from the other side. Perspective, shadows and spacing replace the old flat four-tile mosaic. Caption says 64 measured worlds, 4 shown, 10,785 steps/s. |
| 18.5 s | Sixteen synchronized instances in one perspective scene, all at the same verified pose. Caption says 512 measured worlds, 16 shown, 77,008 steps/s. There is no invented trajectory variety. |
| 20.5 s | Elevated light-studio grid of 64 instances. Continuous ground and expanded shadow coverage avoid floating floor edges and out-of-bounds shadow artifacts. Caption reports 2,048 measured worlds and 248,064 steps/s. |
| 22.5 s | Dark diagonal fly-over of the 64-instance grid with strong near/far scale cues. Large endpoint reads 686,725 steps/s at 8,192 measured worlds; 64 shown, same config/start, no randomized motion. |
| 24.5 s | Real moving simulation remains on the right while the first proof group says Fake results, Flipped gravity, No contact limit and Tiny time step. Smaller identifiers identify the actual rejected configs. The footer says all six checks PASS and gives the measured agreement bound. |
| 26.5 s | Opposite-angle moving simulation beside Stops too soon, Weak solver, Contact overflow and Out of memory. All four are marked REJECTED with their actual identifiers. No fake failing trajectories are shown. |
| 29.0 s | Static finished real render, large `python3 run.py --gpu` launch, working-directory hint, 25.8× CPU and 4× floor. This frame is held through the final two seconds. |

Also opened the complete generated `result.png` (2400×1950, 200 dpi):
four real CPU poses at 0, 0.2, 0.4 and 0.8 s, unchanged measured ladder
and explicit throughput/oracle pass lines. Opened `loop.png`
(2400×1600, 200 dpi): the explicitly labelled config-fixing replay,
5/6 → 4/6 → 6/6 gates, all eight real self-test kills and ≥90% pass line.

## Verification

```text
make_media.sh rc=0
CPU reference: 801 states; graded oracle matches within 1e-9
Recorded GPU trajectory: 201 samples; max error 0.00811055 <= 0.05
MuJoCo Renderer: 1054 frames verified against
CPU reference / retained GPU qpos data within 1e-9
MANIFEST: files, sizes, source and output SHA256 verified
Ran 14 tests in 25.359s
OK
```

The three new grid/GPU-comparison/plain-English regression tests were
also run against the previous committed renderer. All three failed on
descriptive assertions, not imports or skips. Negative controls reject
altered CPU/GPU poses, parity samples, friction, solid dimensions, mutant
results, hashes and clipped labels. Caption tests check cap height and
contrast over a white scene. Grid tests check exact display translations
at MuJoCo's float32 geometry precision, while qpos checks remain 1e-9.

The first draft recut failed motion (0.1311) and scene cuts (0.3333 per
10 s). That failure was fixed through real camera motion, contrasting
native studio views and stronger floor scale cues, not gate changes.
The shared gate test initially caught that same draft failure; it is
rerun against the final encode below.

Final `video_gate.py`: **`"passed": true, "failed": []`**.

| Check | Final measurement | Required |
|---|---:|---:|
| Scene cuts / 10 s | 2.0 (6 detected cuts) | ≥ 0.8 |
| Motion fraction | 0.6472 | ≥ 0.2 |
| End-card mean difference | 0.0010 | ≤ 0.5 |
| Size | 6.3330 MiB / 6,640,581 bytes | < 8 MB |
| First-frame mean luma | 84.1996 | ≥ 20 |
| First-frame luma standard deviation | 60.0758 | ≥ 12 |
| First-frame luma range | 248 | ≥ 8 |

Codec, pixel format, resolution, aspect ratio, duration, frame rate and
faststart also pass (`moov@32`, `mdat@11708`). No audio is required.

```text
ffprobe:
codec_name=h264
width=1920
height=1080
pix_fmt=yuv420p
r_frame_rate=30/1
nb_frames=900
duration=30.000000
size=6640581
```

`MANIFEST.json` records every generator/input and output SHA256.
Final inspected video SHA256:
`e05581b55e406ea2e25d5d431516aed5cbaa207a4252837d42945c09bae3fd86`.
All 104 tracked JSON files parse. `git diff --check` passes.
The environment uses `python3`; `python` is not installed on PATH.
The shared gate suite is therefore invoked with `python3 -m pytest`.

```text
$ python3 -m pytest -q cookbook/tools/test_video_gate.py --color=no
....................                                                     [100%]
20 passed in 767.20s (0:12:47)
```

The final rerun passes every test, including the committed-demo baseline.
The host was heavily loaded during this run; no checks were skipped or
gate thresholds/baselines changed.

Not run for this media-only change: fresh GPU lease grading, CLI Python
3.10/3.13 matrix, or the blind review panel. The existing acceptance
receipt remains the source of physics/performance numbers. Scratch
inspection images and temporary test files are removed after review;
the required ignored lossless clips and master remain.
