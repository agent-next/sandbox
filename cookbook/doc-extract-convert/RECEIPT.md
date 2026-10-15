# RECEIPT — doc-extract-convert

Real command output.  Nothing below is invented; every block is pasted from
the command it names.  Two *fresh* one-command runs
(`python3 cookbook/doc-extract-convert/run.py --ref
sbx/demo-doc-extract-convert-f5`, launched from outside any sandbox, each
creating its own sandbox and killing it at the end) are recorded side by
side in §4.  They graded `a938680` and `820bb36`; the only difference
between those two commits is README prose (the media-regeneration section),
so both runs exercised identical judge, artifact and corpus bytes.

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

**exit 0**, wall **16.5 s** (run 1) / **19.4 s** (run 2) — faster than the
34.5 s measured in an earlier pass because these sandboxes' apt lists were
already warm.  Every `.deb` is
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

**exit 0**, wall **256.4 s** (run 1) / **250.5 s** (run 2) — the spread is
the 2 vCPU sandbox being busy, not a different result.  Kill rate
**6/6 = 100 %** (rule ≥ 90 %, ≥ 5 mutants), plus the judge-guard mutant
and the determinism check.

## 3. `bash judge/grade.sh examples/good --json /tmp/v.json --seed 42`

Run 1 (run 2 differs only in `timing`, as the determinism gate requires):

```json
{
  "all_gates_passed": true,
  "artifact": "/tmp/docgrade.EA4e0J/artifact",
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
  "timing": {"corrupt_corpus": 0.44, "extract_clean": 12.75,
             "extract_corrupt": 12.76, "generate_corpus": 1.94}
}
```

**exit 0**, wall **30.8 s** (run 1) / **29.6 s** (run 2).  Run 2's verdict
is identical except for the timing block — same verdict, same numbers, only
wall times moved, which is what the determinism gate requires.

Key numbers: field accuracy **48/48**, totals exact **11/11**, grounding
failures **0**, negative control **2/2 quarantined + 12/12 accounted**,
selftest kill rate **6/6**.

## 4. Two fresh one-command runs

`python3 cookbook/doc-extract-convert/run.py --ref
sbx/demo-doc-extract-convert-f5`, launched from outside any sandbox:

| step | run 1 | run 2 |
|---|---|---|
| sandbox id | `01a14091-18f6-7cf0-b410-873396f5dd25` | `01a14092-2838-7a50-8eb4-d07a28538daa` |
| commit graded | `a9386809ed60af81c4ea06805aaf42ec0d1f2308` | `820bb36d6b5e55c8222d521f69a0f88f04813d5e` |
| `sbx create --timeout-min 30` | exit 0, 2.1 s | exit 0, 2.4 s |
| `git clone --depth 1 -b <ref>` | exit 0, 4.1 s | exit 0, 5.2 s |
| `judge/setup.sh` | exit 0, 16.5 s | exit 0, 19.4 s |
| `judge/selftest.sh` | exit 0, 256.4 s | exit 0, 250.5 s |
| selftest kill rate | 6/6 = 100 % | 6/6 = 100 % |
| judge-guard mutant | killed | killed |
| determinism (two runs, seed 42) | identical apart from `timing` | identical apart from `timing` |
| `grade.sh examples/good` | exit 0, 30.8 s | exit 0, 29.6 s |
| verdict | `all_gates_passed: true` | `all_gates_passed: true` |
| field accuracy | 48/48 = 1.000 | 48/48 = 1.000 |
| exact totals | 11/11 | 11/11 |
| `sbx kill` + `sbx list` | confirmed gone | confirmed gone |
| **run.py exit code** | **0** | **0** |

Run 1 in full (run 2's output is the same apart from ids, the commit and
wall times):

```
[run] sbx create --timeout-min 30     2.1s  exit=0
[run] sandbox id: 01a14091-18f6-7cf0-b410-873396f5dd25
Cloning into 'repo'...
[run] git clone --depth 1 -b sbx/demo-doc-extract-convert-f5    4.1s  exit=0
[run] git rev-parse HEAD              1.7s  exit=0
[run] commit: a9386809ed60af81c4ea06805aaf42ec0d1f2308
[setup] all tools present; versions recorded to judge/VERSIONS.txt
[run] judge/setup.sh                 16.5s  exit=0
[run] judge/selftest.sh             256.4s  exit=0
[selftest] judge-guard: weakened ink check fails the good artifact (as it must)
[selftest] determinism: two runs at seed 42 identical (apart from timing)
[selftest] kill rate: 6/6 mutants killed (100%)
[selftest] OK
[run] grade examples/good            30.8s  exit=0
[run] ======== verdict ========
{
  "all_gates_passed": true,
  ...
  "seed": 42,
  "timing": {
    "corrupt_corpus": 0.44,
    "extract_clean": 12.75,
    "extract_corrupt": 12.76,
    "generate_corpus": 1.94
  }
}
[run] PASS
[run] sbx kill                        2.1s  exit=0
killed 01a14091-18f6-7cf0-b410-873396f5dd25
[run] sbx list                        0.6s  exit=0
[run] confirmed: 01a14091-18f6-7cf0-b410-873396f5dd25 is gone
EXIT=0
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
  sandbox at commit `a938680` by a full `bash media/make_media.sh`
  (setup + seven grading runs + render + encode, seed 42); the result is
  **byte-identical** to the files committed here (sha256 of `result.png`,
  `loop.png`, `demo.mp4` and `MANIFEST.json` all match).  The verdict
  JSONs they were drawn from are listed in `media/MANIFEST.json`.
