# sim-tuner receipt, 2026-10-15

Grading source: `602f4d60`, after merging `origin/main`.
The inherited branch was reviewed as a whole, not just the closeout patch.
`media/data/provenance.json` records the exact grading-source hashes.
Documentation and media are committed separately from that tested source.

## Two fresh API runs

Commands, from the repository root with an existing API key exported:

```bash
env -u HTTPS_PROXY -u https_proxy -u HTTP_PROXY -u http_proxy \
  python3 cookbook/sim-tuner/run.py --seed 7 \
  --report-json cookbook/sim-tuner/media/data/run-1.json
env -u HTTPS_PROXY -u https_proxy -u HTTP_PROXY -u http_proxy \
  python3 cookbook/sim-tuner/run.py --seed 7 \
  --report-json cookbook/sim-tuner/media/data/run-2.json
```

| result | fresh run 1 | fresh run 2 |
|---|---:|---:|
| runner exit | 0 | 0 |
| stack-check exit / seconds | 0 / 0.2 | 0 / 0.3 |
| selftest exit / seconds | 0 / 67.9 | 0 / 71.4 |
| grade exit / seconds | 0 / 5.6 | 0 / 5.7 |
| lease creation, seconds | 4.1 | 3.0 |
| lease job, seconds, including transport | 83 | 86 |
| full runner, seconds | 90 | 90 |
| G1 / G2 / G3 / G4 | PASS / PASS / PASS / PASS | PASS / PASS / PASS / PASS |
| CPU train error | 0.016299 | 0.016299 |
| held-out / default error | 0.022060 / 0.118495 | 0.022060 / 0.118495 |
| fraction of default | 0.1862 | 0.1862 |
| GPU train error | 0.016322 | 0.016322 |
| GPU absolute / relative difference | 0.000023 / 0.001441 | 0.000023 / 0.001441 |
| selftest | 18/18 = 100% | 18/18 = 100% |
| CPU determinism | OK | OK |
| judge unchanged | yes | yes |
| DELETE followed by GET 404 | confirmed | confirmed |

Actual runner output, run 1 (the complete grade and stage results are in
`media/data/run-1.json`):

```text
created gl-e0bca3-7 in 4.1 s
lease job done in 83 s
  [stack-check] rc=0 (0.2 s)
  [selftest] rc=0 (67.9 s)
  [grade] rc=0 (5.6 s)
selftest: known-good: PASS (G1-G4)
selftest: kill rate: 18/18 = 100%
selftest: determinism: OK
selftest: ok (18/18 mutants killed, seed 7)
sim-tuner demo: PASS (seed 7)
  gate G1_ranges: pass
  gate G2_train: pass
  gate G3_heldout: pass  heldout_err 0.02206 (< 0.025; frac of default 0.1862 < 0.3)
  gate G4_gpu_cpu_agree: pass  gpu 0.016322 vs cpu 0.016299 (abs 2.3e-05, rel 0.001441)
destroyed gl-e0bca3-7; verified GET 404
total: 90 s
run.py rc=0
```

Actual runner output, run 2:

```text
created gl-e0bca3-8 in 3.0 s
lease job done in 86 s
  [stack-check] rc=0 (0.3 s)
  [selftest] rc=0 (71.4 s)
  [grade] rc=0 (5.7 s)
selftest: known-good: PASS (G1-G4)
selftest: kill rate: 18/18 = 100%
selftest: determinism: OK
selftest: ok (18/18 mutants killed, seed 7)
sim-tuner demo: PASS (seed 7)
  gate G1_ranges: pass
  gate G2_train: pass
  gate G3_heldout: pass  heldout_err 0.02206 (< 0.025; frac of default 0.1862 < 0.3)
  gate G4_gpu_cpu_agree: pass  gpu 0.016322 vs cpu 0.016299 (abs 2.3e-05, rel 0.001441)
destroyed gl-e0bca3-8; verified GET 404
total: 90 s
run.py rc=0
```

Earlier closeout checks also destroyed their leases and confirmed GET 404:
`gl-e0bca3-4`, `gl-e0bca3-5`. No unrelated sandbox was touched.

## Versions and measured search

