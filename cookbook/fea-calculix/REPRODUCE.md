VERDICT: REPRODUCED

# fea-calculix — independent reproduction from README.md

Reproducer run, 2026-10-14 (UTC), Debian 12 (bookworm) container,
2 vCPU / 3.8 GB RAM — same image class the `sbx` sandbox runs.
Followed README.md literally: `judge/setup.sh` → `judge/selftest.sh` →
`judge/grade.sh examples/good --seed 42` (the sequence `run.py` performs
inside its sandbox). RECEIPT.md was read only after all numbers below
were in hand.

## 1. Setup — `bash judge/setup.sh`

Fresh sandbox had no `~/tools` (README's "already installed" applies to
the `sbx` sandbox; here setup had to be run — see §6). Exit 0, wall
12.4 s (README table: ~15 s).

```
== downloading http://deb.debian.org/debian/pool/main/c/calculix-ccx/calculix-ccx_2.20-1_amd64.deb ==
/tmp/tmp.ygi41EG5jF/calculix-ccx_2.20-1_amd64.deb: OK
== downloading http://deb.debian.org/debian/pool/main/s/spooles/libspooles2.2_2.2-14_amd64.deb ==
/tmp/tmp.ygi41EG5jF/libspooles2.2_2.2-14_amd64.deb: OK
== downloading http://deb.debian.org/debian/pool/main/a/arpack/libarpack2_3.8.0-3_amd64.deb ==
/tmp/tmp.ygi41EG5jF/libarpack2_3.8.0-3_amd64.deb: OK
== downloading https://gmsh.info/bin/Linux/gmsh-4.10.0-Linux64.tgz ==
/tmp/tmp.nMq858Pm08/gmsh-4.10.0-Linux64.tgz: OK
ccx: This is Version 2.20
gmsh: 4.10.0
setup complete -> /home/user/tools/bin
EXIT CODE: 0
real 0m12.371s
```

All four pinned downloads sha256-checked OK. `judge/VERSIONS.txt`
(written by setup.sh): ccx 2.20-1, libspooles2.2 2.2-14, libarpack2
3.8.0-3, gmsh 4.10.0, python3 3.12.15.

## 2. Selftest — `bash judge/selftest.sh`

Exit 0, wall 4m58.6s (298.6 s; README: ~5 min).

```
== selftest: known-good artifact ==
known-good: PASS (expected)
== selftest: generating known-bad mutants ==
mutant coarse-mesh: FAIL (expected) -- killed by gate: verification, convergence, spec_limits
mutant load-on-ntip: FAIL (expected) -- killed by gate: verification, convergence, spec_limits
mutant load-wrong-dof: FAIL (expected) -- killed by gate: verification, convergence, spec_limits
mutant no-stress-output: FAIL (expected) -- killed by gate: verification, convergence, spec_limits
mutant overload-10x: FAIL (expected) -- killed by gate: verification, spec_limits
mutant propped-tip: FAIL (expected) -- killed by gate: verification, spec_limits
mutant unconverged: FAIL (expected) -- killed by gate: convergence
mutant undersized: FAIL (expected) -- killed by gate: spec_limits
mutant units-in-metres: FAIL (expected) -- killed by gate: spec_limits
== selftest summary ==
known-good: passed
kill rate: 9/9 (100%)
== selftest: determinism (grade twice with --seed 42) ==
determinism: PASS (two --seed 42 runs identical excluding "timing")
selftest: PASS
EXIT CODE: 0
real 4m58.621s
```

## 3. Grade the good example — `bash judge/grade.sh examples/good --seed 42`

Exit 0, wall 32.7 s (README: ~35 s). Verdict JSON:

