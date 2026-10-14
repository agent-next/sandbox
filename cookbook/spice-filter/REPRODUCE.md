VERDICT: REPRODUCED

# REPRODUCE — `cookbook/spice-filter/`

Independent reproduction from `README.md` + `SPEC.md` only. `RECEIPT.md`
was read only after my own numbers were measured (criterion 1).
Sandbox: Debian GNU/Linux 12 (bookworm), Linux x86_64, passwordless sudo —
the base image the SPEC pins (`judge/setup.sh`, ngspice 39.3+ds-1 from
Debian bookworm).

No step failed, so there is no error output to record anywhere below.

## 1. Setup — `bash judge/setup.sh`

```text
$ cd cookbook/spice-filter && time bash judge/setup.sh
setup: downloading ngspice 39.3+ds-1 from Debian pool
/tmp/tmp.HXLdzwBp8w/ngspice.deb: OK
sudo: unable to resolve host instance: Name or service not known
sudo: unable to resolve host instance: Name or service not known
debconf: delaying package configuration, since apt-utils is not installed
Selecting previously unselected package ngspice.
(Reading database ... 30273 files and directories currently installed.)
Preparing to unpack .../ngspice_39.3+ds-1_amd64.deb ...
Unpacking ngspice (39.3+ds-1) ...
Setting up ngspice (39.3+ds-1) ...
setup: tool versions
** ngspice-39 : Circuit level simulation program
ngspice debian package: 39.3+ds-1
Python 3.12.15
setup: wrote /home/user/w/cookbook/spice-filter/judge/VERSIONS.txt
setup: done
EXIT=0

real	0m5.426s
user	0m3.704s
sys	0m1.187s
```

Download verified by `sha256sum -c` inside setup (`.deb: OK`). Cosmetic
`sudo: unable to resolve host instance` warnings do not affect the exit
code. The pre-existing committed `judge/VERSIONS.txt` was rewritten by
setup.sh with byte-identical content (ngspice-39, 39.3+ds-1, python
3.12.15). Fresh-install wall time 5.43 s (README table says ~3.2 s, RECEIPT
3.3 s — slower here; see §7).

## 2. Self-test — `bash judge/selftest.sh`

```text
$ time bash judge/selftest.sh
selftest: grading known-good /home/user/w/cookbook/spice-filter/examples/good/lpf4sk.cir
selftest: known-good PASSED all gates
mutants: r-decade-up.cir  edit: 'R1 in s1a 750' -> 'R1 in s1a 7.5k'
mutants: c-decade-down.cir  edit: 'C3 s2a out 680n' -> 'C3 s2a out 68n'
mutants: off-series.cir  edit: 'R2 s1a s1b 750' -> 'R2 s1a s1b 740'
mutants: swap-nodes.cir  edit: 'C1 s1a out1 120n' -> 'C1 s1b out1 120n'
mutants: missing-ground.cir  edit: 'C2 s1b 0 100n' -> 'C2 s1b gnd0 100n'
mutants: opamp-gain.cir  edit: 'E2 out 0 s2b 0 1' -> 'E2 out 0 s2b 0 100'
mutants: include-directive.cir  edit: +'.include "helpers.inc"'
mutants: unrecognised-topology.cir  edit: +'Rbias s1a s1b 1meg' (parallel damping resistor: valid design, shape the oracle cannot verify)
mutants: swap-feedback.cir  edit: 'C1 s1a out1 120n' -> 'C1 s1a 0 120n'
mutants: wrote 9 mutants to /tmp/tmp.brUBQ3MTOZ/mutants
selftest: killed    c-decade-down (gate: mask)
selftest: killed    include-directive (gate: parse)
selftest: killed    missing-ground (gate: parse)
selftest: killed    off-series (gate: series)
selftest: killed    opamp-gain (gate: sanity)
selftest: killed    r-decade-up (gate: mask)
selftest: killed    swap-feedback (gate: mask)
selftest: killed    swap-nodes (gate: mask)
selftest: killed    unrecognised-topology (gate: analytic)
selftest: kill rate 9/9 = 100%
selftest: determinism OK (two --seed 1 runs byte-identical)
selftest: OK
EXIT=0

real	0m7.877s
user	0m5.012s
sys	0m2.199s
```

Kill rate 9/9 = 100 % (requirement ≥ 90 %, ≥ 5 mutants — SPEC), every
mutant killed, gate attribution per mutant identical to the RECEIPT's
paste. Determinism line present. Wall 7.88 s (README 6.8 s, RECEIPT
6.4–7.0 s — slower here; see §7).

