# RECEIPT — aicad-text-to-cad

Real command output from the build sandbox (2 vCPU, ~3 GB RAM, Debian,
CPython 3.12.15), recorded 2026-10-14. Commands were run from the repo
root with this branch checked out. Nothing below is hand-composed; each
block is pasted from the transcript.

## `bash judge/setup.sh` (fresh venv, cold pip cache)

```
[setup] creating venv at /home/user/.venvs/aicad-judge (host python 3.12)
[setup] installing pinned, hash-checked wheels (this takes a few minutes)
...
Successfully installed Pygments-2.21.0 anytree-2.13.0 ... cadgen-0.7.2
  cadquery-ocp-novtk-7.9.3.1.1 ... manifold3d-3.5.2 ... rtree-1.4.1
  scikit-learn-1.9.1 scipy-1.18.1 shapely-2.2.0 ... trimesh-4.12.2 ...
[setup] verifying versions
[setup] kernel volume check ok: 1570.796
[setup] done. Tool: cadgen 0.7.2 — pinned, verified.

real    1m44.086s
user    1m12.641s
sys     0m13.109s
setup exit=0
```

Idempotence re-run: `[setup] judge venv already installed at
/home/user/.venvs/aicad-judge (pins unchanged)`, exit 0, < 1 s.
`judge/VERSIONS.txt` (written by the same run):

```
python = 3.12.15
cadgen = 0.7.2
build123d = 0.11.1
cadquery-ocp-novtk = 7.9.3.1.1
trimesh = 4.12.2
manifold3d = 3.5.2
ezdxf = 1.4.4
numpy = 2.5.4
shapely = 2.2.0
OCP = importable
```

## `bash judge/selftest.sh`

```
[selftest] regenerating mutants with the pinned tool...
[mutants] built plate-hole-count (adapter_plate, model.py edit)
[mutants] built plate-hole-diameter (adapter_plate, model.py edit)
[mutants] built plate-hole-drift (adapter_plate, model.py edit)
[mutants] built bracket-missing-fillet (bracket, model.py edit)
[mutants] built bracket-fillet-radius (bracket, model.py edit)
[mutants] built bushing-scale-25_4 (bushing, model.py edit)
[mutants] built bushing-non-watertight (bushing, STL byte edit)
[mutants] built plate-flipped-facet (adapter_plate, STL byte edit)
[mutants] 8 mutants in /tmp/aicad-selftest.*/mutants

[selftest] known-good parts (must PASS):
[selftest]   good/bushing  PASS  (27s)
[selftest]   good/adapter_plate  PASS  (25s)
[selftest]   good/bracket  PASS  (27s)

[selftest] determinism (same seed twice, verdict JSON minus 'timing'):
[selftest]   bushing: byte-identical (minus timing)  OK
[selftest]   adapter_plate: byte-identical (minus timing)  OK
[selftest]   bracket: byte-identical (minus timing)  OK

[selftest] mutants (each must FAIL >= 1 gate):
[selftest]   bracket-fillet-radius  killed by: features
[selftest]   bracket-missing-fillet  killed by: features, volume_analytic
[selftest]   bushing-non-watertight  killed by: delivery_matches, stl_valid
[selftest]   bushing-scale-25_4  killed by: bbox, features, volume_analytic
[selftest]   plate-flipped-facet  killed by: delivery_matches, stl_valid
[selftest]   plate-hole-count  killed by: features, volume_analytic
[selftest]   plate-hole-diameter  killed by: features, volume_analytic
[selftest]   plate-hole-drift  killed by: features

[selftest] summary: good 3/3 pass, determinism 3/3, mutants killed 8/8 (kill rate 100%)
[selftest] OK

real    8m21.023s
selftest exit=0
```

## `bash judge/grade.sh examples/good/bushing --seed 42 --json /tmp/v.json`

```
verdict: {"pass": true, "part": "bushing", "seed": 42, ...}
  tool_runs           PASS   exit 0, wrote model.step + model.stl
  delivery_matches    PASS   sha256 delivered == fresh regen (both files)
  step_valid          PASS   BRepCheck valid, 1 solid
  stl_valid           PASS   watertight, winding consistent, 1 body, 1006 facets
  bbox                PASS   36x36x40 vs spec, max dev 0.0 mm (STL vs STEP 0.0)
  volume_analytic     PASS   15054.511996 mm3 vs analytic 15054.511996, rel 0.0
  xor_volume          PASS   XOR 0.0 mm3 (0.0 % of reference 15054.511996)
  features            PASS   shaft r10 / flange r18 / bore r5 x1, centre (0,0)
  min_wall            PASS   4.927 mm >= 5.0 - 0.1 (48 seeded rays)
  judge_intact        PASS   7 files under judge/ unchanged

real    0m22.386s
grade exit=0
```

`adapter_plate` and `bracket` grade the same way (exit 0; key numbers:
plate volume rel err 0.0 / XOR 0.0; bracket volume rel err 0.0 / XOR
0.0 / min wall 2.5). Full JSONs: `--json /tmp/v.json` per part, seed 42.

## Fresh-sandbox runs via `run.py`

(not done: this build sandbox cannot create agent-next sandboxes — the
`sbx` CLI needs SBX_API_KEY and an outside-in connection. run.py was
verified instead by `python3 -m py_compile` and by running its exact
in-sandbox command sequence (`clone → setup → selftest → grade`)
verbatim via `bash -c` in a scratch dir: all four steps exit 0. The
lead's end-to-end `run.py` output belongs here: sandbox id, per-step
wall times, verdict JSON, `sbx kill` + `sbx list` confirmation.)

Two fresh-sandbox runs, side by side (required by DEMO-STANDARD.md):
(not done: same reason — to be filled from two `run.py` runs in fresh
sandboxes before merge; expected identical: byte-identical delivery
files are enforced by gate 2 and every pinned wheel is sha256-checked.)

## Independent reproduction (REPRODUCE.md)

(not done: requires a different agent following only README.md in a
fresh sandbox; must happen before merge per DEMO-STANDARD.md.)

## Deviations

- **Delivered files are checked in** (`examples/*/model.step|.stl`, each
  < 120 KB), not git-ignored as SPEC.md first said: the judge grades the
  DELIVERED files, so the known-good artifact must ship them. SPEC.md
  was amended (commit history records the change).
- **`bracket-missing-fillet` dies at features + volume_analytic**, not
  xor_volume as SPEC.md first predicted: replacing the R5 arc with its
  chord changes volume by only 0.58 %, below the XOR gate's deliberate
  1 % bar (SPEC.md amended). Every other mutant died exactly where the
  SPEC table predicted.
- **`pip install --upgrade pip` inside setup.sh is unpinned** (26.2.1);
  pip installs nothing the judge imports — every judge-touched package
  is hash-pinned in requirements.txt.
- **Python floor is 3.12**, not cadgen's own 3.11: the pinned
  numpy 2.5.4 / scipy 1.18.1 / contourpy 1.4.0 ship no cp311 wheels.
  setup.sh fails loudly on older interpreters.
- **Media** (media/, make_media.sh) not built in this task: explicitly
  out of scope per the task instructions ("Do NOT do media").
- ezdxf is installed and recorded (a cadgen dependency) but no gate is
  DXF-based: the three specs are solid parts, no 2D drawings (SPEC.md
  "Non-goals").
