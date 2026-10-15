# MuJoCo 3D media review

Implementation inspected and validated: `b6ea3ba`.

Regenerate from the repository root:

```bash
bash cookbook/sim-engine-arena/media/make_media.sh
```

The media pipeline runs setup and self-test on an unchanged scratch copy
of the judge, then invokes its full grading driver with seed 0. An observer
copies the artifact's actual CSVs and generated MJCF before judge cleanup.
No replacement trajectories are generated. The oracle metrics are checked
against the full verdict.

Replay uses the artifact-generated model, timestep and initial state.
Every sample, including the velocity columns, is checked against the actual
graded CSV. The artifact's free-joint CSV positions are pre-integration
`xpos`; those frames use the corresponding pre-step `qpos`, not the next
integrated state. Pendulum CSVs use post-step joint angles. Every rendered
frame checks the full joint state and the recorded position or angle.

Render-only copies add textures, materials, lights, a skybox and camera
settings. The pendulum's massless link, anchor and floor are noncolliding
visual geometry. Original mass, inertia, geometry, friction, contact
parameters, transforms, gravity and timestep are asserted unchanged.
Shadows are enabled. Pillow draws labels and the loop table.

The master is lossless `-crf 0` in ignored `media/master/demo.mp4`.
The web file is encoded from it using
`-crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart`.
The video slows the complete drop by 4x, slows the two complete inclines
by 8x side by side, plays the full pendulum at real time, and ends on a
PASS card over the last rendered state.

The generated MJCF is intentional: the committed drop snapshot spells out
friction differently from `sim.py`'s defaults. Rendering the snapshot
instead of the model actually produced by the graded artifact would not
meet the replay contract. The artifact and its physics are unchanged.

## Images opened

Opened `result.png` and `loop.png`, then inspected the final images at
native pixel size in unscaled crops under ignored `media/work/review/`.
The crop boundaries split some tiles and labels; the original images do
not have those cuts.

- **result.png, 2400×2130, 200 dpi:** a four-row, three-column grid of
  shaded 3D scenes. The orange sphere starts above a checker-textured
  floor, reaches contact at 0.441 s, then rests with a shadow/reflection.
  The 35° orange box moves downhill between 0, 0.5 and 1 s; the 20° box
  stays at essentially the same location. Both ramps have perspective,
  lit box faces and cast shadows. The bottom row shows the fixed anchor,
  silver 3D link and small orange bob at release, the center crossing and
  the opposite extremum. The bob remains the artifact's actual 2 cm
  radius, not an enlarged illustrative mass. Every tile names its scene
  and time, prints measured versus oracle, and has a green numeric PASS
  line. No trajectory plots or drawn substitutes for the simulated
  objects appear.
- **loop.png, 2400×1600, 200 dpi:** Pillow bars/table, not simulation
  imagery. Iterations show 3/4 FAIL, 3/4 FAIL, then 4/4 PASS. The third
  row explicitly includes reference agreement. The right column shows
  known-good passing, all eight mutant names, the observed failing-gate
  categories and the 8/8 = 100% kill rate. Text is large and legible;
  pass/fail words distinguish outcomes without relying on color.

Native crops opened:

```text
media/work/review/result-native-0-0.png
media/work/review/result-native-1-0.png
media/work/review/result-native-0-1.png
media/work/review/result-native-1-1.png
media/work/review/loop-native-0-0.png
media/work/review/loop-native-1-0.png
```

## Full-size video frames opened

Extracted from the final web encode without resizing and opened all eight
at **1920×1080**. Paths below are relative to this demo's directory.

| path | visible content |
| --- | --- |
| `media/work/review/frame-00.5s.png` | Orange 3D sphere suspended above the checker floor during its fall; lit surface and separate floor shadow; contact measurement 0.4406 s versus 0.4401 s oracle below. |
| `media/work/review/frame-01.8s.png` | Sphere at floor contact, with shadow/reflection; scene time about 0.45 s; contact PASS line remains readable. |
| `media/work/review/frame-04.0s.png` | Sphere settled on the floor around simulation time 1 s, not a drawn circle or free-fall ghost. |
| `media/work/review/frame-10.0s.png` | Two real 3D views side by side: orange box partway down the 35° ramp, box near its start on the 20° ramp; acceleration and millimetre travel captions below. |
| `media/work/review/frame-13.0s.png` | Sliding box farther downhill while the sticking box remains near its initial location; perspective checker ramps, lit faces and cast shadows remain visible. |
| `media/work/review/frame-15.0s.png` | Fixed 3D anchor, thin silver link and orange bob during the swing; period 2.0073 s versus oracle 2.0073 s and the 2% pass line below. |
| `media/work/review/frame-18.0s.png` | Same anchored pendulum at a different swing phase; the bob/link position changes while the anchor remains fixed. |
| `media/work/review/frame-26.0s.png` | PASS card on the left, final rendered pendulum clearly visible on the right. Card lists contact 0.4406 s, stick travel 1.79 mm, slide acceleration 1.6082 m/s², period 2.0073 s, their oracle/pass lines, kill rate 8/8 and “graded by the judge in a disposable sandbox”. |