## 3. Grade the good example — `bash judge/grade.sh examples/good/lpf4sk.cir --json good.json`

Seed 20261014 = SPEC default (`--seed` default), which is also the seed
shown in the RECEIPT's verdict JSON.

```text
$ time bash judge/grade.sh examples/good/lpf4sk.cir --json good.json
{ ...verdict JSON printed... }
EXIT=0

real	0m1.808s
user	0m1.178s
sys	0m0.584s
```

Full verdict JSON as produced (pretty-printed copy):

```json
{
  "artifact": "examples/good/lpf4sk.cir",
  "seed": 20261014,
  "passed": true,
  "gates": {
    "parse":       { "passed": true, "points": 801, "f_grid": "10..100000 200/dec" },
    "sanity":      { "passed": true, "dc_gain_db": -0.0 },
    "mask":        { "passed": true, "ripple_db": 0.096,
                     "stopband_max_db": -56.14 },
    "analytic":    { "passed": true, "max_deviation_db": 0.0,
                     "gbw_deviation_db": 0.15029, "gbw_hz": 1000000.0 },
    "series":      { "passed": true, "off_series": [] },
    "montecarlo":  { "passed": true, "runs": 100, "seed": 20261014,
                     "pass_fraction": 1.0,
                     "worst_ripple_db": 0.757,
                     "worst_stopband_db": -53.193 }
  }
}
```

## 4. Comparison with RECEIPT.md

Tolerance basis (SPEC): all judge gates are deterministic and numeric;
with a fixed seed the SPEC requires the pass fraction to be *identical*
between two consecutive `grade.sh` runs, and `selftest.sh` requires
byte-identical verdict JSON for same-seed runs. So the tolerance for
every verdict field is exact equality; gate limits (ripple ≤ 1.0 dB,
stopband ≤ −40 dB, ideal oracle ≤ 0.05 dB, GBW oracle ≤ 0.5 dB,
pass fraction ≥ 90 %) are pass thresholds, not tolerances.

| item | mine | RECEIPT | tolerance | result |
|---|---|---|---|---|
| verdict `passed` | true | true | exact | match |
| exit code (setup/selftest/grade) | 0/0/0 | 0/0/0 | exact | match |
| kill rate | 9/9 = 100 % | 9/9 = 100 % | exact (req. ≥ 90 %) | match |
| `ripple_db` | 0.096 | 0.096 | exact (deterministic gate) | match |
| `stopband_max_db` | −56.14 | −56.14 | exact | match |
| `max_deviation_db` (ideal) | 0.0 | 0.0 | exact | match |
| `gbw_deviation_db` (1 MHz macro-model) | 0.15029 | 0.15029 | exact (limit 0.5) | match |
| MC `pass_fraction` | 1.0 (100 runs) | 1.0 (100 runs) | exact / identical between runs | match |
| MC `worst_ripple_db` | 0.757 | 0.757 | exact | match |
| MC `worst_stopband_db` | −53.193 | −53.193 | exact | match |
| `parse` points | 801 | 801 | exact | match |
| `sanity` `dc_gain_db` | −0.0 | −0.0 | exact | match |
| `series` `off_series` | [] | [] | exact | match |
| seed used | 20261014 (default) | 20261014 | exact | match |
| ngspice version | 39.3+ds-1 (dpkg + `ngspice -v` line 2) | 39.3+ds-1 | exact (pinned) | match |
| python3 | 3.12.15 | 3.12.15 | exact (pinned ≥ 3.10) | match |
| ffmpeg (media env, MANIFEST) | 5.1.9-0+deb12u1 | 5.1.9-0+deb12u1 | exact | match |
| .deb sha256 | `710bc58f…c42d32f9` OK (inside setup output) | `710bc58f…c42d32f9` OK | exact | match |
| wall: setup.sh fresh | 5.43 s | 3.3 s | none stated | mismatch (slower env) |
| wall: selftest.sh | 7.88 s | 7.0 / 6.4 s | none stated | mismatch (slower env) |
| wall: grade.sh good | 1.81 s | 2.1 s | none stated | match (within 0.3 s) |

Key-numbers section of the README (ripple 0.096 dB, stopband −56.14 dB,
GBW deviation 0.150 dB, MC 100/100, kill rate 9/9 = 100 %) — all five
reproduce exactly.

## 5. Determinism — `grade.sh` twice, same seed

