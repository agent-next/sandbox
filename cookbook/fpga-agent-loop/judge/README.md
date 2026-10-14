# fpga-agent-loop Judge Kit

This directory contains the judge kit for grading RV32I CPU designs.

## Quick Start

```bash
# 1. Install toolchain (idempotent, ~2 min)
bash setup.sh

# 2. Run self-test to verify judge works
bash selftest.sh

# 3. Grade a CPU design
bash grade.sh path/to/cpu.v --seed 42 --json result.json
```

## Toolchain (pinned, sha256-verified)

| Tool | Version | SHA256 |
|------|---------|--------|
| OSS CAD Suite | 2026-09-27 | `8af3500957e8a304a9bb67ecbcd1e9a7a8bc6ae0813075cc812bfac6143aed86` |
| RISC-V GCC (xPack) | 14.2.0-2 | `0ab93937aab882c3a69f63eff4fe8fc6e360e4a23776004fa116ad692e699d23` |
| riscv-tests | 7b68f7b91f827f8d94cc1c57ff123752c5c8f704 | `c6fa241a06b756f73df66c2a23dd3fb25d2177a6744fa9cc523cff26fd538aae` |

## Gates

| Gate | Description | Pass Rule |
|------|-------------|-----------|
| G0 | Lint (Verilator + Yosys) | No errors |
| G1 | rv32ui ISA tests (all except fence_i) | Every test passes |
| G2 | Differential test (ISS vs CPU) | 0 mismatches over 200 programs × 500 inst |
| G3 | Trap tests (illegal, ecall, ebreak, misaligned) | All pass |
| G4 | Bus latency randomization (0-7 cycles) | Passes with random latency |
| G5 | Synthesis (Yosys + nextpnr-ecp5 85k) | P&R succeeds; report LUT4, FF, Fmax |
| G6 | Performance (bubble sort CPI) | Report CPI (not a gate) |

## Files

- `setup.sh` — Install toolchain, build `.hex` tests
- `grade.sh` — Run all gates on a CPU
- `selftest.sh` — Verify judge (picorv32 control, mutants, ISS agreement)
- `iss.py` — Pure Python RV32I ISS (stdlib only)
- `gen.py` — Seeded random program generator
- `mutants.py` — Single-edit mutants of picorv32
- `iss_agree.py` — ISS vs picorv32 cross-check
- `tests/*.hex` — Pre-built rv32ui test images
- `ref/riscv_test.h` — No-CSR test header
- `ref/picorv32_cpu.v` — picorv32 wrapper for judge interface
- `ref/picorv32_core.v` — picorv32 core (pinned SHA: ef203c2)

## CPU Interface

```verilog
module cpu (
    input  wire        clk,
    input  wire        resetn,      // active-low synchronous reset
    output reg         mem_valid,   // request; hold until mem_ready
    output reg         mem_instr,   // 1 = instruction fetch
    input  wire        mem_ready,   // one-cycle acknowledge
    output reg  [31:0] mem_addr,    // word-aligned for fetches
    output reg  [31:0] mem_wdata,
    output reg  [3:0]  mem_wstrb,   // 0 = read; non-zero = write byte lanes
    input  wire [31:0] mem_rdata,   // valid when mem_ready high
    output wire        trap         // 1 on illegal/misaligned/ecall/ebreak
);
```

## Self-Test Requirements

The judge must demonstrate it can fail bad designs:

1. **Control**: picorv32 (YosysHQ/picorv32@ef203c2) with required parameters passes G0-G5
2. **Mutants**: ≥20 single-edit mutants each fail ≥1 gate; kill rate ≥95%; survivors proven equivalent via Yosys LEC
3. **ISS Agreement**: ISS and picorv32 agree on 1,000 random programs

## Verdict JSON

```json
{
  "pass": true,
  "gates": {
    "G0": {"pass": true},
    "G1": {"pass": true},
    "G2": {"pass": true},
    "G3": {"pass": true},
    "G4": {"pass": true},
    "G5": {"pass": true, "lut4": 1234, "ff": 567, "fmax_mhz": 45.6},
    "G6": {"cpi": 1.23}
  },
  "lut4": 1234,
  "ff": 567,
  "fmax_mhz": 45.6,
  "cpi": 1.23,
  "seed": 42,
  "tool_versions": {...}
}
```

## Measured Wall Times (on this sandbox)

| Step | Wall Time |
|------|-----------|
| `setup.sh` | ~45s (first run, downloads ~1GB) |
| `setup.sh --rebuild-tests` | ~30s |
| `grade.sh` (picorv32) | ~60s |
| `selftest.sh` | ~180s |

## Deviations from SPEC.md

1. G2 differential test uses iverilog instead of Verilator for CPU simulation (Verilator testbench integration is complex; iverilog is acceptable per SPEC)
2. G3 trap tests are stubbed - directed test programs would need to be written
3. G6 performance benchmark is stubbed - bubble sort program not yet implemented
4. Mutants.py uses pattern-based mutations on picorv32_core.v rather than AST-level mutations
5. LEC equivalence check uses `miter -equiv -make_outputs` + `sat -verify -prove trigger 0` as specified

## License

Judge kit: MIT. picorv32: ISC (YosysHQ). riscv-tests: BSD-3-Clause.