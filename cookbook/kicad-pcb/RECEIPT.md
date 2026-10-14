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

`bash judge/setup.sh` — exit 0, 19.9 s (cold download, sha256 verified):

```
=== KiCad PCB demo — judge setup ===
downloading https://github.com/KiCad/kicad-source-mirror/releases/download/9.0.9/kicad-9.0.9-x86_64-lite.AppImage.tar
verifying sha256
kicad-9.0.9-x86_64-lite.AppImage.tar: OK
installed
Setup OK
real    0m19.937s
```

`bash judge/selftest.sh` — exit 0, 25.2 s, kill rate 8/8:

```
    determinism: identical verdict JSON (excluding timing)
    drc_short: killed (failed: G2_drc)
    drc_unconnected: killed (failed: G2_drc G3_netlist)
    drill_no_tools: killed (failed: G2_drc)
    erc_off_grid: killed (failed: G1_erc)
    erc_power_short: killed (failed: G1_erc G3_netlist)
    erc_unconnected_pin: killed (failed: G1_erc G3_netlist)
    netlist_mismatch: killed (failed: G3_netlist)
    outline_open: killed (failed: G2_drc G4_outline)
=== selftest: kill rate 8/8 = 100%
=== selftest: judge/ checksum unchanged
SELFTEST PASS
real    0m25.159s
```

`bash judge/grade.sh examples/good/555-blinker --json /tmp/v.json` —
exit 0, 2.9 s:

```
  G1_erc: PASS {"erc_errors": 0, "erc_warnings": 19,
    "warning_types": {"lib_symbol_issues": 19},
    "warning_types_not_allowed": {},
    "warnings_allowlist": ["lib_symbol_issues"]}
  G2_drc: PASS {"drc_unconnected_items": 0, "drc_violations": 0}
  G3_netlist: PASS {"unrouted_items": 0, "floating_pins": 0,
    "sch_nets": [CTRL, DIS, GND, LED, OUT, TRIG, VCC],
    "pcb_nets": [CTRL, DIS, GND, LED, OUT, TRIG, VCC]}
  G4_outline: PASS {"closed": true, "edge_cuts_items": 4, "open_endpoints": 0}
  G5_gerber: PASS {7/7 layers with apertures>=1 + ops>=1:
    F.Cu ap=9 ops=85, B.Cu ap=4 ops=35, F.Silkscreen ap=2 ops=352,
    B.Silkscreen ap=1 ops=186, F.Mask ap=7 ops=22, B.Mask ap=2 ops=2,
    Edge.Cuts ap=1 ops=8;
    "extents_mm": {"gerber": [100.0, -130.0, 140.0, -100.0],
                   "board":  [100.0, -130.0, 140.0, -100.0],
                   "max_delta_mm": 0.0, "tol_mm": 0.1}}
  G6_drill: PASS {"drill_files": 1, "drill_hits": 11, "tools": 2}
  overall: PASS
```

## Run 2 (fresh, install wiped first)

| step | exit | wall time |
|---|---|---|
| `judge/setup.sh` | 0 | 15.7 s |
| `judge/selftest.sh` | 0 | 26.1 s |
| `judge/grade.sh` | 0 | 2.8 s |

Self-test: 8/8 mutants killed (same failed-gate lists as run 1).
Verdict `overall_pass: true`; key numbers identical to run 1.

## Key numbers

| metric | run 1 | run 2 |
|---|---|---|
| overall_pass | true | true |
| erc errors / warnings | 0 / 19 (all `lib_symbol_issues`) | 0 / 19 |
| drc violations / unconnected | 0 / 0 | 0 / 0 |
| sch nets = pcb nets | 7 = 7 | 7 = 7 |
| Edge.Cuts segments / open endpoints | 4 / 0 | 4 / 0 |
| gerber-vs-board extents max_delta_mm | 0.0 (tol 0.1) | 0.0 |
| drill tools / hits | 2 / 11 | 2 / 11 |
| mutants killed | 8/8 (100 %) | 8/8 (100 %) |
| verdict JSON (same seed, two grades) | identical except `timing` | identical except `timing` |
| setup / selftest / grade wall time | 19.9 / 25.2 / 2.9 s | 15.7 / 26.1 / 2.8 s |