The fresh lease reports Python 3.13.5, MuJoCo 3.8.1, NumPy 1.26.4,
mujoco-warp 3.8.1 and warp-lang 1.13.0, on an RTX 5090 VRAM slice.
The host-side CPU replay uses Python 3.12.3, MuJoCo 3.8.1 and NumPy 1.26.4;
Pillow 11.3.0 produces the figures. Every local CPU gate equals the fresh
lease gate exactly.

The shipped search history is **CPU**, 732.3 s, followed by pattern-search
refinement. This closeout did not rerun that search. The one-command run
grades the shipped fit, not a fresh optimization. G4 performs real GPU
evaluation; no GPU-search speedup is claimed.

## Regression evidence

Tests cover runner output, grade timing, selftest-only skipping, strict
artifact parsing, duplicate keys, stack versions, lease ownership on
exceptions, CPU-only incomplete verdicts, selftest infrastructure failures
and survivors, deterministic scenario serialization, and Python 3.13 setup.
Fixtures generate fake grade processes in temporary directories; infrastructure
failure is never accepted as evidence that a mutant was killed.

The new judge/setup tests were run against isolated sources at `236686f5`.
Six **assertion failures** demonstrated the old behavior: setup idempotence,
duplicate JSON keys, both missing Warp-version fields, CPU-only false PASS,
and the internally owned lease leak. Runner regressions likewise failed
before the runner fixes. No import failure or skipped test counted as power
evidence.

## Independent execution-based code review

GLM-5.3 reviewed `origin/main..602f4d60`, ran the tests and parser probes,
and returned the following. The primary separately executed the demo tests
and both real fresh-lease runs.

```text
findings: []

checked_does_not_hold:
- `GpuLease` created inside `grade()` leaks on a raised gate: `test_judge.py::LeaseOwnership` exercises the `BaseException` cleanup path and confirms close (see `judge/_grade.py:373-380`).
- Mutant surviving a CPU gate, or an infra exit counted as a kill: all 18 scripted mutants grade `rc=1` with a failing G1/G2/G3 gate; `selftest.sh` rejects rc≠1 and empty verdicts (verified clones in `tests/test_judge.py::SelftestHarness`).
- Strict artifact parser accepting booleans, non-finite, Infinity, duplicate keys, lists/dicts, null, oversize, out-of-range, missing/extra keys: `load_artifact` rejects each (`judge/_grade.py:108+`, asserted in `tests/test_judge.py::DuplicateKeys` and local probe).
- Version-table drift silently passing: `check_version_table` names each mismatched/missing field including `mujoco_warp`, `warp`, os release, mujoco older cv (`judge/engine.py` `check_version_table`, asserted in `VersionTable` tests).
- CPU-only grade being reported as a full PASS: `overall(..., complete=False)` returns INCOMPLETE, and `grade(gpu=False)` sets `pass=False` (asserted in `OverallContract`/`CpuOnlyGrade`).
- Rendered lease job containing unbound names / stage-skipping: `tools/test_rendered_job.py` compiles and executes it end to end with stubs (3 tests passed).

VERDICT: SHIP
```

Correction to that raw review: `test_rendered_job.py` is a standalone
script, not a collected pytest test. The three pytest cases are in
`tools/test_run.py`. The primary reran the script directly and obtained:

```text
ok: rendered job compiles, has no unbound names, and ran end to end
```

### Final Opus execution-based review

Opus 5.5 reviewed the full branch through `6aedff29`, not only the last
patch. Its actual conclusion:

> **VERDICT: SHIP-CODE.** I found no blocking bugs in
> `origin/main..6aedff2`. All 12 findings below are low severity. This
> verdict covers the code only; it is not media acceptance or merge approval.

It independently ran **34 tests in 15.10 s**, all eighteen actual CPU
mutants (13 G3 failures and 5 G1 failures), two identical-except-timing
CPU-only grades, the standalone rendered-job check, schema/hash checks and
generated no-network probes. Its non-findings include strict artifact
parsing, infrastructure failures never counting as kills, exception-path
lease ownership, GPU world layout, exact provenance and truthful media status.
It removed its own generated fixtures.

Nonblocking findings are retained, not silently treated as fixes:

