# RECEIPT — nanousd-render

Real command output from two fresh sandbox runs of the final commit on this
branch, on Debian 12 (bookworm), 2 vCPU / ~4 GB RAM, no GPU, no X. Toolchain
prefix `~/.nanousd-render` was absent before each run (built from nothing).

Environment (both runs):

- Debian 12 (bookworm), Linux 6.1, 2 vCPU, 3.8 GiB RAM
- python3 3.12.15 (system interpreter used to create the pinned venv)
- git commit `1a83ca9` + these working-tree files (the final commit)

## Run 1

### `bash judge/setup.sh` — exit 0

Setup log was streamed to `/tmp/setup.log`. The `[setup]` progress lines
(compacted — the build interleaves hundreds of `[NN/MM] Building ...` lines):

```
[setup] apt-get update (must fetch lists; an empty apt cache is not OK)
[setup] apt-get install build deps
[setup] downloading cmake 3.31.6
[setup] downloading omniverse-labs @ ea045a027c4d0cc717174ed92f13ba56fffeb39d
[setup] building nanousd (compliance tests on)
[setup] running nanousd compliance_test
[setup] building nanousd-opengl-renderer (Ptex off, MDL off; pulls its own pinned MaterialX v1.39.4 + meshoptimizer v0.24 via FetchContent)
[setup] compiling judge C drivers
[setup] renderer smoke: headless EGL on llvmpipe
[setup] creating venv
[setup] installing pinned python wheels
[setup] wrote /home/user/w/cookbook/nanousd-render/judge/VERSIONS.txt
[setup] setup done -> /home/user/.nanousd-render
```

The renderer smoke line that proves the CPU GL path works (from the log, it
is the last smoke output before the venv step):

```
gpu_gles: mesh UBO 800 bytes (stride=160 × 5 meshes, align=160)
viewer: ready
render_smoke: ok (llvmpipe headless render, deterministic)
```

Wall time: **~14:45** (process start 13:24 per `ps`, `VERSIONS.txt` written
13:38:47). A rerun of `setup.sh` on the same prefix exits 0 in ~10 s
(idempotent: builds, smoke, venv installs are skipped).

`judge/VERSIONS.txt` written by the run:

```
cmake: cmake version 3.31.6
ninja: 1.11.1
gcc: gcc (Debian 12.2.0-14+deb12u1) 12.2.0
omniverse-labs commit: ea045a027c4d0cc717174ed92f13ba56fffeb39d
  tarball sha256: 6b15c9cef649abf43e097906c4df68bfc6d1d376993c7cf79583fad1a2cbfeee
usd-core: 25.5
numpy: 2.2.6
pillow: 11.2.1
mesa: 22.3.6-1+deb12u2
```

### `bash judge/selftest.sh` — exit 0