In the inspected frames the caption bands do not cover the moving
objects, and the final card does not cover the pendulum. All simulation
images are real MuJoCo offscreen renders, not charts, stick figures or
2D replacements. The loop graphic alone intentionally uses Pillow bars.

## Regression checks

Eight tests run automatically at the end of `make_media.sh`:

- actual retained CSVs equal the full judge's oracle verdicts;
- each incline uses its own angle for agreement;
- scene `timestep_s` overrides the global timestep for row counts;
- every graded state replays, and deliberately corrupted rendered states
  fail for all four scenes;
- forbidden plotting imports/dependencies are rejected, including
  deliberately injected imports;
- missing/surviving-mutant self-test evidence is rejected;
- required media/source files and hashes match; missing media fails;
- web format, faststart, size and lossless-master encoder settings pass.

The two P3 tests were also executed against in-memory copies of the
judge with the old calculation restored, one bug at a time. Both failed
on assertions, not import errors:

```text
old 35-degree projection: regression test FAILS on assertion, as required
AssertionError: 0.9659258262890683 != 1 within 12 places:
incline_stick: agreement must use its own angle
old timestep key: regression test FAILS on assertion, as required
scene timestep_s must override global timestep
```

## Two clean builds / VERIFY

Before each build, removed only the known generated PNGs, web video,
master, manifest, CSVs, model copies, joint-state files, verdict, versions
and self-test/render-check outputs. Kept the installed toolchain/cache.
Each build reran setup, the real 8-mutant self-test, full seed-0 grading,
state replay, 3D rendering, encoding, manifest generation and all tests.

```text
Clean build 1: rc 0
Clean build 2: rc 0
IDENTICAL f288bf87251d3599419eb1f3813bab23c758ab1d18c79e50d200952195f390a6  result.png
IDENTICAL a831b513901ab47d5a45e60cf1d45a9fb6fe951405716ddd0b0e0136854e6c3b  loop.png
IDENTICAL 6d9a7123239e93e157f76770b72df5d5167d66b806056157fa4370e659490c0c  demo.mp4
IDENTICAL 1a4fd08f0890f2f18f35e4623bafb4c4d83ed6d5c9e50e54edad596e9389fea9  MANIFEST.json
Two clean builds: byte-identical media, manifest, master and evidence
```

Both builds printed:

```text
selftest: kill rate: 8/8 = 100%
selftest: determinism: OK
Actual graded CSVs retained; oracle metrics exactly equal (4/4)
drop: 1501 actual graded samples verified
incline_stick: 1001 actual graded samples verified
incline_slide: 1001 actual graded samples verified
pendulum: 10001 actual graded samples verified
video drop: every frame state-checked
video inclines: every frame state-checked
video pendulum: every frame state-checked
video pass: every frame state-checked
Ran 8 tests
OK
```

Final `ffprobe` output:

```text
codec_name=h264
width=1920
height=1080
pix_fmt=yuv420p
r_frame_rate=30/1
duration=28.000000
size=1151013
```

The forbidden-library repository search returned no matches (exit 1).
`git diff --check` passed. All changes are confined to this demo.
EGL succeeded; the implemented OSMesa fallback was not exercised.
Dependencies: MuJoCo 3.8.1, NumPy 2.5.3, Pillow 11.3.0, Python 3.12.3,
ffmpeg 6.1.1; font files are checksummed in the manifest.

The existing fresh-sandbox physics receipts remain unchanged. A new
remote `run.py`, optional GPU replay, unrelated CLI/plugin CI and an
independent reproduction/review were not run for this media replacement.
No new remote sandbox run is claimed. The final card's sandbox grading
statement refers to the existing disposable-sandbox receipts for this
same unchanged good artifact and the same measured numbers.
