# REPRODUCE — doc-extract-convert

Independent reproduction by a **different agent** (a different model family
from the builder), following **only `README.md`**, in a fresh sandbox, with
the judge's own numbers compared against `RECEIPT.md`.

Tolerances are those stated in [SPEC.md](SPEC.md#reproducibility): the
verdict JSON must match byte-for-byte apart from `timing`, and the two
measured numbers (field accuracy, quarantine count) must be identical.

> **Status: not yet recorded.**
>
> The standard requires this file to be written by an agent *other than the
> one that built the demo*, which cannot be done from inside the building
> run — an agent reproducing its own work is not an independent check. The
> protocol below is exactly what such an agent should do; the recorded
> numbers go in the table at the bottom, which stays empty until that run
> happens.
>
> **What is already independent:** the *judge* is checked by a different
> model family — the FIX-FIRST review of this demo's PR re-ran the judge from
> a clean clone and confirmed the truth oracle, the drift refusal at
> `--seed 7`, 15/16 Pillow pins against PyPI and a 6/6 kill rate. The
> numbers it produced are in [RECEIPT.md](RECEIPT.md).

## Protocol — follow README.md alone

1. **Start from a fresh sandbox.** Nothing pre-installed, no cached corpus,
   no warm byte-code.

   ```bash
   export SBX_API_KEY=<your key>
   pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
   python3 cookbook/doc-extract-convert/run.py --ref <the branch under test>
   ```

   Expect: `exit=0` for every step, a `PASS` verdict, and the sandbox id
   confirmed gone (`[run] confirmed: <id> is gone`). Non-zero exit or a
   missing confirmation line is a **failed** reproduction — report it as one.

2. **Then repeat the three steps by hand inside a second fresh sandbox**,
   exactly as README.md's "In-sandbox / no API key" section writes them,
   and keep the raw output:

   ```bash
   bash judge/setup.sh
   bash judge/selftest.sh
   bash judge/grade.sh examples/good --json /tmp/v.json --seed 42
   ```

3. **Check the numbers** against the table below. Report any difference,
   however small, rather than rounding it away.

4. **Confirm the judge can still fail**, from the same sandbox, so the
   reproduction is not just "the tool ran":

   ```bash
   python3 judge/mutants.py --src examples/good --out /tmp/bad
   bash judge/grade.sh /tmp/bad/m01-total-as-float --seed 42   # must fail
   ```

5. **Kill the sandbox** and confirm with `sbx list` that the id is gone.

## What must match

| quantity | expected | from |
|---|---|---|
| `setup.sh` exit | 0 | `judge/VERSIONS.txt` written at the end |
| `selftest.sh` exit | 0 | |
| kill rate | 6/6 = 100 % (rule: ≥ 90 %, ≥ 5 mutants) | |
| judge-guard mutant | killed (the weakened ink check must fail the good artifact) | |
| determinism | two runs at seed 42 identical apart from `timing` | |
| `grade.sh` exit | 0 | |
| G1 field accuracy | 48/48 = 1.000 (line: ≥ 0.95) | |
| G3 exact totals | 11/11 at 0 ulp | |
| G2 grounding | 0 boxes failing the ink check | |
| G4 negative control | 2/2 corrupted pages quarantined, 0 invented values, 12/12 pages accounted | |

Wall times are **not** a tolerance: the sandbox is 2 vCPU and the grading
runs share it, so seconds vary run to run. Report them, but do not fail the
reproduction on them.

## Recorded runs

| quantity | builder (`RECEIPT.md`) | independent agent | match? |
|---|---|---|---|
| setup exit | 0 | | |
| selftest exit | 0 | | |
| grade exit | 0 | | |
| kill rate | 6/6 | | |
| field accuracy | 48/48 | | |
| exact totals | 11/11 | | |
| grounding failures | 0 | | |
| negative control | 2/2 quarantined, 12/12 accounted | | |

_Filled in by the reproducing agent, with the sandbox id and the commit it
reproduced, as soon as that run happens._