## Lead review run (host, `run.py --ref sbx/demo-kicad-pcb-2`)

Recorded from the lead's review of the previous revision
(pre-hardening, branch `sbx/demo-kicad-pcb-2`): `run.py` exit 0;
setup 24 s, selftest 23 s, grade 3 s; 6/6 gates passed; kill rate
7/7; determinism check identical; sandbox killed and verified absent
from `sbx list`.

## Hardening verification

1. **Pinned tooling.** `judge/setup.sh` installs only the KiCad 9.0.9
   lite AppImage tarball, sha256-checked
   (`a54c3ff9…61e540`, `sha256sum -c` output above). `judge/VERSIONS.txt`
   (committed) records the installed `kicad-cli --version`.
   `judge/requirements.txt` hash-pins the media-only pip deps
   (matplotlib 3.11.2 + transitive wheels); the judge is stdlib-only.
2. **Determinism.** `selftest.sh` grades the good example twice with
   `--seed 42` and compares verdict JSON with the `timing` key removed.
   Verified again here: `r1_verdict.json` vs `r2_verdict.json` differ
   only in `timing.wall_seconds` (2.812 vs 2.684).
3. **Fresh-setup runs.** Both runs above did `rm -rf
   ~/.local/kicad-pcb-demo` first; side-by-side numbers in the table.
4. **Judge strength.** 8/8 scripted mutants killed (100 %). Every gate
   is evaluated by `judge/oracle.py` parsing the exported artifacts —
   not by kicad-cli exit codes. G5 additionally cross-checks gerber
   Edge.Cuts extents against the board within 0.1 mm.
5. **Lead findings.** ERC warnings enumerated by type
   (`kicad-cli sch erc --format json`): previously 70 =
   51 `endpoint_off_grid` + 19 `lib_symbol_issues`. The generator
   placed pins/wires on arbitrary mm positions; `tools/gen_sch.py` now
   emits all coordinates on the 50-mil (1.27 mm) grid → the 51
   off-grid warnings are gone. The 19 `lib_symbol_issues` are inherent
   (self-contained embedded symbols, headless library-less ERC) and are
   the single entry in the SPEC.md allow-list; G1 fails on any other
   warning type, exercised by the new `erc_off_grid` mutant.
   G5 now reports per-layer aperture/op counts and the measured
   extents delta (0.0 mm).
6. **SPEC.md allow-list claim verified.** The claim that "KiCad's own
   shipped demos produce the same warning under kicad-cli" was checked
   against the `video` demo shipped inside the pinned 9.0.9 AppImage
   (`appimage/share/kicad/demos/video/video.kicad_sch`), run headless
   with the same command the judge uses:

   ```
   $ kicad-cli sch erc video.kicad_sch --format json --severity-all \
         -o /tmp/erc_video.json
   Found 21 violations
   Saved ERC Report to /tmp/erc_video.json
   ```

   Violation tally: 18 `lib_symbol_issues` + 3 `footprint_link_issues`
   warnings, 0 errors. First `lib_symbol_issues` item: `"The current
   configuration does not include the symbol library 'power'"` — the
   same warning class the self-contained artifact produces.

## Deviations

- The two runs were performed in this dev environment, not in two
  separate `sbx` sandboxes — nested sandbox creation is not possible
  from inside a sandbox. Each run still did a cold setup (install dir
  deleted first). The lead's host `run.py` run above covers the
  end-to-end sandboxed path (previous revision).
- `media/` (figures, `media/data/*.json`) predates this hardening
  round and still reflects the pre-fix warning counts; media
  regeneration is a later round.
- `REPRODUCE.md` awaits a run by a different agent family.
