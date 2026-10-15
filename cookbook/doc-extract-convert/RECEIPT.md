# RECEIPT — doc-extract-convert

Real command output.  Nothing below is invented; every block is pasted from
the command it names.  Two *fresh* one-command runs
(`python3 cookbook/doc-extract-convert/run.py --ref
sbx/demo-doc-extract-convert-f5`, each in its own brand-new sandbox created
by that same command) are recorded side by side in §4.

## 1. `bash judge/setup.sh` (cold, inside run.py's first sandbox)

```
[setup] fonts-dejavu-core already installed
[setup] refreshing apt lists
[setup] all tools present; versions recorded to judge/VERSIONS.txt
tesseract-ocr 5.3.0-2
tesseract-ocr-eng 1:4.1.0-2
fonts-dejavu-core 2.37-6
python3 Python 3.12.15
Pillow 11.3.0
```

**exit 0**, wall **34.5 s** (run 1) / **32.2 s** (run 2).  Every `.deb` is
sha256-checked against `judge/package-sha256.txt` and the Pillow wheel
against `judge/requirements.txt` before anything is installed.  All 16
Pillow digests and the three named Debian packages were re-verified against
PyPI's published set and the bookworm archive respectively during this
build (16/16 and 3/3 match; the remaining eleven dependency pins are
checked by setup.sh itself whenever apt downloads them).

## 2. `bash judge/selftest.sh` (inside run.py's sandbox)

```
[selftest] grading known-good artifact
[selftest] known-good: all gates passed
[selftest] grading mutant m01-total-as-float
[selftest] killed m01-total-as-float (failed: G1,G3)
[selftest] grading mutant m03-box-on-whitespace
[selftest] killed m03-box-on-whitespace (failed: G2)
[selftest] grading mutant m03b-whole-page-box
[selftest] killed m03b-whole-page-box (failed: G0,G2)
[selftest] grading mutant m04-quarantine-everything
[selftest] killed m04-quarantine-everything (failed: G1,G3,G4)
[selftest] grading mutant m05-wrong-date-format
[selftest] killed m05-wrong-date-format (failed: G0,G1)
[selftest] grading mutant m06-accept-bad-date
[selftest] killed m06-accept-bad-date (failed: G0,G1)
[selftest] judge-guard: weakened ink check fails the good artifact (as it must)
[selftest] determinism: two runs at seed 42 identical (apart from timing)
[selftest] kill rate: 6/6 mutants killed (100%)
[selftest] OK
```

**exit 0**, wall **450.9 s** (run 1) / **352.3 s** (run 2) — the spread is
the 2 vCPU sandbox being busy, not a different result.  Kill rate
**6/6 = 100 %** (rule ≥ 90 %, ≥ 5 mutants), plus the judge-guard mutant
and the determinism check.

## 3. `bash judge/grade.sh examples/good --json /tmp/v.json --seed 42`

Run 1 (run 2 differs only in `timing`, as the determinism gate requires):

```json
{
  "all_gates_passed": true,
  "artifact": "/tmp/docgrade.GNsJT5/artifact",
  "gates": [
    {"gate": "G0", "passed": true,
     "detail": "11 record(s) + 1 quarantined, all well formed",
     "violations": []},
    {"gate": "G1", "passed": true,
     "detail": "field accuracy 1.000 (48/48, min 0.95)",
     "accuracy": 1.0, "correct": 48, "slots": 48, "examples": []},
    {"gate": "G2", "passed": true,
     "detail": "every claimed box sits on ink", "violations": []},
    {"gate": "G3", "passed": true,
     "detail": "11/11 totals exact to 0 ulp", "exact": 11, "totals": 11},
    {"gate": "G4", "passed": true,
     "detail": "2/2 corrupted pages quarantined, no invented values, 12/12 pages accounted",
     "violations": []}
  ],
  "seed": 42,
  "timing": {"corrupt_corpus": 0.51, "extract_clean": 23.77,
             "extract_corrupt": 19.56, "generate_corpus": 3.27}
}
```

**exit 0**, wall **51.9 s** (run 1) / **56.1 s** (run 2).  Run 2's timing:
`corrupt_corpus 0.52, extract_clean 23.73, extract_corrupt 21.67,
generate_corpus 3.45` — same verdict, same numbers, only wall times moved.

Key numbers: field accuracy **48/48**, totals exact **11/11**, grounding
failures **0**, negative control **2/2 quarantined + 12/12 accounted**,
selftest kill rate **6/6**.

## 4. Two fresh one-command runs

`python3 cookbook/doc-extract-convert/run.py --ref
sbx/demo-doc-extract-convert-f5` at commit `4a88886`, launched from outside
any sandbox, each creating its own sandbox and killing it at the end:

| step | run 1 (sandbox `01a14071-571b…`) | run 2 (sandbox `01a1407c-9efd…`) |
|---|---|---|
| `sbx create --timeout-min 30` | exit 0, 4.6 s | exit 0, 3.0 s |
| `git clone --depth 1 -b <ref>` | exit 0, 7.6 s | exit 0, 5.9 s |
| `judge/setup.sh` | exit 0, 34.5 s | exit 0, 32.2 s |
| `judge/selftest.sh` | exit 0, 450.9 s | exit 0, 352.3 s |
| `grade.sh examples/good` | exit 0, 51.9 s | exit 0, 56.1 s |
| verdict | `all_gates_passed: true` | `all_gates_passed: true` |
| field accuracy | 48/48 = 1.000 | 48/48 = 1.000 |
| exact totals | 11/11 | 11/11 |
| `sbx kill` + `sbx list` | confirmed gone | confirmed gone |
| **run.py exit code** | **0** | **0** |

Tail of run 1 (run 2's tail is identical apart from the ids and timings):

```
[run] PASS
[run] sbx kill                        2.7s  exit=0
killed 01a14071-571b-7551-9c93-1d5c98df6845
[run] sbx list                        1.0s  exit=0
[run] confirmed: 01a14071-571b-7551-9c93-1d5c98df6845 is gone
```

`run.py`'s failure paths were checked separately with a stub `sbx` CLI:
a grade that crashes (no verdict JSON), a grade that exits non-zero with
no JSON, and a verdict with `all_gates_passed: false` each make the whole
run exit **1**; only a clean rc *and* `all_gates_passed: true` exits 0.

## 5. Cold-start `grade.sh`

The first `grade.sh` call in a fresh clone was verified in its own sandbox:
with `judge/__pycache__` absent, `bash judge/grade.sh examples/good --json
/tmp/vclean.json --seed 42` exits **0** (it used to exit 2 with "judge/
changed during grading" — the interpreter's own `.pyc` files were tripping
the tamper check; they are now excluded and the judge runs with
`PYTHONDONTWRITEBYTECODE=1`).

## Deviations

- **`REPRODUCE.md` (independent reproduction) is not recorded.**  It needs
  an agent from a different model family following README.md alone; an
  agent reproducing its own work is not an independent check, so its table
  stays empty until that run happens.  The protocol, tolerances and
  expected numbers are all in place.
- `sudo` in the build/acceptance sandboxes prints a cosmetic `unable to
  resolve host instance` warning (no hostname in /etc/hosts).  It does not
  affect any exit code.
- The `media/` figures and video were regenerated in a separate fresh
  sandbox (same setup, same seed 42) by `bash media/make_media.sh`; the
  verdict JSONs they were drawn from are listed in
  `media/MANIFEST.json`.
