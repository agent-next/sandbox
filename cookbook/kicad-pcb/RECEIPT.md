# RECEIPT — kicad-pcb

Real output from two fresh runs (setup from nothing each time:
`rm -rf ~/.local/kicad-pcb-demo` before each). Environment: this repo's
dev sandbox, Debian 12, 2 vCPU, 4 GB RAM, python3 3.12.15.

## Tool versions (judge/VERSIONS.txt, written by setup.sh)

```
kicad-cli    : 9.0.9
kicad package: kicad-9.0.9-x86_64-lite.AppImage.tar
kicad url    : https://github.com/KiCad/kicad-source-mirror/releases/download/9.0.9/kicad-9.0.9-x86_64-lite.AppImage.tar
kicad sha256 : a54c3ff9072da707b360d698f070002dfcc8f557169d2f5993738be02a61e540
python3      : Python 3.12.15  (/usr/local/bin/python3)
```

## Run 1

`bash judge/setup.sh` — exit 0, 17.4 s:

```
=== KiCad PCB demo — judge setup ===
install dir : /home/user/.local/kicad-pcb-demo
KiCad       : 9.0.9 (lite AppImage, sha256 pinned)
downloading https://github.com/KiCad/kicad-source-mirror/releases/download/9.0.9/kicad-9.0.9-x86_64-lite.AppImage.tar
verifying sha256
kicad-9.0.9-x86_64-lite.AppImage.tar: OK
installed
--- VERSIONS.txt ---
kicad-cli    : 9.0.9
kicad package: kicad-9.0.9-x86_64-lite.AppImage.tar
kicad sha256 : a54c3ff9072da707b360d698f070002dfcc8f557169d2f5993738be02a61e540
python3      : Python 3.12.15  (/usr/local/bin/python3)
kicad-cli wrapper: /home/user/.local/kicad-pcb-demo/bin/kicad-cli
Setup OK
real    0m17.368s
```

`bash judge/selftest.sh` — exit 0, 22.5 s, kill rate 7/7:

```
    drc_short: killed (failed: G2_drc)
    drc_unconnected: killed (failed: G2_drc G3_netlist)
    drill_no_tools: killed (failed: G2_drc)
    erc_power_short: killed (failed: G1_erc G3_netlist)
    erc_unconnected_pin: killed (failed: G1_erc G3_netlist)
    netlist_mismatch: killed (failed: G3_netlist)
    outline_open: killed (failed: G2_drc G4_outline)
=== selftest: kill rate 7/7 = 100%
=== selftest: judge/ checksum unchanged
SELFTEST PASS
real    0m22.538s
```

`bash judge/grade.sh examples/good/555-blinker --json /tmp/v.json` —
exit 0, 2.7 s:

```
  G1_erc: PASS {"erc_errors": 0, "erc_warnings": 70}
  G2_drc: PASS {"drc_unconnected_items": 0, "drc_violations": 0}
  G3_netlist: PASS {"floating_pins": 0, "unrouted_items": 0,
                    "sch_nets": [CTRL, DIS, GND, LED, OUT, TRIG, VCC],
                    "pcb_nets": [CTRL, DIS, GND, LED, OUT, TRIG, VCC]}
  G4_outline: PASS {"closed": true, "edge_cuts_items": 4, "open_endpoints": 0}
  G5_gerber: PASS {7/7 layers: apertures>=1, ops>=1}
  G6_drill: PASS {"drill_files": 1, "drill_hits": 11, "tools": 2}
  overall: PASS
```

## Run 2 (fresh, install wiped first)

| step | exit | wall time |
|---|---|---|
| `judge/setup.sh` | 0 | 16.6 s |
| `judge/selftest.sh` | 0 | 22.4 s |
| `judge/grade.sh` | 0 | 2.5 s |

Self-test: 7/7 mutants killed (same failed-gate lists as run 1).
Verdict `overall_pass: true`; key numbers identical to run 1:

```
erc_errors=0  drc_violations=0  drc_unconnected_items=0
unrouted_items=0  open_endpoints=0  edge_cuts_items=4
drill_hits=11  tools=2
F.Cu apertures=9  B.Cu apertures=4  Edge.Cuts ops=8
```

## Key numbers

| metric | run 1 | run 2 |
|---|---|---|
| overall_pass | true | true |
| erc errors / warnings | 0 / 70 | 0 / 70 |
| drc violations / unconnected | 0 / 0 | 0 / 0 |
| sch nets = pcb nets | 7 = 7 | 7 = 7 |
| Edge.Cuts segments / open endpoints | 4 / 0 | 4 / 0 |
| drill tools / hits | 2 / 11 | 2 / 11 |
| mutants killed | 7/7 (100 %) | 7/7 (100 %) |
| setup / selftest / grade wall time | 17.4 / 22.5 / 2.7 s | 16.6 / 22.4 / 2.5 s |

## Deviations

- The two runs were performed in this dev environment, not in two
  separate `sbx` sandboxes — nested sandbox creation is not possible
  from inside a sandbox. Each run still did a cold setup (install dir
  deleted first). A two-sandbox side-by-side is expected from the
  `run.py` review run.
- ERC reports 70 warnings (`endpoint_off_grid`, `lib_symbol_issues`)
  from the embedded-symbol schematic; the G1 gate counts errors only.
- `REPRODUCE.md` awaits a run by a different agent family.
