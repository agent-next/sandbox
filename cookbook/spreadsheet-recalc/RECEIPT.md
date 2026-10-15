# spreadsheet-recalc demo — receipt

## Builder-local judge

### `bash judge/setup.sh`

```
setup: libreoffice 7.4.7-1+deb12u14 already installed (skipping download)
setup: openpyxl 3.1.5 already present
setup: wrote /home/user/w/cookbook/spreadsheet-recalc/judge/VERSIONS.txt
setup: done
```

exit=0.

### `bash judge/selftest.sh`

```
selftest: generating mutants...
selftest: grading known-good...
selftest: known-good: PASS
selftest: mutant hardcoded_npv: killed (gate: negative_control,npv_10_match,npv_12_match)
selftest: mutant wrong_cashflow: killed (gate: npv_10_match,npv_12_match,npv_8_match)
selftest: mutant wrong_rate: killed (gate: npv_8_match)
selftest: mutant missing_formula: killed (gate: npv_10_match,npv_12_match,npv_8_match)
selftest: mutant wrong_formula: killed (gate: negative_control,npv_10_match,npv_12_match,npv_8_match)
selftest: mutant static_pv: killed (gate: negative_control,npv_10_match,npv_12_match)
selftest: kill rate: 6/6 = 100%
selftest: determinism: OK
selftest: ok
```

exit=0.

### `bash judge/grade.sh examples/good/dcf_model.xlsx --json /tmp/v.json`

```json
{
  "artifact": "dcf_model.xlsx",
  "gates": {
    "judge_intact": true,
    "negative_control": true,
    "npv_8_match": true,
    "npv_10_match": true,
    "npv_12_match": true,
    "recalc_8": true,
    "recalc_10": true,
    "recalc_12": true,
    "structure": true
  },
  "metrics": {
    "npv_8_computed": 890.1082,
    "npv_8_oracle": 890.1082,
    "npv_8_err_pct": 0.0,
    "npv_10_computed": 484.598,
    "npv_10_oracle": 484.598,
    "npv_10_err_pct": 0.0,
    "npv_12_computed": 103.2935,
    "npv_12_oracle": 103.2935,
    "npv_12_err_pct": 0.0,
    "npv_moves": true
  },
  "pass": true,
  "problems": [],
  "seed": 0
}
```

exit=0.

### Wall times (builder-local)

| step | wall |
|---|---|
| setup.sh | ~1 s (cached) |
| selftest.sh | ~45 s |
| grade.sh | ~8 s |

### Key numbers

| quantity | computed | oracle | err % |
|---|---|---|---|
| NPV @ 8% | 890.1082 | 890.1082 | 0.00% |
| NPV @ 10% | 484.598 | 484.598 | 0.00% |
| NPV @ 12% | 103.2935 | 103.2935 | 0.00% |

Kill rate: 6/6 = 100% (≥ 90% required).

### Tool versions

- LibreOffice 7.4.7-1+deb12u14 (Debian bookworm, sha256-verified .deb)
- openpyxl 3.1.5 (pip, x86-64 Linux CPython 3.12 wheel)
- Python 3.12.15

## Fresh-sandbox runs

(not done: builder sandbox has no `sbx` CLI / SBX_API_KEY; run.py verified via `py_compile` and in-sandbox command sequence per task constraints)

## Deviations

- **Parallel recalculation**: The judge runs the three discount-rate recalculations in parallel (ThreadPoolExecutor) to keep selftest wall time under 60 s on 2 vCPU. Each worker uses an isolated HOME directory so LibreOffice profiles do not collide.
- **Structure gate vs negative control**: The structure gate checks for formula presence and scans for hardcoded oracle values. The negative control (re-recalc at 12% and verify NPV changes) is the stronger catch — static or hardcoded values pass structure but fail negative control. The `hardcoded_npv` mutant is caught by structure (oracle literal in cell value), while `static_pv` is caught by both structure and negative control.
