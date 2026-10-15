# REPRODUCE.md — independent reproduction

A different agent (different model family from the builder) follows only
README.md in a fresh sandbox and records its numbers here. Numbers must
match the RECEIPT within the tolerances stated in SPEC.md.

## Reproduction run

**Agent:** [to be filled by independent agent]  
**Model family:** [to be filled]  
**Date:** [to be filled]  
**Sandbox:** fresh Debian, 2 vCPU / 3.8 GiB, Python 3.12  
**Commit:** [to be filled]

### Commands and output

```bash
# 1. Clone repo
git clone --depth 1 https://github.com/agent-next/sandbox
cd sandbox/cookbook/usd-validate-fix

# 2. Setup judge
bash judge/setup.sh
# Expected: exit 0, ~38 s, creates ~/.usd-validate-fix-venv with usd-core==25.5, usd-validation-nvidia==1.22.0

# 3. Self-test
bash judge/selftest.sh
# Expected: exit 0, ~85 s, kill rate 12/12 = 100%, determinism OK

# 4. Grade known-good
bash judge/grade.sh examples/good/traffic_cone_fixed.usda --json /tmp/v.json
# Expected: exit 0, ~4 s, verdict.passed=true, all 4 gates passed
```

### Verdict comparison

| Metric | RECEIPT (run 1) | Reproduction | Match? |
|--------|-----------------|--------------|--------|
| setup.sh exit | 0 |  |  |
| setup.sh wall | 38.7 s |  |  |
| selftest.sh exit | 0 |  |  |
| selftest.sh wall | 84.7 s |  |  |
| kill rate | 12/12 = 100% |  |  |
| determinism | OK |  |  |
| grade.sh exit | 0 |  |  |
| grade.sh wall | 3.97 s |  |  |
| validator status | PASS |  |  |
| oracle errors | 0 |  |  |
| geometry bbox dev | 0.0 cm |  |  |
| recount errors | 0 |  |  |

### Deviations

[Any differences explained here]

## Verification

- [ ] All gate measurements match RECEIPT within SPEC.md tolerances
- [ ] Two fresh-sandbox runs produce byte-identical verdict bodies (excl. timing)
- [ ] Video gate passes: `python3 cookbook/tools/video_gate.py media/demo.mp4`