```json
{
  "verdict": "PASS",
  "timing": {"wall_s": 32.6},
  "gates": {
    "verification": {"pass": true, "detail": "reference beam vs Euler-Bernoulli: deflection 0.4016 vs 0.4000 mm (+0.41%), stress 11.91 vs 12.00 MPa (-0.74%); tolerance 3%"},
    "convergence": {"pass": true, "detail": "mesh 4 vs 2 mm (11250 -> 60000 elements): deflection change 0.23%, stress change 0.50%; tolerance 2%"},
    "spec_limits": {"pass": true, "detail": "sigma 138.2 <= allowable 166.7 MPa; deflection 7.72 <= limit 10.00 mm"}
  },
  "metrics": {
    "L_mm": 1000.0, "b_mm": 12.0, "h_mm": 60.0, "mesh_size_mm": 4.0,
    "mass_g": 5652.0, "ref_delta_mm": 0.4016, "ref_sigma_mpa": 11.911,
    "coarse_elems": 11250, "fine_elems": 60000,
    "delta_mm": 7.7221, "sigma_mpa": 138.241
  }
}
```

Byte-identical to committed `media/data/verdicts/good.json` except
`timing.wall_s` (32.6 vs 35.5).

## 4. Comparison with RECEIPT.md (match / mismatch per item)

| item | this run | RECEIPT.md | SPEC tolerance | result |
|---|---|---|---|---|
| verdict (good) | PASS | PASS | all gates must pass | match |
| EB deflection error (ref beam) | +0.41 % | +0.41 % | ≤ 3 % | match |
| EB stress error (ref beam) | −0.74 % | −0.74 % | ≤ 3 % | match |
| convergence deflection / stress | 0.23 % / 0.50 % | 0.23 % / 0.50 % | ≤ 2 % | match |
| sigma_wall | 138.241 MPa | 138.241 MPa | ≤ 166.667 MPa | match |
| tip deflection | 7.7221 mm | 7.7221 mm | ≤ 10.00 mm | match |
| mass | 5652.0 g | 5652.0 g | informational | match |
| mesh elements coarse → fine | 11250 → 60000 | 11250 → 60000 | — | match |
| ref_delta / ref_sigma | 0.4016 mm / 11.911 MPa | 0.4016 / 11.911 | — | match |
| kill rate | 9/9 (100 %) | 9/9 (100 %) | ≥ 90 % | match |
| determinism (same seed, excl `timing`) | identical | identical | byte-identical | match |
| ccx version | 2.20 ("This is Version 2.20") | 2.20 | — | match |
| gmsh version | 4.10.0 | 4.10.0 | — | match |
| python3 | 3.12.15 | 3.12.15 | — | match |
| setup wall | 12.4 s | 10 s / 16 s | — | match (ballpark) |
| selftest wall | 298.6 s | 311 s / 300 s | — | match (ballpark) |
| grade wall | 32.7 s | 34 s / 34 s | — | match (ballpark) |
| mutant gates: 8 of 9 | — | — | — | match |
| mutant overload-10x gates | verification, spec_limits | spec_limits | — | **mismatch** |

**The one mismatch — overload-10x gate attribution.** RECEIPT.md's
pasted per-mutant block says `killed by gate: spec_limits`; this run
says `verification, spec_limits`. The mutant's verdict is FAIL in both
and the kill rate is unaffected (9/9, 100 % both). The repo's own
committed `media/data/verdicts/overload-10x.json` agrees with this run
(`failed gates = ['verification', 'spec_limits']`), as do all nine
committed mutant verdict JSONs with this run's gate attribution. The
RECEIPT prose line is stale relative to the tree it ships with; every
measured quantity matches.

**Tool-version note.** The repo's top-level `VERSIONS.txt` says
`python3: 3.11.2-1+b1`, but the interpreter on PATH (and the one
`grade.sh`/`judge.py` actually ran under) is `/usr/local/bin/python3`
= 3.12.15, matching `judge/VERSIONS.txt` and RECEIPT.md. The
top-level file is stale; no effect on results.

## 5. Determinism — `grade.sh` twice with `--seed 42`, diff excl. `timing`

Two explicit runs (exit 0 each; 34.8 s and 37.0 s wall):

