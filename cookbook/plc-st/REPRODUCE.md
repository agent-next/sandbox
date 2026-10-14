VERDICT: REPRODUCED

# plc-st — independent reproduction (README + SPEC only, then RECEIPT)

Reproduced from `README.md` / `SPEC.md` alone on a fresh sandbox, then compared with
`RECEIPT.md`. No builder numbers were reused: every figure below came out of my own
runs, and I only opened `RECEIPT.md` after the numbers were on disk (in a scratch
directory outside the repo, since deleted).

- repo tree: `agent-next/sandbox` @ `a25347bc8503ab6049fe575e0d7a542ffba2a46f`
  (branch `sbx/demo-plc-st-repro2`, clean working tree)
- machine: 2 vCPU, ~3.9 GB RAM, Debian bookworm, `/usr/local/bin/python3` = 3.12.15
- `SBX_API_KEY`/`E2B_API_KEY`: unset. `sbx` CLI: not installed.
  So the README's one-command path (`run.py`) could not run; I ran the exact
  in-sandbox sequence locally instead, against this working tree.
- seeds used (the ones the judge/RECEIPT use): grade default
  **20261014** (`judge/grade.sh:24`, `judge/grade.py:280`), **999999**
  (`judge/selftest.sh:61` determinism step), **12345** (RECEIPT hardening §2).

---

## 1. Steps, with real output

### 1.1 `python3 cookbook/plc-st/run.py` — FAILED (no credentials), continued

```text
$ time python3 cookbook/plc-st/run.py
/home/user/w/cookbook/plc-st/run.py:85: SyntaxWarning: invalid escape sequence '\$'
  try:
plc-st: export SBX_API_KEY (or E2B_API_KEY) first; get one at https://sbx.agent-next.com/console
wall: 0.08 s   exit: 1
```

Nothing else ran (no sandbox was created, so nothing to kill). I fell back to the
pipeline `run.py` runs *inside* the sandbox: `judge/setup.sh` → `judge/selftest.sh` →
`judge/grade.sh examples/good/tank_ctrl.st`.

### 1.2 `bash judge/setup.sh` — exit 0

First fresh run on this sandbox (bison/flex were *not* preinstalled):

```text
$ bash judge/setup.sh
[setup] installing Debian build deps (bison flex autoconf automake libtool ...)
sudo: unable to resolve host instance: Name or service not known
sudo: unable to resolve host instance: Name or service not known
debconf: delaying package configuration, since apt-utils is not installed
Selecting previously unselected package flex.
...
[setup] downloading MATIEC 75d6e82cce5bc8b98ce03a417b106884cbb7ebb5
[setup] building iec2c from source (gcc/bison/flex)
[setup] installed /home/user/.plc-st/bin/iec2c
[setup] done.
  iec2c   -> /home/user/.plc-st/bin/iec2c
  lib     -> /home/user/.plc-st/lib
matiec version 0.1
changeset id:
wall: 44.14 s   exit: 0
```

The sha256 pin is real — I verified the tarball independently:

```text
$ curl -fsSL -o matiec.tar.gz https://github.com/thiagoralves/matiec/archive/75d6e82...tar.gz
$ sha256sum matiec.tar.gz
a679c8e69459c2e4a05850438e073866eeb695b598ff244029dac0ea5d8e9a08  matiec.tar.gz
a679c8e69459c2e4a05850438e073866eeb695b598ff244029dac0ea5d8e9a08  expected   # MATCH
```

