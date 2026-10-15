# Media review: sim-engine-arena

## Provenance

Run from the repository root:

```bash
bash cookbook/sim-engine-arena/media/make_media.sh
```

The script copies the judge unchanged into ignored `media/work/` before
running `judge/setup.sh`, `judge/selftest.sh` and the same full-run
`judge/grade.sh examples/good/sim.py --seed 0` path used by `run.py`.
The copy keeps setup's `VERSIONS.txt` rewrite out of the original judge.
Toolchains, caches and temporary files stay under `media/`.

The judge deletes its private CSVs. The script therefore runs the same
good artifact again with the same spec and pinned CPU interpreter, retains
its CSVs, and asserts **exact equality of every oracle metric** against the
full-run verdict, for all four scenes. No `--skip-run` grade is used.
`data/grade.json` drops only the unplotted `timing` key.
`data/selftest.txt` is real, complete selftest stdout. CSV dumps are
ignored; `MANIFEST.json` records their hashes and regeneration command.
The loop source is the existing `examples/good/loop.json`, not a new or
invented history. Its caption identifies the recorded draft replay.

Environment: Python 3.12.3; judge MuJoCo 3.8.1 / NumPy 2.5.3;
rendering Matplotlib 3.10.7 / NumPy 2.2.6; ffmpeg 6.1.1-3ubuntu5.
Rendering dependencies are pinned in `requirements.txt`; the judge
installs its separate hash-pinned wheel set.

## Images opened and checked

Both original PNGs were opened, then inspected at native resolution in
two 1200-pixel-wide tiles, without resizing. Separate 1200-pixel-wide
previews were also opened to check README-sized readability.

- **result.png, 2400×1760, 200 dpi:** A shows the measured sphere-center
  height, analytic pre-contact free fall and measured contact-time marker.
  B shows downhill slide displacement against `½at²`, with the stick
  trajectory and zero-travel oracle at the baseline. C shows measured
  pendulum angle and both measured and oracle periods. The dashed cosine
  is explicitly a **period guide**, not an exact nonlinear trajectory.
  D shows each measured error divided by its SPEC limit, with a common
  100% pass line; stick uses travel / 20 mm, not relative error to zero.
  Actual relative errors and their limits are printed above the bars.
  The near-zero pendulum bar is correctly tiny, not artificially enlarged.
- **loop.png, 2400×1600, 200 dpi:** the replay passes three, three, then
  four scenes; the overall labels are FAIL, FAIL, PASS from the recorded
  verdicts. The final iteration also passed reference agreement. Good is
  correctly shown as not killed; all eight mutants are rejected. Labels
  show the gates actually printed by selftest, including csv-shape for
  the time-stretched mutant, rather than the SPEC's predicted gate.

Titles, axes, units, legends and numeric labels are readable. No clipped
or overlapping text was seen. Blue/orange/green/purple use the
colour-blind-safe Okabe–Ito palette; dashes and text also distinguish
series, so meaning does not depend on colour alone.

## Full-size video frame check

Four frames were extracted with
`ffmpeg -ss T -i media/demo.mp4 -frames:v 1 ...` and opened at 1920×1080:

| video time | observed content |
|---|---|
| 1 s | sphere falling in the measured lane, dashed analytic ghost alongside; both heights and measured/oracle contact times visible |
| 10 s | 35° box partway down the incline, 20° box near its starting position; orange ghosts and live displacement/acceleration readouts visible |
| 19 s | pendulum near its negative-angle extremum; measured rod/bob and period-guide ghost agree closely; angles and both periods are readable |
| 26 s | four-row PASS table with measured values, oracle values and SPEC limits, plus all five gate results, judge integrity and 8/8 selftest |

No text collisions or clipping were seen. The motion comes from CSV
positions/angles, interpolated onto the video timeline. Chapters cover
the full simulated spans: drop (6 video seconds), inclines (8), pendulum
(10), then the PASS table (4).

Two deliberately stated drawing limits:

- The drop is a **sphere**, not a box: that is the actual SPEC and good
  artifact. Its analytic ghost stops at first contact and is labelled as
  held there; no post-impact analytic trajectory is claimed.
- Incline CSVs contain centers, not orientation. Box outlines retain their
  initial orientation, stated in the subtitle. The pendulum's analytic
  ghost is `θ₀ cos(2πt/T_oracle)`, labelled as a period guide.

The master is encoded with `-crf 0` in ignored `media/master/demo.mp4`.
The web file is encoded **from that master** with
`-crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart`.

