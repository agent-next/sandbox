# RECEIPT — usd-validate-fix

Real output, pasted verbatim, of the three commands the standard requires,
from **two runs**, each with the judge venv wiped first (setup from
nothing; same disposable Debian sandbox, 2 vCPU / 3.8 GiB, Python
3.12.15). Commands were run from `cookbook/usd-validate-fix/`.

## Run 1

### `bash judge/setup.sh` — exit 0, 38.7 s

```text
$ bash judge/setup.sh
setup: creating venv /home/user/.usd-validate-fix-venv and installing pinned wheels
setup: wrote /home/user/w/cookbook/usd-validate-fix/judge/VERSIONS.txt
setup: done

real	0m38.711s
user	0m11.795s
sys	0m3.793s
EXIT=0
```

`judge/VERSIONS.txt` after the run:

```text
# usd-validate-fix judge: versions installed by judge/setup.sh
# (Linux x86_64)
python3 3.12.15 (venv: 3.12.15)
usd-core 25.5
usd-validation-nvidia 1.22.0
nvidia_usd_validate path: /home/user/.usd-validate-fix-venv/bin/nvidia_usd_validate
usd-core==25.5
usd-validation-nvidia==1.22.0
```

Idempotent re-run (nothing wiped): `setup: venv ... already has the
pinned versions (skipping install)`, exit 0, ~2 s.

### `bash judge/selftest.sh` — exit 0, 1 m 24.7 s, kill rate 11/11 = 100 %

```text
$ bash judge/selftest.sh
selftest: grading known-good /home/user/w/cookbook/usd-validate-fix/examples/good/traffic_cone_fixed.usda
selftest: known-good PASSED all gates
mutants: wrote /tmp/tmp.tsOTf2ZQME/mutants/no_normals.usda (no_normals)
mutants: wrote /tmp/tmp.tsOTf2ZQME/mutants/mpu_1.usda (mpu_1)
mutants: wrote /tmp/tmp.tsOTf2ZQME/mutants/upaxis_z.usda (upaxis_z)
mutants: wrote /tmp/tmp.tsOTf2ZQME/mutants/zero_face.usda (zero_face)
mutants: wrote /tmp/tmp.tsOTf2ZQME/mutants/unbind.usda (unbind)
mutants: wrote /tmp/tmp.tsOTf2ZQME/mutants/no_defaultprim.usda (no_defaultprim)
mutants: wrote /tmp/tmp.tsOTf2ZQME/mutants/no_extent.usda (no_extent)
mutants: wrote /tmp/tmp.tsOTf2ZQME/mutants/delete_band.usda (delete_band)
mutants: wrote /tmp/tmp.tsOTf2ZQME/mutants/scale_points.usda (scale_points)
mutants: wrote /tmp/tmp.tsOTf2ZQME/mutants/short_normals.usda (short_normals)
mutants: wrote /tmp/tmp.tsOTf2ZQME/mutants/no_collision.usda (no_collision)
mutants: 11 mutants
selftest: killed    delete_band (gate: geometry)
selftest: killed    mpu_1 (gate: oracle)
selftest: killed    no_collision (gate: oracle)
selftest: killed    no_defaultprim (gate: validator)
selftest: killed    no_extent (gate: validator)
selftest: killed    no_normals (gate: validator)
selftest: killed    scale_points (gate: validator)
selftest: killed    short_normals (gate: validator)
selftest: killed    unbind (gate: oracle)
selftest: killed    upaxis_z (gate: oracle)
selftest: killed    zero_face (gate: validator)
selftest: kill rate 11/11 = 100%
selftest: determinism OK (two --seed 1 runs identical except timing)
selftest: OK

real	1m24.686s
user	0m30.988s
sys	0m4.196s
EXIT=0
```

(The mutant `wrote ...` lines' only run-to-run difference is the mktemp
directory name.)

### `bash judge/grade.sh examples/good/traffic_cone_fixed.usda --json /tmp/v.json` — exit 0, 8.2 s

```text
$ bash judge/grade.sh examples/good/traffic_cone_fixed.usda --json /tmp/v.json
{ ...full verdict JSON printed to stdout... }

real	0m8.192s
EXIT=0
```

Verdict JSON body (timing key shown separately; this is what lands in
`/tmp/v.json`):