- The runner's self-test still uses seed 7 even with another grade seed.
  Only seed 7 has a shipped passing fit; a different rig needs refitting.
- Standalone `GpuLease.close()` accepts a reported `dead` phase; the
  one-command runner instead requires GET 404. A lost create response
  cannot recover an unknown lease id. No blind deletion of unrelated
  leases was attempted to work around that API limitation.
- Standalone rendering trusts its captured array. Exact-state checks
  validate the supplied qpos/qvel, not their origin. The delivered pipeline
  captures immediately before rendering and checks CPU gates against the
  lease, but the ignored array is not cryptographically bound in the manifest.
- The hero's “Oracle” label denotes noiseless truth; the binding acceptance
  oracle remains the noisy recordings specified in SPEC. The historical
  CPU search retains a misleading `best_train_err_gpu` key; its actual
  `engine: cpu` and measured CPU provenance are stated explicitly.
- Low-priority cleanup includes duplicate payload text in a GPU-template
  comment, a redundant CPU evaluation, an ineffective search `sys.path`
  entry and a stale search-docstring calibration link. Verdicts identify
  the temporary basename rather than an artifact hash. The storyboard
  caption and this receipt's pytest attribution were corrected.

No grading/search refactor was made after this gate. Shared request code
stays duplicated so that `run.py` remains stdlib-only; there is no new
compatibility layer. The quality lenses were covered in this single review,
not represented as the unrun three-agent simplify panel.

## Verification

- Demo tests and physics/media contracts: **34 passed in 10.20 s** locally.
- CLI CI equivalents, isolated installed package: **310 passed** on Python
  3.10.21; **310 passed** on Python 3.13.15.
- Shared video-gate suite: **20 passed in 361.62 s**. The committed-video
  baseline after the final media encode: **1 passed in 232.48 s**. Its first
  attempt hit a 120 s harness timeout; rerunning with a sufficient deadline
  passed.
- Result-card schema, JSON/plugin manifests, source hashes, media hashes and
  public-hygiene checks are checked before delivery.
- Native full-frame-rate two-family vision playback: not available in this
  harness. Blind sampled-frame reviews are explicitly identified as such
  in `media/REVIEW.json`, not passed off as native playback. Final scores
  (craft/wow/clarity) are Opus 5.5 **6/4/6**, Gemini 3.1 Pro **7/7/9**.
  **Neither passes the complete panel bar. This PR remains draft.**
- Independent README-only reproduction: **not run**, reserved for another
  agent. No `REPRODUCE.md` was created.
- No PR merge, release or deployment was attempted.

Final base integration: merged `origin/main` at `ecfbcfa1` in `69115e5b`.
Its only new files are the unrelated `ci-test-matrix` demo. An exact diff
confirmed no changes to the reviewed sim-tuner source, CLI, workflows,
plugin manifests or shared cookbook tools. The CLI matrix and video checks
therefore exercise the same files as this integrated tree.
The two GPU verdicts differ in measured GPU timings, as expected; the CPU
gate objects and all accepted GPU/CPU error numbers match exactly.

## Deviations and limits

1. GPU leases have a pinned preinstalled stack and no outbound network.
   The runner uses the GPU API, uploads this source checkout, and validates
   the image instead of cloning and pip-installing within it. This is not a
   cold package-install timing.
2. The public deterministic generator is not secure hidden data. “Truth” is
   withheld from the search by convention. The biased-fit mutant is an
   intentional bias, not evidence of an optimizer overfitting noise.
3. CPU-only grading is incomplete, not a demo PASS, even when its partial
   checks exit 0. Require JSON `pass: true` for full acceptance. CPU and GPU implement
   the same MuJoCo equations, not independent physical reality.
4. The video replays real graded states, at labelled real time, with a
   translucent same-timestep truth ghost. Its opening includes the PASS
   threshold. Camera motion contributes to the motion metric. There is no
   fabricated sped-up agent screen recording; the real CPU search history
   and per-mutant matrix are in `loop.png` instead.
5. Semantic simplification after the independent code gate was skipped to
   preserve its verified behavior. The full three-reviewer simplify fan-out
   was not run; code review and targeted tests are reported separately.
