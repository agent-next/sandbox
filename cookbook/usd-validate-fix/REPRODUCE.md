# REPRODUCE.md — independent reproduction

DEMO-STANDARD.md: "before merge, a different agent (different model family
from the builder) follows only README.md in a fresh sandbox and records its
numbers in `REPRODUCE.md`; numbers must match the RECEIPT within the
tolerances stated in SPEC.md."

## Status: not done in this environment

The independent reproduction has **not** been run here, and this file says
so rather than claiming it has:

- It needs a *fresh sandbox*, which needs an `SBX_API_KEY`
  (`run.py` reads that key from the environment and there is no
  `sbx login`). No such key exists in the environment that built this
  branch, so `run.py` cannot create a sandbox and a different agent cannot
  be started in one.
- It needs a second agent from a different model family, which also
  requires API access this environment does not have.

So the comparison table below is **not filled in** — a filled-in table
copied from the RECEIPT would be a fabricated reproduction, which is worse
than a missing one (LESSONS.md: "A lost reply is not a confirmation:
verify, and report failure instead of claiming success").

## What to run

For whoever can run it (a fresh Debian sandbox, 2 vCPU / ~4 GiB, Python
3.10–3.12, with `SBX_API_KEY` set), following **only README.md**:

```bash
export SBX_API_KEY=<your key>
python3 cookbook/usd-validate-fix/run.py
```

or the judge directly, following README's "Ask your agent" prompt:

```bash
git clone --depth 1 -b <ref> https://github.com/agent-next/sandbox
cd sandbox
bash cookbook/usd-validate-fix/judge/setup.sh
bash cookbook/usd-validate-fix/judge/selftest.sh
bash cookbook/usd-validate-fix/judge/grade.sh \
    cookbook/usd-validate-fix/examples/good/traffic_cone_fixed.usda \
    --seed 20261015 --json /tmp/repro.json
python3 cookbook/tools/video_gate.py \
    cookbook/usd-validate-fix/media/demo.mp4
```

## Verdict comparison (to fill in)

| Metric | RECEIPT.md | Reproduction | Match? |
|--------|------------|--------------|--------|
| `setup.sh` wall | ~36 s | | |
| `selftest.sh` wall | ~110 s | | |
| `selftest.sh` exit | 0 | | |
| kill rate | 16/16 = 100 % | | |
| determinism (--seed 1 twice) | OK | | |
| `grade.sh` exit | 0 | | |
| `grade.sh` wall | ~3 s | | |
| gate 1 validator status | PASS, 0 FAILURE / 0 ERROR | | |
| gate 2 oracle errors | 0 | | |
| gate 3 world bbox deviation | 0 cm (tolerance 1e-6) | | |
| gate 4 recount errors | 0 | | |
| gate 5 height axis | Y, margin 22 cm (>= 5) | | |
| verdict body vs RECEIPT (excl. `timing`) | identical | | |
| `video_gate.py` | `passed: true` | | |

Tolerances: SPEC.md gates are exact-count or <= 1e-6 cm tolerances, and the
verdict must be byte-identical apart from the `timing` key; wall times may
differ by any amount.

## Deviations (to fill in)

[Any difference explained here]

## Verification (to fill in)

- [ ] all gate measurements match RECEIPT.md within SPEC.md tolerances
- [ ] the two verdict bodies are byte-identical except `timing`
- [ ] `python3 cookbook/tools/video_gate.py media/demo.mp4` prints
      `passed: true`
