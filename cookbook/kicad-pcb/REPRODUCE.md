VERDICT: REPRODUCED

# REPRODUCE — kicad-pcb

Independent reproduction: a different agent following only `README.md`
in a fresh sandbox (KiCad not pre-installed; `sbx` CLI absent, so the
`run.py` path was skipped and the `judge/` scripts were run directly —
README's "Ask your agent" block documents the same three commands).
Environment: Debian 12, python3 3.12.15 (`/usr/local/bin/python3`),
ffmpeg 5.1.9, kicad-cli 9.0.9 installed by `judge/setup.sh`.

## Steps run (real output)

`bash judge/setup.sh` — exit 0, real 0m33.8s (user 0m5.6s, sys 0m22.4s):

```
=== KiCad PCB demo — judge setup ===
downloading https://github.com/KiCad/kicad-source-mirror/releases/download/9.0.9/kicad-9.0.9-x86_64-lite.AppImage.tar
verifying sha256
kicad-9.0.9-x86_64-lite.AppImage.tar: OK
installed
--- VERSIONS.txt ---
kicad-cli    : 9.0.9
kicad package: kicad-9.0.9-x86_64-lite.AppImage.tar
kicad sha256 : a54c3ff9072da707b360d698f070002dfcc8f557169d2f5993738be02a61e540
python3      : Python 3.12.15  (/usr/local/bin/python3)
Setup OK
real    0m33.837s
```

`bash judge/selftest.sh` — exit 0, real 0m45.5s, kill rate 8/8 = 100%
(default `SEED=42`, the same seed the RECEIPT used):

```
    determinism: identical verdict JSON (excluding timing)
    drc_short: killed (failed: G2_drc)
    drc_unconnected: killed (failed: G2_drc G3_netlist)
    drill_no_tools: killed (failed: G2_drc G6_drill)
    erc_off_grid: killed (failed: G1_erc)
    erc_power_short: killed (failed: G1_erc G3_netlist)
    erc_unconnected_pin: killed (failed: G1_erc G3_netlist)
    netlist_mismatch: killed (failed: G3_netlist)
    outline_open: killed (failed: G2_drc G4_outline)
=== selftest: kill rate 8/8 = 100%
=== selftest: judge/ checksum unchanged
SELFTEST PASS
real    0m45.469s
```

`bash judge/grade.sh examples/good/555-blinker --json /tmp/v.json` —
exit 0, real 0m6.2s:

```
  G1_erc: PASS {"erc_errors": 0, "erc_warnings": 19,
    "warning_types": {"lib_symbol_issues": 19},
    "warning_types_not_allowed": {}}
  G2_drc: PASS {"drc_unconnected_items": 0, "drc_violations": 0}
  G3_netlist: PASS {"unrouted_items": 0, "floating_pins": 0,
    "sch_nets": [CTRL, DIS, GND, LED, OUT, TRIG, VCC],
    "pcb_nets": [CTRL, DIS, GND, LED, OUT, TRIG, VCC]}
  G4_outline: PASS {"closed": true, "edge_cuts_items": 4, "open_endpoints": 0}
  G5_gerber: PASS {F.Cu ap=9 ops=85, B.Cu ap=4 ops=35,
    F.Silkscreen ap=2 ops=352, B.Silkscreen ap=1 ops=186,
    F.Mask ap=7 ops=22, B.Mask ap=2 ops=2, Edge.Cuts ap=1 ops=8;
    "extents_mm": {"gerber": [100.0, -130.0, 140.0, -100.0],
                   "board":  [100.0, -130.0, 140.0, -100.0],
                   "max_delta_mm": 0.0, "tol_mm": 0.1}}
  G6_drill: PASS {"drill_files": 1, "drill_hits": 11,
    "expected_holes": 11, "missing_tool_mm": [],
    "no_drill_pads": 0, "no_drill_vias": 0, "tools": 2}
  overall: PASS
GRADE_EXIT=0
```

Determinism check (criterion 3): `grade.sh examples/good/555-blinker
--seed 42 --json` run twice; verdict JSONs with the `timing` key removed
compare **identical** (both `seed: 42`; exits 0/0).

## Comparison with RECEIPT.md (SPEC tolerances)

| item | RECEIPT (run 1 / run 2) | this run | tolerance (SPEC.md) | match? |
|---|---|---|---|---|
| `overall_pass` | true / true | true | true | MATCH |
| erc_errors / erc_warnings | 0 / 19 | 0 / 19 | 0 / 19 | MATCH |
| warning types | all `lib_symbol_issues` | all `lib_symbol_issues` | allow-list only | MATCH |
| drc_violations / unconnected | 0 / 0 | 0 / 0 | 0 / 0 | MATCH |
| sch nets = pcb nets | 7 = 7 | 7 = 7 | exact set equality | MATCH |
| unrouted_items / floating_pins | 0 / 0 | 0 / 0 | 0 / 0 | MATCH |
| edge_cuts_items / open_endpoints | 4 / 0 | 4 / 0 | closed, 0 open | MATCH |
| gerber extents max_delta_mm | 0.0 | 0.0 | <= 0.1 | MATCH |
| drill tools / hits / expected | 2 / 11 / 11 | 2 / 11 / 11 | cover all holes | MATCH |
| gerber apertures/ops per layer | F.Cu 9/85, B.Cu 4/35, F.Silk 2/352, B.Silk 1/186, F.Mask 7/22, B.Mask 2/2, Edge.Cuts 1/8 | identical | +-20% if regenerated | MATCH |
| mutants killed | 8/8 (100%) | 8/8 (100%), same failed-gate lists | >= 90% | MATCH |
| verdict JSON, same seed x2 | identical except `timing` | identical except `timing` | identical | MATCH |
| kicad-cli version | 9.0.9 | 9.0.9 | pinned 9.0.9 | MATCH |
| AppImage sha256 | a54c3ff9...61e540 | a54c3ff9...61e540 (`sha256sum -c` OK) | pinned | MATCH |
| python3 | 3.12.15 (/usr/local/bin/python3) | 3.12.15 (/usr/local/bin/python3) | >= 3.10 | MATCH |
| setup wall time | 19.9s / 15.7s | 33.8s | none (README ~18s) | slower |
| selftest wall time | 25.2s / 26.1s | 45.5s | none (README ~26s) | slower |
| grade wall time | 2.9s / 2.8s | 6.2s | none (README ~3s) | slower |

Every verdict, kill rate, key metric and tool version matches the
RECEIPT and is inside the SPEC tolerance. Wall times are ~1.7-2.1x
slower than the RECEIPT's — no tolerance is specified; attributed to a
slower sandbox (mostly I/O: setup `sys` time was 22 s extracting the
200 MB AppImage).

## Media rebuild (`media/make_media.sh`)

`bash media/make_media.sh` — exit 0, real 3m32.9s. Created `media/.venv`
(gitignored) via `pip install --require-hashes -r judge/requirements.txt`,
rendered with kicad-cli 9.0.9 + ffmpeg 5.1.9, verified
`demo.mp4: 1920x1080 30 fps 46.0 s 0.91 MB`, rewrote `MANIFEST.json`
(7 outputs, 51 data files). Rebuilt files were compared to the committed
MANIFEST sha256s, then the tree was restored (`git checkout`).

| file | committed sha256 | rebuilt sha256 | match? |
|---|---|---|---|
| loop.png | 0c1cda6e...d2a170 | 0c1cda6e...d2a170 | IDENTICAL |
| result.png | 3ac307f7...64f0ca | 48c8d014...59cda | DIFFERS |
| demo.mp4 | 31af2cdc...879240 | f5bb1670...309d3ea | DIFFERS |
| media/data/* (51 files) | per `source_data_sha256` | regenerated MANIFEST `source_data_sha256` section unchanged | IDENTICAL |

- `result.png` differs only on the left half (the `kicad-cli pcb render`
  3D image): 8,790 of 2,880,000 pixels (0.3%), max RGB-sum delta 6 —
  raytracer noise. The right half (verdict panel drawn from
  `data/good.json`) is pixel-identical.
- `demo.mp4` differs: it embeds a re-rendered 3D frame (same noise) and
  is a fresh x264 encode. Stream checks pass (1920x1080, 30 fps, 46.0 s,
  0.91 MB).
- All underlying data files (verdicts, raw ERC/DRC JSONs, mutant
  projects) hash-identical — the rebuilt manifest's
  `source_data_sha256` section is unchanged.

## README steps that were unclear, wrong or missing

1. **Wall-time table is optimistic.** README lists ~18 s / ~26 s / ~3 s
   "this sandbox, 2 vCPU / 4 GB"; observed 33.8 s / 45.5 s / 6.2 s on
   comparable specs. Environment-dependent, but readers may treat them
   as bounds. No error output — just slow.
2. **Media rebuild not documented.** `media/make_media.sh` is only named
   in the layout list; its prerequisites (ffmpeg/ffprobe on PATH,
   network for the hash-pinned venv, `media/data/` from
   `media/make_data.sh`) are described only in the script header, not
   the README. It worked first try here because ffmpeg was installed.
3. **`run.py` untestable as documented.** It needs the `sbx` CLI and
   `SBX_API_KEY`/`E2B_API_KEY`; `sbx` is absent in this sandbox
   (`command -v sbx` → not found). README's Limits section discloses
   this, and the "Ask your agent" commands do not need it — noted, not a
   failure.
4. **Minor wording.** "Ask your agent > clone this repo" assumes the
   agent starts outside the repo; the reproducer already has it
   checked out. Cosmetic.
5. No step produced an error or wrong output; nothing was missing for
   the setup → selftest → grade path.

## Reproduction results summary

| metric | builder (RECEIPT) | reproducer |
|---|---|---|
| setup exit / time | 0 / ~17 s | 0 / 33.8 s |
| selftest exit / kill rate | 0 / 100 % | 0 / 100 % (8/8) |
| grade exit / overall_pass | 0 / true | 0 / true |
| erc_errors | 0 | 0 |
| erc_warnings | 19 (`lib_symbol_issues`) | 19 (`lib_symbol_issues`) |
| drc_violations / unconnected | 0 / 0 | 0 / 0 |
| unrouted_items | 0 | 0 |
| extents max_delta_mm | 0.0 | 0.0 |
| drill_hits / tools | 11 / 2 | 11 / 2 |
| same-seed determinism | identical excl. timing | identical excl. timing |