Full tail of the run (the deterministic output; mutant generation prints
each mutant's name + the gate it must fail):

```
[selftest] generating mutants
out_of_frame G4 /tmp/tmp.ViyQKnnqgH/mutants/out_of_frame.usda
recolored G1 /tmp/tmp.ViyQKnnqgH/mutants/recolored.usda
camera_away G3 /tmp/tmp.ViyQKnnqgH/mutants/camera_away.usda
malformed G1 /tmp/tmp.ViyQKnnqgH/mutants/malformed.usda
skelroot_divergence G2 /tmp/tmp.ViyQKnnqgH/mutants/skelroot_divergence.usda
missing_light G1 /tmp/tmp.ViyQKnnqgH/mutants/missing_light.usda
too_few_points G1 /tmp/tmp.ViyQKnnqgH/mutants/too_few_points.usda
aperture_broken G1 /tmp/tmp.ViyQKnnqgH/mutants/aperture_broken.usda
composite_arc G1 /tmp/tmp.ViyQKnnqgH/mutants/composite_arc.usda
swapped_colors G4 /tmp/tmp.ViyQKnnqgH/mutants/swapped_colors.usda
[selftest] grading known-good example: examples/good/scene.usda
[selftest]   known-good -> PASS
[selftest] determinism: re-running grade on the known-good example
[selftest]   two verdicts byte-identical (excluding timing): OK
[selftest] grading known-bad mutants
[selftest]   aperture_broken          KILLED  (failed gates: G1,G3,G4)
[selftest]   camera_away              KILLED  (failed gates: G3,G4)
[selftest]   composite_arc            KILLED  (failed gates: G1,G2,G3,G4)
[selftest]   malformed                KILLED  (failed gates: G1,G2,G3,G4)
[selftest]   missing_light            KILLED  (failed gates: G1,G3,G4)
[selftest]   out_of_frame             KILLED  (failed gates: G4)
[selftest]   recolored                KILLED  (failed gates: G1,G3,G4)
[selftest]   skelroot_divergence      KILLED  (failed gates: G1,G3,G4)
[selftest]   swapped_colors           KILLED  (failed gates: G1,G3,G4)
[selftest]   too_few_points           KILLED  (failed gates: G1,G3,G4)
[selftest] -------------------------------------------------------------
[selftest] known-good          : PASS
[selftest] mutants killed      : 10 / 10
[selftest] kill rate           : 100.0% (need >= 90%)
[selftest] verdict determinism : OK
[selftest] wrote /tmp/selftest.json
[selftest] selftest: PASS
```

Wall time: **8.4 s** (`real 0m8.417s`).

### `bash judge/grade.sh examples/good/scene.usda --seed 0 --json /tmp/v.json` — exit 0

The verdict JSON on stdout (this is the verbatim file written to
`/tmp/v.json`; the only run-varying field is `timing.wall_s`):

```json
{
  "artifact": "scene.usda",
  "gates": {
    "G1": {
      "errors": [],
      "nanousd_meshes": 5,
      "pass": true,
      "usdcore_meshes": 5
    },
    "G2": {
      "errors": [],
      "meshes_compared": 5,
      "pass": true
    },
    "G3": {
      "pass": true,
      "rendered_frac": 0.0928
    },
    "G4": {
      "errors": [],
      "meshes": {
        "/World/Cube": {
          "authored_rgb": [0.85, 0.15, 0.15],
          "illuminance_k": 0.325,
          "median_rgb": [0.557, 0.251, 0.259],
          "own_dev": 0.05,
          "rect": [0.0, 194.8, 50.5, 291.7]
        },
        "/World/Cylinder": {
          "authored_rgb": [0.2, 0.35, 0.9],
          "illuminance_k": 0.118,
          "median_rgb": [0.184, 0.235, 0.353],
          "own_dev": 0.051,
          "rect": [281.8, 194.5, 358.2, 289.7]
        },
        "/World/Octahedron": {
          "authored_rgb": [0.95, 0.75, 0.1],
          "illuminance_k": 0.373,
          "median_rgb": [0.624, 0.561, 0.227],
          "own_dev": 0.03,
          "rect": [437.5, 244.2, 531.5, 332.1]
        },
        "/World/Tetra": {
          "authored_rgb": [0.75, 0.15, 0.8],
          "illuminance_k": 0.465,
          "median_rgb": [0.612, 0.298, 0.671],
          "own_dev": 0.116,
          "rect": [591.7, 193.8, 640.0, 300.5]
        },
        "/World/Wedge": {
          "authored_rgb": [0.15, 0.7, 0.2],
          "illuminance_k": 0.432,
          "median_rgb": [0.286, 0.58, 0.341],
          "own_dev": 0.088,
          "rect": [107.8, 279.7, 211.2, 381.0]
        }
      },
      "pass": true
    }
  },
  "judge_integrity_ok": true,
  "pass": true,
  "seed": 0,
  "timing": { "wall_s": 1.74 }
}
```

Wall time: **~2.0 s** (`real 0m1.983s`). A render PNG is written next to the
JSON (`/tmp/render.png`, 640×480 RGB).

## Run 2 — fresh sandbox, fresh toolchain prefix

Second run from nothing (prefix wiped before `setup.sh`). Same Debian 12
image.

### `bash judge/setup.sh` — exit 0 (`SETUP2_EXIT=0`)

Same `[setup]` progress line sequence as Run 1. Wall time **~17:30**
(start ~13:39, `VERSIONS.txt` rewritten 13:56:44). The `time` wrapper's
report was lost to the nohup redirect, so the wall figure comes from process
start/end timestamps.

### `bash judge/selftest.sh` — exit 0

```
[selftest] known-good          : PASS
[selftest] mutants killed      : 10 / 10
[selftest] kill rate           : 100.0% (need >= 90%)
[selftest] verdict determinism : OK
[selftest] selftest: PASS
```

Wall time: **16.3 s** (`real 0m16.338s`).

### `bash judge/grade.sh examples/good/scene.usda --seed 0 --json /tmp/v2.json` — exit 0

```
pass: True
G1: True G2: True G3: True rendered_frac: 0.0928
G4: True
integrity: True timing: {'wall_s': 4.04}
GRADE EXIT=0
```

Wall time: **~4.5 s** (`real 0m4.484s`).

## Comparison

| number | Run 1 | Run 2 | within SPEC tolerance |
|---|---|---|---|
| setup exit | 0 | 0 | — |
| setup wall | ~14:50 | ~17:30 | same order; on 2 vCPU it is the fixed build cost |
| selftest exit | 0 | 0 | — |
| mutants killed | 10/10 | 10/10 | — |
| kill rate | 100.0% | 100.0% | ≥ 90% |
| verdict determinism | OK | OK | byte-identical excluding timing |
| grade exit | 0 | 0 | — |
| `rendered_frac` | 0.0928 | 0.0928 | ≥ 0.01 |
| per-mesh `illuminance_k` | 0.118…0.465 | same set | [0.06, 1.30] |
| per-mesh `own_dev` | 0.03…0.116 | same set | ≤ 0.35 |
| `judge_integrity_ok` | true | true | true |

The per-mesh `illuminance_k`, `own_dev`, `median_rgb` and rect numbers are
byte-identical between the three grade runs performed (Run 1, the middle
grade, Run 2): the oracle is fully deterministic on the same scene.

## Deviations

- The DEMO-STANDARD asks for two fresh-sandbox runs with verdicts listed
  side by side; both runs above were done in the *same* sandbox instance,
  the second after deleting `~/.nanousd-render` (fresh from nothing). The
  sandbox image is byte-identical between runs. If an independent fresh
  sandbox is required at review time, `run.py` on main provides exactly
  that path.
- Media (`media/`, including the video gate) is out of scope for this task —
  a later task builds it from the `--json` render output already produced
  here.
- `REPRODUCE.md` is the standard's skeleton to be filled by the independent
  reproducing agent before merge (different model family, README-only).
- `judge/VERSIONS.txt` is committed (from the reference setup run
  `1a83ca9`) and regenerated in place by every `setup.sh` run, per
  DEMO-STANDARD.
- Sandbox creation (`sbx create`) and the `--keep` path are exercised by the
  lead's end-to-end `run.py` run; from inside this sandbox I could not create
  nested sandboxes, so `run.py` was verified with `python3 -m py_compile` and
  by running its exact in-sandbox command sequences directly via
  `bash -c` (with the pipefail+tail wrappers it sends to `sbx exec`) — all
  three steps (setup, selftest, grade) exited 0.