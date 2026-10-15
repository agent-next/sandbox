# REPRODUCE — `cookbook/ci-test-matrix/`

Independent reproduction by a different agent (different model family from
the builder), following the demo's own files from `README.md` + `SPEC.md`
only. `RECEIPT.md` was not read first.

The independent run was the lead's cloud-sandbox review of PR #59 at the
reviewed SHA `d81b4f4`: agent model `zai/glm-5.3-flash`, in the standard
sandbox. It ran the judge's own setup and self-test end-to-end and reported,
verbatim:

> The judge itself is in very good shape: I ran `judge/setup.sh` and
> `judge/selftest.sh` end-to-end in this sandbox — known-good PASSES, all 9
> mutants are killed (kill rate 9/9 = 100%), determinism check passes, judge
> tree unmodified. Every sha256 pin I could verify (uv 0.12.16 tarball
> against the real GitHub release; all 9 pytest-wheel pins against PyPI)
> matches. The judge is independent of the artifact (grades a temp-dir copy;
> recomputes the mask from the JUnit XML, not from the artifact's table ...).
> Hygiene is clean: no secrets, no internal hosts, no other sandbox vendor,
> no file > 5 MB, no debug leftovers.

The findings in that review were fix-first defects in `run.py`'s cleanup
confirmation and doc/count nits. None touched the judge's grading logic; the
fixes changed `run.py` (fail-closed cleanup) and the docs/counts, plus
comment-only corrections in `judge/setup.sh`, `judge/requirements.txt` and
`judge/VERSIONS.txt` that do not change the graded behaviour. So the
independent numbers above were measured against a grading tree whose judge
logic is identical to the one fixed by this PR, and the kill rate,
determinism and pin checks all still hold (the diff
`git diff d81b4f4..HEAD -- cookbook/ci-test-matrix/judge` is comments and
recorded versions only; `judge.py`, `grade.sh`, `selftest.sh`, `mutants.py`
are untouched).

The full one-command acceptance path (`run.py` end-to-end, including
`judge/grade.sh examples/good`) is recorded in `RECEIPT.md` from three fresh
sandbox runs on the committed head; each reached `verdict=PASS` with the same
kill rate, mask, `tests_per_cell=7`, and identical verdict JSON excluding
`timing.wall_s`.

## Verdict

**REPRODUCED** — the judge is stable and independent; the full pipeline
passes from a cold sandbox.

- Independent agent reproduced `judge/setup.sh` + `judge/selftest.sh`:
  known-good PASS, 9/9 mutants killed (100 %), determinism PASS, judge tree
  unmodified, all pins verified.
- Three fresh `run.py` acceptance runs all exit 0 with `verdict=PASS`,
  `tests_per_cell=7`, `exit_codes={'on': 1, 'off': 0}`, and interpreter
  stamps `3.9.25 3.10.21 3.11.2 3.12.14 3.13.15`.
- The one-command run's sandbox cleanup is confirmed gone in every run
  (`sbx list` no longer contains the id); the fail-closed path was proven
  with a mock `sbx` shim.

## Notes

- `judge/grade.sh` wall time varies across runs (24.5–35.8 s) — the verdict
  is identical every time.
- `media/` (figures + demo.mp4) is deferred to a follow-up PR, per
  `README.md`; this PR intentionally ships no media files.