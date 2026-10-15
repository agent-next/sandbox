# Blender studio acceptance specification

## Goal and artifact

Produce a centered red car-paint Suzanne on a stone plinth, with a glass orb,
gold torus, smooth cyclorama, and a seamless 12-frame turntable. The artifact is
`examples/good/scene.py`: a Blender scene script using the documented
`from studio import build_scene`, literal `SETTINGS` dictionary, and
`build_scene(SETTINGS)` skeleton. The optional leading docstring is allowed.
Agents edit the eight settings, not the judge. No executable edits, duplicate
keys, imports, calls, NaN, or extra fields are accepted.

The recipe is an original implementation derived from the **scene design** of
the public `blender` sandbox template's `product_shot.py`, inspected through
https://sbx.agent-next.com on 2026-10-15. Its source SHA-256 was
`0717b9cec97dffc0d857ce65eacead84aaeefa314cfeed61b08da027d7cf87a4`.
No third-party source or downloaded assets are copied. Repository MIT licensing
applies to this implementation. Blender itself is GPL-licensed and is not
redistributed here.

Settings: `hero_x` [-5,5] m; `camera_y` [-20,-1] m; `key_energy`
[0,1000000] W; integer `period` [2,120] frames; boolean `rim_link` and
`halo_link`; `seam_height` [0,8] m (zero disables the fault); and `exposure`
[-10,10] stops. Other scene choices are fixed.

## Independent acceptance oracle

The submitted script is **parsed, never executed by the judge**. Its AST must
match the skeleton after replacing only the literal dictionary. A trusted copy
of `judge/studio.py` builds the scene from validated data. `grade.py` copies the
artifact and judge into a temporary directory, starts factory-clean Blender,
and computes measurements from Blender's own output. Judge files are SHA-256
checked before and after. No artifact-provided score, image, metadata, object
label, or render settings are trusted.

| gate | numeric rule | independent measurement and failure |
| --- | --- | --- |
| G1 framing | projected hero bounding-box area / frame area 0.07–0.22; center x within 0.055 of 0.5, y within 0.12; all vertices inside 4% frame margins and in front of near clip | Project every evaluated subdivided hero vertex through the actual camera. Off-center or too-close camera fails. This is bounding-box coverage, not silhouette area. |
| G2 exposure | mean display-referred RGB luminance 0.15–0.65; fraction with any channel >=253/255 <=0.005 | Read judge-rendered 8-bit PNG pixels; luminance weights 0.2126/0.7152/0.0722. Eight extra exposure stops fails. This is a display clipping gate, not an HDR energy-conservation claim. |
| G3 backdrop | >=99.5% of two background strips see Cyclorama; >=4000 valid difference pixels; maximum vertical second luminance difference <=0.055 | Independent primary ray casts verify the strips (x 8–47 and 208–247, bottom-up y 78–133 at 256×144). Three vertically adjacent pixels must all see backdrop. A foreign seam object fails visibility even if its dark pixels would otherwise be masked out. Large gradient discontinuities fail smoothness. |
| G4 loop | each of 12 evaluated angular steps differs from 2π/12 by <=0.00001 radians; frame 1 vs 13 mean absolute RGB difference <=0.003 | Read evaluated Turntable rotation after setting every frame, then render both endpoints at the same seed. A period of 13 fails both speed and endpoint gates. Checking only the endpoint would incorrectly accept extra complete revolutions. |
| G5 linking | direct-only rim-on/off backdrop mean RGB delta <=0.001; product delta >=0.001; exact rim receivers GlassOrb/GoldRing/Hero/Plinth and halo receiver Cyclorama | Two additional renders with all other lights/world disabled, zero indirect bounces, and independent primary-ray masks. The positive product signal prevents a missing/off rim from passing vacuously. Wrong rim or halo receiver collection fails. |

All five gates and unchanged judge checksums must pass. Exceptions, missing
measurement output, or a 120 s grade subprocess timeout fail closed.

## Determinism and self-test

Pinned template tools: Blender **5.2.2 LTS**, build `d13f752e3b9c`; embedded
Python 3.13.13 / NumPy 2.3.4; host Python 3.13.5. `setup.sh` checks these exact
versions and writes `judge/VERSIONS.txt`. It idempotently creates its state
directory under `$HOME`; it installs no packages and downloads nothing.
Thus there are no unverified archives, pip dependencies, or new releases to
install. The Blender build predates this work by a month.

Hero and endpoint: Cycles CPU, four fixed threads, 256×144, 8 fixed samples,
OpenImageDenoise, no adaptive sampling, AgX Punchy, seed 17 by default.
Linking probes: 128×72, 4 samples, no denoising, no indirect bounces.
No animated seed. `--seed` controls all stochastic renders.
`selftest.sh` grades good twice and compares the serialized JSON after removing
only `timing`. All seven single-setting mutants must fail an actual numeric
gate, with no runtime error and unchanged judge. Required kill rate is 100%
(stricter than the standard's 90%).

Cross-sandbox comparison tolerances: framing 0.00001, angular error 0.000001
rad, display luminance and image-difference metrics 0.002, backdrop difference
0.01. All gate booleans, receiver lists, seed and render settings must agree.
Within one pinned sandbox, repeat verdicts must be byte-identical excluding
`timing`, not merely within tolerance.

## Limits and non-goals

Not an unrestricted Python execution judge, a photorealism score, a material
physics certification, a full animation occlusion audit, or a hardware benchmark.
The output is a finite constrained studio-design task. The grader controls the
objects, so renaming an object cannot change a mask. Light-linking excludes
direct light, not physically valid indirect bounce, which is why the linking
probe explicitly disables indirect bounces.

The live runner clones a public repository ref (default `main`) and then uploads
the exact source snapshot of the local demo. This deliberate pre-publication
overlay allows two real runs without pushing an unpublished branch. Both the
clone commit and the uploaded snapshot SHA-256 are printed. Media uses the same
scene/settings/seed at 1920×1080, 8 samples; grade thresholds are evaluated only
at the pinned small judge resolution.