```
$ python3 -c "load both, pop('timing'), compare"
run1 == run2 (excl timing): True
$ diff <(run1 sans timing) <(run2 sans timing)
(no output — no differences)
timing: run1 wall_s 34.7, run2 wall_s 36.9
```

Identical excluding `timing`, as README/SPEC require. (Selftest's
internal determinism check also passed, §2.)

## 6. Media rebuild — `bash media/make_media.sh`

Exit 0, wall 4m52.9s. Solved real ccx fields: good-coarse (11250
elements), good-fine (60000), overload-10x (60000), undersized (40000),
propped-tip (60000), load-on-ntip (60000); `convergence.json` rewritten
("delta 0.23% sigma 0.50% (verdict agrees)"); demo.mp4 33.5 s,
1920x1080, 0.77 MB.

sha256 of rebuilt files vs committed `media/MANIFEST.json`:

| file | MANIFEST sha256 | rebuilt sha256 | bytes (manifest vs rebuilt) | match |
|---|---|---|---|---|
| result.png | dceaa8bbe5f68344435cae93fb8a2b2ef30a8ebc539ecb54cab61b7f933cca4e | same | 373759 vs 373759 | yes |
| loop.png | 2f03aa99c064921ddd33996b36695b1fd9a6399666962a077cbb9da40f9d1dfa | same | 379406 vs 379406 | yes |
| demo.mp4 | 9ab8dfa672ec6c481c2c5eabde8681c4ac479f2ff45abb515c66b4a1cf10ce72 | same | 772596 vs 772596 | yes |

PNG/MP4 are byte-identical, so the underlying data files match by
construction; verified anyway: regenerated `data/convergence.json` is
byte-identical to the committed one, the .frd solves reproduced the
verdict element counts (11250 / 60000), and the regenerated
`MANIFEST.json` is byte-identical to the committed one. `git status`
after the rebuild: clean — no tracked file changed.

## 7. README steps that were unclear, wrong or missing

1. **"Already installed" is false in a fresh sandbox.** "Ask your agent"
   opens with "In this sandbox, `judge/setup.sh` has already installed
   CalculiX `ccx` and gmsh under `~/tools/bin`." Here `~/tools` did
   not exist; the README never states the explicit first step of
   running `judge/setup.sh` manually — it is only implied by the
   `run.py` description ("It creates a sandbox, … runs
   `judge/setup.sh`, …"). A literal reproducer must infer it.
2. **No manual fallback for the sbx-only one-command run.** `run.py`
   needs the `sbx` CLI (`pip install "git+https://github.com/
   agent-next/sandbox#subdirectory=cli"`) and `SBX_API_KEY`; neither
   exists in this sandbox. The manual equivalent (setup.sh →
   selftest.sh → grade.sh) is never spelled out as such.
3. **Media provenance undocumented in README.** README links
   `media/result.png`, `media/loop.png`, `media/demo.mp4` but never
   mentions `media/make_media.sh` or `media/MANIFEST.json` (the
   "regenerate" pointer lives only inside MANIFEST.json itself).
4. **Environment quirk (not a README error):** `/tmp/opencode` is
   root-owned and not writable by the reproducer user; first
   determinism attempt failed with `mkdir: cannot create directory
   '/tmp/opencode/repro': Permission denied` and `grade.sh` exit 1
   (could not write the `--json` path). Rerun in `~/repro-scratch`
   succeeded. Also `sudo: unable to resolve host instance` warnings
   during apt are harmless (RECEIPT notes the same).

## 8. Deviations

- None in the judged path: setup, selftest, grade, determinism and
  media rebuild all ran as documented and every README/RECEIPT number
  reproduced exactly (see §4). The single mismatch (RECEIPT's
  overload-10x gate line) is a stale line in the RECEIPT prose,
  contradicted by the repo's own committed verdict JSON, which this
  run matches.
- Wall times are same-ballpark as RECEIPT's two fresh-setup runs
  (setup 12.4 s vs 10/16 s; selftest 298.6 s vs 311/300 s; grade
  32.7 s vs 34/34 s).