```json
{
 "artifact": ".../examples/good/traffic_cone_fixed.usda",
 "failed_gate": null,
 "gates": {
  "geometry": {"errors": [], "passed": true},
  "oracle": {"errors": [], "passed": true},
  "validator": {"errors": [], "issues_by_severity": {},
                "passed": true, "rules_not_passing": [],
                "validator_exit": 0, "validator_status": "PASS"}
 },
 "passed": true,
 "seed": 0,
 "timing": {"geometry_s": 0.013, "oracle_s": 0.94,
            "total_s": 7.717, "validator_s": 6.756}
}
```

Key facts from `facts.oracle` (the independent recount): normals/corners
24/24 (Base), 60/60 (Body), 40/40 (Band); max unit-length deviation
1.7e-08; zero-area faces 0; bound materials 3/3; colliders 1;
`metersPerUnit = 0.01`, `upAxis = "Y"`, `defaultPrim = "TrafficCone"`.
`facts.geometry`: mesh paths identical to the original, point counts
8/20/20, bbox deviation 0.0 cm on every mesh (limit 1e-06).

Grading the **broken** task asset fails as it must:

```text
$ bash judge/grade.sh task/traffic_cone_broken.usda --json /tmp/b.json
EXIT=1   failed_gate: validator
         oracle errors: metersPerUnit = 1.0 != 0.01, upAxis = 'Z' != 'Y'
         validator: nvidia_usd_validate exited 1, status 'FAIL' != 'PASS'
```

## Run 2 (venv wiped before setup)

| command | exit | wall | run 1 wall |
|---|---|---|---|
| `bash judge/setup.sh` | 0 | 38.9 s | 38.7 s |
| `bash judge/selftest.sh` | 0 | 1 m 26.7 s | 1 m 24.7 s |
| `bash judge/grade.sh examples/good/traffic_cone_fixed.usda --json /tmp/v2.json` | 0 | 7.6 s | 8.2 s |

Self-test run 2: same 11 `killed` lines (same gate attribution), kill
rate 11/11 = 100 %, determinism OK. Verdict `/tmp/v2.json` equals
`/tmp/v.json` byte-for-byte after removing the `timing` key
(`timing` run 2: `{geometry_s: 0.027, oracle_s: 1.555, total_s: 6.976,
validator_s: 5.394}`); all gate pass/fail values and key numbers
identical.

## Traceability

- Every number above was produced by the commands shown, in
  `cookbook/usd-validate-fix/` of this repo at the demo-build commit,
  with `judge/VERSIONS.txt` as recorded above.
- Pinned inputs: `usd-core==25.5` and `usd-validation-nvidia==1.22.0`,
  sha256-checked via `pip --require-hashes` (`judge/requirements.txt`).
  The validator wheel is the official PyPI release of commit
  `14a998c0445f33140f56879e165691c2955afca1`.
- `judge/setup.sh --make-assets` regenerates
  `task/traffic_cone_broken.usda` and
  `examples/good/traffic_cone_fixed.usda` byte-identically to the
  committed files (verified with `git status` empty after regeneration).

## Deviations

- **Two fresh *agent-next sandboxes*: not done from inside this build
  sandbox** (the `sbx` CLI cannot create sandboxes here). The two runs
  above each start from a wiped `$HOME` venv — setup from nothing — in
  the same disposable Debian sandbox. The lead's end-to-end `run.py`
  execution provides the fresh-sandbox run.
- **REPRODUCE.md: not done** — per DEMO-STANDARD.md it is written by a
  different agent (different model family) following README.md alone,
  before merge.
- **media/: not done** — a later task in this plan owns media
  generation.
- SPEC.md gate 1 originally named two disabled rules; the second
  (`UsdShadeShaderSdrCompliance`) does not exist at the pinned release
  and the CLI rejects it (exit 2). Gate 1 disables exactly
  `MaterialUsdPreviewSurfaceChecker`; SPEC.md was corrected in this
  branch.
- The original plan (and the census build) built the validator from the
  git clone with `uv`. The official PyPI 1.22.0 wheel of that same
  commit is installed instead: verified byte-identical validator code
  (all 90 `.py` modules except 4 generated Sphinx-metadata files that
  differ only in generated example-snippet ordering/paths, which no gate
  reads). This removes the `uv` dependency and adds a sha256 pin.