```text
$ bash judge/grade.sh examples/good/lpf4sk.cir --seed 20261014 --json det1.json ; echo "RUN1 EXIT=$?"
RUN1 EXIT=0
$ bash judge/grade.sh examples/good/lpf4sk.cir --seed 20261014 --json det2.json ; echo "RUN2 EXIT=$?"
RUN2 EXIT=0
$ diff det1.json det2.json && echo "DIFF: identical"
DIFF: identical
$ cmp det1.json det2.json && echo "CMP: byte-identical"
CMP: byte-identical
```

Identical: **yes** (byte-identical, `cmp` clean). There is no `timing`
key in the verdict JSON at all — the verdict's top-level keys are
exactly `artifact`, `gates`, `passed`, `seed` — so "ignoring the timing
key" changes nothing. `det1.json` also equals the §3 default-seed run.

## 6. Media rebuild — `bash media/make_media.sh` vs `media/MANIFEST.json`

```text
$ time bash media/make_media.sh
... (venv creation, replay grading, 1200-frame render, ffmpeg encodes) ...
MANIFEST.json written
media: demo.mp4 is 525752 bytes
media: done
EXIT=0

real	12m55.774s
```

Rebuilt sha256 vs `media/MANIFEST.json` (committed, and regenerated
byte-identical by the run itself):

| file | rebuilt sha256 | MANIFEST sha256 | size | result |
|---|---|---|---|---|
| result.png | `5f3cc17b…72a271e` | `5f3cc17b…72a271e` | 184383 B | match, byte-identical |
| loop.png | `2afc87ed…4b70b691f` | `2afc87ed…4b70b691f` | 132976 B | match, byte-identical |
| demo.mp4 | `124efaba…d6ffc98a` | `124efaba…d6ffc98a` | 525752 B | match, byte-identical |
| master/demo_master.mp4 | `4352d5b1…c786c00584` | `4352d5b1…c786c00584` | 1235735 B | match, byte-identical |

PNG/MP4 differences: none — byte-identical, so the underlying data
trivially matches. Source data files: `media/data/sweep_good.json` and
`media/data/selftest.json` regenerated unchanged (git-clean after the
run). `media/data/replay.json` regenerated with identical verdict
content (`passed`, `failed_gate`, `reason`, `label` per entry) but a
different absolute temp path (`/tmp/tmp.NMoHAdd23n/mutants/…` vs
`/tmp/tmp.BYvWlFOOZ6/mutants/…`) — a random `mktemp` dir baked into the
recorded `artifact` field, not a data difference; restored to the
committed copy afterwards so only this REPRODUCE.md is committed.

## 7. README step issues (criterion 5)

1. **Wrong demo.mp4 size.** README (line 20) says
   `media/demo.mp4 — 40 s animation … (1920×1080, H.264, 416 KB)`.
   The committed file is 525,752 bytes ≈ 513 KiB, and the rebuild
   reproduced exactly that. "416 KB" is wrong by ~100 KB.
2. **Wall-time table is environment-specific.** README: setup ~3.2 s,
   selftest 6.8 s, grade 1.8 s. Measured here: 5.43 s / 7.88 s / 1.81 s.
   RECEIPT measured 3.3 / 6.4–7.0 / 2.1 s. Same machine class would
   presumably match; these are soft numbers, not functional failures.
3. **One-command run not exercisable here.** `run.py` needs
   `SBX_API_KEY` and creates a cloud sandbox; this sandbox has no `sbx`
   CLI and no key, so that README step cannot be run (the RECEIPT
   records the same limitation). What could be checked passed:
   `python3 -m py_compile run.py` → exit 0; `python3 run.py --help`
   renders (`--ref`, `--keep`).
4. **Unclear/missing:** none found in setup/selftest/grade steps — every
   README step ran as written with exit 0. The only noisy output is the
   cosmetic `sudo: unable to resolve host instance: Name or service not
   known` warning during apt install (step 1); it does not change any
   exit code.

## Conclusion

Every verdict number, kill rate, key metric and tool version in the
README/RECEIPT reproduces exactly; same-seed grading is byte-identical;
the media pipeline rebuilds all committed media byte-for-byte. The only
factual error found in the README is the demo.mp4 size claim
("416 KB" vs the real 525,752 bytes). Verdict: **REPRODUCED**.

Scratch cleanup: `/tmp/spice-repro` (my scratch dir, outside the repo)
deleted. The gitignored `media/.venv`, `media/master/` and `__pycache__`
dirs are regenerable outputs of the demo's own media/ judge steps, left
in place; `git status` is clean apart from this REPRODUCE.md.