## Executable checks

`render.py` checks the bounding boxes of all drawn text after a real
canvas draw: labels must stay inside the image and must not overlap.
It runs this check on both figures and **every one of the 840 video
frames**. Out-of-view locator ticks, which Matplotlib does not draw, are
excluded. The unit tests prove that actual overlapping/clipped text is
rejected and out-of-view ticks do not cause false failures.

```bash
cookbook/sim-engine-arena/media/.venv/bin/python -m unittest discover \
  -s cookbook/sim-engine-arena/media -p test_media.py -v
```

Five tests pass: exact CSV/verdict agreement; rejected incomplete or
surviving-mutant evidence; layout positive/negative controls; manifest
hashes and 200 dpi/date-free PNG metadata; undrawn-tick handling.

The source review checked fixed subprocess argument lists, quoted shell
paths, cleanup scoped to the newly created temporary directory, and no
new network service or credential handling. No security issue found.
Package-registry enrichment was not run; this is a local media review,
not a dependency vulnerability audit. Unrelated CLI/plugin CI and remote
`run.py` were not rerun: this change adds media only, and its physics
verification deliberately uses the requested local CPU path.

## Two clean builds and VERIFY output

Before each of the two successful builds, the generated PNGs, web video,
lossless master, manifest, CSVs, verdict, versions and selftest output were
removed. Installed toolchains were retained. Both builds reran setup,
selftest, full grading and the good artifact; no physics outputs were
reused. PNGs have no Software or date metadata.

Both builds printed:

```text
selftest: kill rate: 8/8 = 100%
selftest: determinism: OK
CSV oracle metrics: exactly equal to the full-run grade (4/4)
result.png: all text in bounds; no overlapping text
loop.png: all text in bounds; no overlapping text
drop_video: every frame text-checked
incline_video: every frame text-checked
pendulum_video: every frame text-checked
table_video: every frame text-checked
MANIFEST.json: hashes written; video meets duration/size/format limits
make_media: done
```

Second-build hash comparison:

```text
IDENTICAL 91f335bc8c0c8662ccb39bca836f040f92a0f8d68ca22037f119e35cd900d0d5  result.png
IDENTICAL 53af79b206af7789b273877867ee3633c87589875ee35031634379c54eec671b  loop.png
IDENTICAL 30c7abaa0122eda6d4b28f4745c70708ee988b92829b3626417a0e323e417719  demo.mp4
IDENTICAL 0acbf86d2ee3b34866748e0b704cc07085092fd6316b12e8380863c4629c5dc3  MANIFEST.json
IDENTICAL d96fcf920f9c8f4d85187aecd1f127362795b1ce995500fe6a6808727460cc0b  data/grade.json
IDENTICAL 7e239c04261d341d074d35f23c0f4cda29694c9504296cb90facfd8ec4ce572b  data/selftest.txt
Two clean builds: byte-identical PNGs, MP4, manifest and compact evidence
```

```bash
ffprobe -v error \
  -show_entries stream=codec_name,width,height,r_frame_rate,pix_fmt \
  -show_entries format=duration,size \
  -of default=noprint_wrappers=1 cookbook/sim-engine-arena/media/demo.mp4
```

```text
codec_name=h264
width=1920
height=1080
pix_fmt=yuv420p
r_frame_rate=30/1
duration=28.000000
size=1216208
```

Additional binary/source checks:

```text
Source hashes: 23/23 match
Faststart: moov precedes mdat
Master: x264 qp=0 lossless encoder settings present
```

The full five-test suite passed again after the second build. During
development the layout check initially counted undrawn locator ticks;
the out-of-view exclusion and its regression test fixed that false
positive before either successful clean build.

## Review status and limits

Implementation reviewed at `6f7dd12` against `0d1b1fb`; the only subsequent
change is this review receipt. Primary execution and visual checks: PASS.
A separate read-only execution review was attempted after an availability
probe succeeded, but produced no report within 20 minutes and was stopped.
**No independent review verdict was received or is claimed.**

The final quality pass was performed inline. Oracle extraction, CSV
parsing, shape checks and tolerances reuse the judge directly. Drawing
helpers share video framing, readouts, interpolation and box geometry.
The text-layout guard and selftest parser are media-specific; importing
another demo's figure script would also import its unrelated solver/data
requirements. Hashing uses the standard library, and tests reuse the
manifest's helper. There are no legacy formats, compatibility adapters or
speculative extension paths. No further source edits were warranted.