Second fresh run (wiped `~/.plc-st`, the one my own run created, then re-ran, as the
RECEIPT's hardening §3 claims):

```text
$ rm -rf ~/.plc-st && bash judge/setup.sh      # bison/flex now already present
[setup] downloading MATIEC 75d6e82cce5bc8b98ce03a417b106884cbb7ebb5
[setup] building iec2c from source (gcc/bison/flex)
[setup] installed /home/user/.plc-st/bin/iec2c
[setup] done.
matiec version 0.1
changeset id:
wall: 39.85 s   exit: 0
```

Idempotent re-run: `wall: 0.05 s  exit: 0` ("[setup] iec2c already installed").

### 1.3 `bash judge/selftest.sh` — exit 0

```text
$ bash judge/selftest.sh
selftest: known-good PASS
selftest: mutant KILLED: estop_not_safe
selftest: mutant KILLED: inverted_dryrun
selftest: mutant KILLED: missing_estop_latch
selftest: mutant KILLED: missing_overflow_guard
selftest: mutant KILLED: no_dry_restart
selftest: mutant KILLED: swapped_valves
selftest: kill rate 6/6 (100%)
selftest: determinism PASS (same seed -> identical verdict)
selftest: PASS
wall: 36.34 s   exit: 0          # second fresh install: wall: 39.36 s, exit 0, same text
```

Mutant → first failing gate (from my own regenerated verdict JSONs):

| mutant | failing gates (scenario: gates) |
|---|---|
| `estop_not_safe` | `estop: estop_off_from_401`, `recovery: no_actuation_500_700` |
| `inverted_dryrun` | `cycle: autocycle>=2`, `dry_run: autocycle>=2` |
| `missing_estop_latch` | `estop: estop_off_from_401`, `recovery: no_actuation_500_700` |
| `missing_overflow_guard` | `overflow_guard: max_level<=94` (max_level = **100.0**) |
| `no_dry_restart` | `cycle: autocycle>=2`, `dry_run: autocycle>=2` |
| `swapped_valves` | `cycle: no_pump_inlet, autocycle>=2`; `dry_run: no_pump_inlet, autocycle>=2`; `dry_interlock_fault: no_pump_inlet` |

### 1.4 `bash judge/grade.sh examples/good/tank_ctrl.st` — exit 0 (seed 20261014)

```text
$ bash judge/grade.sh examples/good/tank_ctrl.st --json good_run1.json
cycle: PASS []
overflow_guard: PASS []
dry_run: PASS []
dry_interlock_fault: PASS []
lowsw_false_trip: PASS []
estop: PASS []
recovery: PASS []
random_faults: PASS []
grade: PASS (all gates; judge integrity verified)
wall: 4.34 s   exit: 0
```

Verdict JSON (`good_run1.json`), in full:

```json
{
  "pass": true,
  "scenarios": 8,
  "results": [
    { "name": "cycle",                "pass": true, "failures": [], "n_scans": 12000,
      "min_level": 14.99999999999483,  "max_level": 85.01999999999957 },
    { "name": "overflow_guard",      "pass": true, "failures": [], "n_scans": 12000,
      "min_level": 70.0,               "max_level": 88.01999999999641 },
    { "name": "dry_run",             "pass": true, "failures": [], "n_scans": 12000,
      "min_level": 10.0,               "max_level": 85.01999999999822 },
    { "name": "dry_interlock_fault", "pass": true, "failures": [], "n_scans": 12000,
      "min_level": 14.999999999996977, "max_level": 85.01999999999957 },
    { "name": "lowsw_false_trip",    "pass": true, "failures": [], "n_scans": 12000,
      "min_level": 62.54999999999815, "max_level": 85.019999999999 },
    { "name": "estop",               "pass": true, "failures": [], "n_scans": 12000,
      "min_level": 40.0,               "max_level": 48.00000000000125 },
    { "name": "recovery",            "pass": true, "failures": [], "n_scans": 12000,
      "min_level": 14.99999999999483,  "max_level": 85.01999999999957 },
    { "name": "random_faults",       "pass": true, "failures": [], "n_scans": 12000,
      "min_level": 40.0,               "max_level": 55.24000000000238 }
  ]
}
```

Note: the verdict dict has **no `timing` key at all** (keys are exactly
`pass`, `scenarios`, `results`), so the README's "ignoring the `timing` key" refers
to a key `judge/grade.py` never writes.

Derived key numbers: scenarios 8/8 PASS; kill rate 6/6 = 100 %; max level over all
scenarios **88.01999999999641 cm** (≤ 94); min level **10.00 cm** (`dry_run` start
level; pump never on below 15 — gate `pump_never_dry` passed in all 8).
sha256 of `good_run1.json`:
`bf1dd3a491fe06a8e0225d3e8db79acf3a36ac48b4d561407cbcff0d9afc6f02`.

Second fresh install → `bf1dd3a491fe06a8e0225d3e8db79acf3a36ac48b4d561407cbcff0d9afc6f02`
again (`cmp`: byte-identical).

### 1.5 `bash media/make_data.sh` — exit 0

```text
$ bash media/make_data.sh
selftest: kill rate 6/6 (100%)
selftest: determinism PASS (same seed -> identical verdict)
selftest: PASS
make_data.sh: determinism PASS (same seed -> byte-identical verdict JSON)
make_data.sh: mutant estop_not_safe failed the judge (expected)
make_data.sh: mutant inverted_dryrun failed the judge (expected)
make_data.sh: mutant missing_estop_latch failed the judge (expected)
make_data.sh: mutant missing_overflow_guard failed the judge (expected)
make_data.sh: mutant no_dry_restart failed the judge (expected)
make_data.sh: mutant swapped_valves failed the judge (expected)
make_data.sh: wrote /home/user/w/cookbook/plc-st/media/data:
...
wall: 72.38 s   exit: 0
```

### 1.6 `bash media/make_media.sh` — exit 0

```text
$ bash media/make_media.sh
Generating title frames... / result frames... / loop frames... / scenario frames... /
mutant frames... / summary frames...
Done. Generated 1140 frames in /home/user/w/cookbook/plc-st/media/master/
Duration: 38.0 seconds at 30 fps
=== Media verification ===
-rw-r--r-- 1 user user 875945 .../demo.mp4
-rw-r--r-- 1 user user 116394 .../loop.png
-rw-r--r-- 1 user user 108454 .../result.png
h264,1920,1080,38.000000
MANIFEST.json written
31ff1ae1a0ae94bae0beda3960c9dea66eb967fdccb281b9965d7d79ac39ac84  result.png
e17db7bba5386d706fc1a3c08472400feb13d305c334817123dda4a19bdb2db9  loop.png
45db0438981f9b917d2f08bcd67c1c00fd1ba687e7d075caecf129d37861721c  demo.mp4
e49efdbd5a5a888590623b47ec4eae8c8e2dd35b6840e1932c248270645abf55  MANIFEST.json
wall: 323.59 s   exit: 0
```

Pinned venv actually installed by the script: `matplotlib 3.8.4`, `numpy 1.26.4`,
`pillow 10.3.0` (venv python 3.12.15) — exactly the pins in `make_media.sh`.

---

## 2. My numbers vs `RECEIPT.md` (RECEIPT read only after the above)

| # | item | mine | RECEIPT.md | SPEC tolerance / rule | verdict |
|---|---|---|---|---|---|
| 1 | overall verdict | PASS, 8/8 scenarios | PASS, 8/8 | every scenario must pass | **MATCH** |
| 2 | kill rate | 6/6 = 100 % | 6/6 = 100 % | ≥ 90 % (SPEC "Acceptance oracle") | **MATCH** |
| 3 | known-good grade | PASS, exit 0 | PASS, exit 0 | exit 0 iff all gates pass | **MATCH** |
| 4 | per-scenario results | byte-identical verdict JSON (sha `bf1dd3a4…`) | same numbers, incl. `min_level`/`max_level` to the last digit | numeric gates, no tolerance band | **MATCH** |
| 5 | max level (all scenarios) | 88.01999999999641 ≈ **88.02 cm** | 88.02 cm | ≤ 94 cm (`DESIGN_CAP`) | **MATCH** |
| 6 | min level (all scenarios) | **10.00 cm** (`dry_run` start level) | 10.00 cm | pump never on with level < 15 cm | **MATCH** |
| 7 | determinism | byte-identical verdict JSON for the same seed (see §3) | "identical verdict JSON" | determinism claim in README | **MATCH** |
| 8 | `run.py` end to end | not run (exit 1, no `SBX_API_KEY`/`sbx`) | not run ("What was not run here") | — | **MATCH** (same limitation) |
| 9 | MATIEC pin | commit `75d6e82c…`, tarball sha256 `a679c8e6…` re-verified by me | same | exact sha256 | **MATCH** |
| 10 | `iec2c -v` output | `matiec version 0.1` / `changeset id:` (empty) | identical | — | **MATCH** |
| 11 | gcc | 12.2.0 (Debian 12.2.0-14+deb12u1) | 12.2.0-14+deb12u1 | Debian 12.2.0 per SPEC | **MATCH** |
| 12 | make | GNU Make 4.3 | 4.3 | 4.3 | **MATCH** |
| 13 | bison | 3.8.2 (`2:3.8.2+dfsg-1+b1`) | 3.8.2 | 3.8.2 | **MATCH** (dpkg build-string differs from VERSIONS.txt `2:3.8.2+dfsg-1`) |
| 14 | flex | 2.6.4 (`2.6.4-8.2`) | 2.6.4 | 2.6.4 | **MATCH** (VERSIONS.txt says `2.6.4-8`) |
| 15 | autoconf / automake / libtool | 2.71-3 / 1:1.16.5-1.3 / 2.4.7-7~deb12u1 | 2.71 / 1.16.5 / 2.4.7 | — | **MATCH** |
| 16 | Python | 3.12.15 (`/usr/local/bin/python3`) | 3.12.15 | "3.11+ (stdlib only)" | **MATCH** (both differ from VERSIONS.txt's `python3: 3.11.2-6`: `python3` on PATH is not the Debian `python3` package 3.11.2-1+b1) |
| 17 | ffmpeg (media) | `ffmpeg version 5.1.9-0+deb12u1` | (not stated) | no pin in SPEC/VERSIONS | noted |
| 18 | setup wall (fresh) | 44.14 s (with apt) / 39.85 s (deps present) | ~43 s (42.718 s) | no tolerance stated | **MATCH** in magnitude; both above README's ~39 s |
| 19 | selftest wall | 36.34 s / 39.36 s | ~42 s (41.707 s) | none stated | **MATCH** in magnitude (README claims ~33 s) |
| 20 | grade wall | 3.95–4.40 s | ~5 s (5.029 s) | none stated | **MATCH** in magnitude |
| 21 | second fresh run identical | yes — `rm -rf ~/.plc-st`, re-run setup+selftest+grade → identical output and byte-identical verdict JSON | yes (hardening §3) | — | **MATCH** |
| 22 | media data (17 files) | 17/17 sha256 == MANIFEST | — | — | **MATCH** (see §4) |
| 23 | media binaries | result.png / loop.png / demo.mp4 sha256 == MANIFEST | — | — | **MATCH** (see §4) |

Divergences that are *not* verdict-affecting: wall times (README ~39/33/5 s vs
RECEIPT ~43/42/5 s vs mine 40–44/36–39/4–4.4 s); the SPEC nowhere states a timing
tolerance, so these are magnitude-only comparisons. Also, `judge/VERSIONS.txt`
records bison `2:3.8.2+dfsg-1`, flex `2.6.4-8` and `python3: 3.11.2-6`, none of
which is what `setup.sh`/`grade.py` actually end up using on this box (dpkg
`2:3.8.2+dfsg-1+b1`, `2.6.4-8.2`, interpreter 3.12.15) — the RECEIPT agrees with my
machine, so VERSIONS.txt is the outlier.

---

## 3. Determinism: `grade.sh` twice, same seed (README step 3)

```text
$ bash judge/grade.sh examples/good/tank_ctrl.st --json good_run1.json ; echo $?
cycle: PASS [] ... random_faults: PASS []
grade: PASS (all gates; judge integrity verified)     wall: 4.34 s   exit: 0
$ bash judge/grade.sh examples/good/tank_ctrl.st --json good_run2.json ; echo $?
                                                      wall: 4.07 s   exit: 0
$ cmp good_run1.json good_run2.json && echo "cmp: byte-identical"
cmp: byte-identical
$ python3 -c "import json; a=json.load(open('good_run1.json')); b=json.load(open('good_run2.json'));
  a.pop('timing',None); b.pop('timing',None); print(a==b, sorted(a.keys()))"
True ['pass', 'results', 'scenarios']
```

**Identical.** Note the stripped `timing` key does not exist (`sorted(a.keys())` is
`['pass','results','scenarios']`), so the comparison is byte-for-byte equality, which
is stronger than what the README asks for. Also reproduced with the other two seeds
the RECEIPT used:

```text
$ bash judge/grade.sh examples/good/tank_ctrl.st --seed 999999 --json det_a.json   # wall 4.40 s exit 0
$ bash judge/grade.sh examples/good/tank_ctrl.st --seed 999999 --json det_b.json   # wall 4.24 s exit 0
$ sha256sum det_a.json det_b.json
0be5e608b50fb02a4c327d1f8b9ebf7e91f90381d9f9873fffdfc4c680fe3dc2  det_a.json
0be5e608b50fb02a4c327d1f8b9ebf7e91f90381d9f9873fffdfc4c680fe3dc2  det_b.json
-> identical; verdict pass=true, 8/8, random_faults max_level = 44.0

$ bash judge/grade.sh examples/good/tank_ctrl.st --seed 12345 --json {a,b}.json    # both exit 0
$ cmp 12345_a 12345_b -> identical, sha 0be5e608… (same recorded min/max as seed 999999)
```

Seed sensitivity is real (seed 20261014 → `random_faults` max 55.24 cm vs 44.00 cm for
999999/12345), all three still 8/8 PASS.

---

## 4. Media rebuild vs `media/MANIFEST.json`

Rebuilt with the README's own commands (`make_data.sh` then `make_media.sh`), then
compared every hash in `MANIFEST.json`:

| file | MANIFEST sha256 | mine | result |
|---|---|---|---|
| `result.png` | `31ff1ae1a0ae94bae0beda3960c9dea66eb967fdccb281b9965d7d79ac39ac84` | same | **MATCH** (byte-identical, 108454 B) |
| `loop.png` | `e17db7bba5386d706fc1a3c08472400feb13d305c334817123dda4a19bdb2db9` | same | **MATCH** (byte-identical, 116394 B) |
| `demo.mp4` | `45db0438981f9b917d2f08bcd67c1c00fd1ba687e7d075caecf129d37861721c` | same | **MATCH** (byte-identical, 875945 B) |
| `data/grade_good.json` (+`_replica`) | `bf1dd3a4…` / `bf1dd3a4…` | same | **MATCH** |
| `data/grade_estop_not_safe.json`, `…missing_estop_latch.json` | `094f956e…` (both) | same | **MATCH** |
| `data/grade_inverted_dryrun.json` | `d5a52148…` | same | **MATCH** |
| `data/grade_missing_overflow_guard.json` | `572c525c…` | same | **MATCH** |
| `data/grade_no_dry_restart.json` | `7dd9c512…` | same | **MATCH** |
| `data/grade_swapped_valves.json` | `3e9b39a0…` | same | **MATCH** |
| `data/selftest_output.txt` | `5086c584…` | same | **MATCH** |
| `data/traces_good/trace_*.csv` (8 files) | listed in MANIFEST | same | **8/8 MATCH** |
| **totals** | 17 data files + 3 binaries + MANIFEST | | **20/20 MATCH** |

There were **no PNG/MP4 differences** to investigate: the regenerated
`result.png`, `loop.png` and `demo.mp4` are byte-identical to the committed ones, and
the underlying `media/data/` files are byte-identical too, so the "if the media
differs, do the data files match?" question does not arise here. `git status` on the
demo directory is clean after the full rebuild (including `MANIFEST.json`, whose
`ffmpeg_version` field records the same `5.1.9-0+deb12u1` I have). The regenerated
PNG has no timestamp chunk and the x264 encode is deterministic here, so the rebuild
is byte-stable, not merely visually equal.

---

## 5. README steps that were unclear, wrong or missing

1. **`run.py` is the only documented entry point, and it is unusable without a hosted
   key.** Exact output (above, §1.1):
   `plc-st: export SBX_API_KEY (or E2B_API_KEY) first; get one at https://sbx.agent-next.com/console`
   (exit 1). The README never says the judge can be run locally — I had to extract the
   in-sandbox script from `run.py:70-84` to learn the equivalent local sequence. A
   "local / sandboxless run" section is missing.
2. **The seed behind the headline numbers is not in the README.** Nothing in
   `README.md` says the 8/8, 88.02 cm, 100 % figures come from `--seed 20261014`
   (only `judge/grade.sh:24` / `judge/grade.py:280` reveal it); `selftest.sh` silently
   uses 999999. Without that, "reproduce the README numbers" is guesswork — and the
   seed does change results (55.24 vs 44.00 cm in `random_faults`).
3. **The "ignoring the `timing` key" instruction is stale.** `judge/grade.py` never
   emits a `timing` key (verdict keys are exactly `pass`, `scenarios`, `results`), so
   both the README's determinism wording and `selftest.sh`'s "except timing" comment
   describe something that does not exist. Harmless, but it reads as if a
   non-deterministic timing field had to be scrubbed.
4. **Wall-time table does not match a truly fresh sandbox.** README: setup ~39 s,
   selftest ~33 s, grade ~5 s; mine: 44.14 s / 36.34 s / 4.07 s (2 vCPU, 3.9 GB). The
   ~39 s setup figure only holds when bison/flex/autoconf/automake/libtool are already
   installed; `setup.sh`'s own `apt_ensure` silently adds an `apt-get install` step the
   README never mentions (and which needs `sudo`, noisy here:
   `sudo: unable to resolve host instance: Name or service not known`). SPEC/README
   state no tolerance for these numbers, so "~" cannot be falsified either way.
5. **`run.py` line 72 contains a real escape bug (Python 3.12 SyntaxWarning).**
   `run.py:85: SyntaxWarning: invalid escape sequence '\$'`, and the in-sandbox script
   really does contain a literal `cd \$HOME`:
   `'cd /root 2>/dev/null || cd \$HOME'`. In bash that means `cd` to a directory named
   `$HOME`:
   ```text
   $ bash -c 'cd /root 2>/dev/null || cd \$HOME; echo rc=$?'
   bash: line 1: cd: $HOME: No such file or directory
   cd rc=1
   ```
    So if the sandbox exec user is not root, `set -euo pipefail` aborts the whole
    in-sandbox pipeline before anything is graded. (Masked here because `run.py`
    bailed out earlier on the missing key, and in a root exec shell `cd /root`
    succeeds.)
6. **"Rebuilding the media" hard-fails without `media/data/`, and the README does not
   say the committed data blobs are the prerequisite.** `make_media.sh:14` exits with
   `run media/make_data.sh first` (exit 1) when `media/data/` is absent — I confirmed
   by running it with the data directory moved aside. On a fresh clone the data blobs
   are committed (~3 MB of text), so `make_media.sh` alone does work there; but the
   README never states that `make_data.sh` is the only step that re-proves
   determinism (its `cmp` at lines 43-44) or that `make_data.sh` is needed only to
   *refresh* those blobs. It also gives no offline/no-PyPI fallback, and does not
   mention that `media/master/` + `media/.venv/` (~290 MB combined) appear as build
   outputs.
7. **Working directory is never stated.** The README shows `python3 cookbook/plc-st/run.py`
    (repo root) but then `bash judge/setup.sh` and `bash media/make_data.sh`
    (relative to `cookbook/plc-st`). The scripts happen to be `HERE`-relative, but the
    reader is left to infer two different cwds.
8. **Media rebuild prerequisites are understated.** `make_media.sh` needs network
    access (pip installs `matplotlib==3.8.4`, `numpy==1.26.4`, `pillow==10.3.0`),
   creates `media/.venv` (~184 MB) and `media/master` (~106 MB, 1140 frames) inside
   the repo, and needs `ffmpeg`/`ffprobe`. The README lists none of this, and the
   deploy takes ~5.4 min on 2 vCPU (`wall: 323.59 s`) — there is no partial-output
   fallback if pip or ffmpeg is missing. The pip/ffmpeg pins live only as shell
   variables inside `make_media.sh`; they are absent from SPEC.md's pinned-tools table
   and from `judge/VERSIONS.txt`, which contradicts SPEC's "No tool is fetched with
   `latest` … pinned either by exact release sha256 or by exact Debian package
   version" (the pip pins have no sha256).
 9. **Missing-toolchain errors are fine but undocumented** (worth a README line, since
    a fresh box hits them):
    ```text
    $ bash judge/grade.sh examples/good/tank_ctrl.st      # no ~/.plc-st
    grade: iec2c not installed -- run 'bash judge/setup.sh' first (looks for /home/user/.plc-st/bin/iec2c)
    wall: 0.03 s   exit: 1
    $ bash media/make_data.sh                              # no ~/.plc-st
    make_data.sh: iec2c not installed -- run 'bash judge/setup.sh' first
    wall: 0.03 s   exit: 1
    ```
 10. **SPEC.md contradicts itself and overstates two gates** (it is the artefact the
    README tells you to read first): SPEC says the judge "runs six deterministic
   scenarios" (SPEC.md:83-85) while its own table and `grade.py` run **eight**; and
   row 7 claims `recovery` "resumes autocycle after 700", while `recovers_gate()`
   (`judge/grade.py:171-172`) only checks that the `running` output is TRUE somewhere
   in the last 300 scans — no level excursion is required. SPEC:63-64 also words the
   dry-run rule as "pump must never run while `level < 15 cm` **AND** the low switch
   reports dry", which is looser than the implemented gate
   (`not (pump and level < 15)`, regardless of the switch).
 11. **`run.py`'s default `--ref main` does not point at this tree.** The demo under
     test here lives on branch `sbx/demo-plc-st-repro2` @ `a25347bc…`, so a literal
     `run.py` run would grade upstream `main`, whose contents I did not verify. I
     graded the local working tree instead and said so.

---

## 6. What was not run

- `python3 cookbook/plc-st/run.py` end to end (no `SBX_API_KEY`/`E2B_API_KEY`, no
  `sbx` CLI → exit 1; no sandbox created, so no sandbox to kill).
- The "Ask your agent" prompt (needs a live agent session).
- Nothing was created that needs cleanup on the sandbox side: no `sbx` sandbox,
  snapshot, template or id was created by me at any point.

## 7. Conclusion

Every claim in the README's Results block and every numeric item in `RECEIPT.md`
reproduced independently on this fresh sandbox: 8/8 scenarios PASS, 6/6 mutants
killed (100 %), max level 88.02 cm ≤ 94 cm, min level 10.00 cm with the pump never
running below 15 cm, byte-identical verdict JSONs for a fixed seed, byte-identical
media (PNG/MP4) and 17/17 media data files against `media/MANIFEST.json`, with the
pinned MATIEC tarball sha256 re-verified. The only real gaps are documentation and
environment ones (missing seed disclosure, stale `timing` key, unstated cwd, and the
`cd \$HOME` bug plus the hidden apt/pip/ffmpeg prerequisites in the run/media paths),
none of which changes a verdict.
