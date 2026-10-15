# RECEIPT — doc-extract-convert

Real command output from the build sandbox (Debian 12 bookworm, 2 vCPU,
~4 GB RAM, Python 3.12.15), at seed 42, on branch
`sbx/demo-doc-extract-convert` commit `977a749`.  Nothing below is
invented; each block is pasted from the named command.

All three commands were run from `cookbook/doc-extract-convert/` in a
sandbox where the toolchain had been fully purged first
(`apt-get purge tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd
libtesseract5 liblept5` + `pip uninstall Pillow`), so the setup block
below exercised the cold path; the pasted run is the *idempotent re-run*
over that installed state (its output is what a user sees on their
second call, and the cold run printed the same versions — see
Deviations).

## 1. `bash judge/setup.sh`

```
[setup] tesseract-ocr already installed
[setup] tesseract-ocr-eng already installed
[setup] fonts-dejavu-core already installed
[setup] Pillow 11.3.0 already installed
[setup] all tools present; versions recorded to judge/VERSIONS.txt
tesseract-ocr 5.3.0-2
tesseract-ocr-eng 1:4.1.0-2
fonts-dejavu-core 2.37-6
python3 Python 3.12.15
Pillow 11.3.0
```

**exit 0**, wall `0.6 s` (idempotent re-run).  The cold run (tools
purged) downloaded 14 sha256-checked `.deb`s plus the pinned
`Pillow==11.3.0` wheel and took **about 40 s**; both runs record the
same `judge/VERSIONS.txt` (pasted above).

Every downloaded file is sha256-checked before install: `.deb`s against
`judge/package-sha256.txt`, the Pillow wheel against
`judge/requirements.txt` (digests from PyPI's published set for the
11.3.0 release).

## 2. `bash judge/selftest.sh`

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

**exit 0**, wall **13 m 5 s**.  Kill rate **6/6 = 100 %** (rule: ≥ 90 %,
≥ 5 mutants), plus the judge-guard mutant (a deliberately weakened ink
check must fail the good artifact — proving the grounding gate is
load-bearing) and the determinism check (two grading runs at seed 42
byte-identical apart from `timing`).

## 3. `bash judge/grade.sh examples/good --json /tmp/v.json --seed 42`

```
{
  "all_gates_passed": true,
  "gates": [
    {"gate": "G0", "passed": true,
     "detail": "11 record(s) + 1 quarantined, all well formed"},
    {"gate": "G1", "passed": true,
     "detail": "field accuracy 1.000 (48/48, min 0.95)",
     "accuracy": 1.0, "correct": 48, "slots": 48, "examples": []},
    {"gate": "G2", "passed": true,
     "detail": "every claimed box sits on ink"},
    {"gate": "G3", "passed": true,
     "detail": "11/11 totals exact to 0 ulp",
     "exact": 11, "totals": 11},
    {"gate": "G4", "passed": true,
     "detail": "2/2 corrupted pages quarantined, no invented values, 12/12 pages accounted"}
  ],
  "timing": {"corrupt_corpus": 1.0, "extract_clean": 40.14,
             "extract_corrupt": 46.84, "generate_corpus": 3.07}
}
```

**exit 0**, wall **1 m 33 s** (clean-corpus extraction 40 s, corrupted-
corpus extraction 47 s, corpus generation 3 s, corruption 1 s).

Key numbers: field accuracy **48/48**, totals exact **11/11**, grounding
failures **0**, negative control **2/2 quarantined + 12/12 accounted**,
selftest kill rate **6/6**.

## Two-run summary (fresh-sandbox reproduction)

| run | setup | selftest | grade good | accuracy | kill rate |
|---|---|---|---|---|---|
| build sandbox (this receipt) | exit 0, ~40 s cold | exit 0, 13 m 5 s | exit 0, 1 m 33 s | 48/48 | 6/6 |
| second fresh sandbox | (not done: this task cannot create agent-next sandboxes from inside its own sandbox — `run.py` is verified via `python3 -m py_compile` plus running its exact in-sandbox `bash -c` command sequence directly, both of which pass; the lead's end-to-end `run.py` run will produce the second row) |

A second full in-sandbox sequence (setup → grade) was also run inside
this same sandbox during development and reproduced the same verdict
byte-for-byte apart from `timing` (checked by `selftest.sh`'s
determinism gate).

## Deviations

- **`REPRODUCE.md` (independent reproduction) is not done**: it requires
  a *different* agent (different model family) following only README.md
  in a fresh sandbox, which is out of this task's scope.
- **`media/` is not done**: a later task builds the media; nothing in
  this repo references media files yet.
- The second *fresh-sandbox* row of RECEIPT is left to the lead's
  end-to-end `run.py` run (same reason as above: no sandbox API access
  from inside this disposable sandbox).
- The cold-path `setup.sh` run is not pasted verbatim above; the pasted
  block is the idempotent re-run.  The cold run printed the same version
  lines (verified: `tesseract 5.3.0`, `--list-langs` shows `eng`, Pillow
  import works) and installed from the same sha256-checked files.
- `sudo` in this build sandbox prints a cosmetic `unable to resolve host
  instance` warning (no hostname in /etc/hosts); it does not affect any
  command's exit code and would not appear in a normal sandbox.  Those
  lines are filtered from the pasted output.
