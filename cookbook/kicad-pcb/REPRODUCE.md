VERDICT: REPRODUCED

# REPRODUCE — kicad-pcb

Independent reproduction of the `cookbook/kicad-pcb` demo, following
`README.md` (plus `SPEC.md` for the tolerances) in a fresh sandbox.
I am the reproducer: nothing in `judge/`, `examples/`, `media/` or the
tools was fixed, patched or improved. `RECEIPT.md` was read only after
all numbers below had been measured.

## Environment

```
E2B_SANDBOX=true   E2B_SANDBOX_ID=01a13b39-c62c-7a63-8cff-2f4dcd1175e2
2 vCPU, 3939 MB RAM, Debian 12 (bookworm), ffmpeg 5.1.9-0+deb12u1
python3 3.12.15 (/usr/local/bin/python3)
repo: /home/user/w  branch sbx/demo-kicad-pcb-repro  HEAD c68b33b
~/.local/kicad-pcb-demo did not exist before this run (cold setup)
```

`sbx` CLI: **not found**; `SBX_API_KEY`/`E2B_API_KEY`: **not set** (see
"README issues" #1). The `sbx` wrapper in `run.py` could not be
exercised, so I ran the README's agent steps (`setup.sh` → `selftest.sh`
→ `grade.sh`) directly in this sandbox, which is the path the RECEIPT
itself had to take (its "Deviations" note).

## Step 1 — `bash judge/setup.sh`

```
$ time bash judge/setup.sh
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
kicad url     : https://github.com/KiCad/kicad-source-mirror/releases/download/9.0.9/kicad-9.0.9-x86_64-lite.AppImage.tar
kicad sha256 : a54c3ff9072da707b360d698f070002dfcc8f557169d2f5993738be02a61e540
python3      : Python 3.12.15  (/usr/local/bin/python3)
kicad-cli wrapper: /home/user/.local/kicad-pcb-demo/bin/kicad-cli
KiCad share dir  : /home/user/.local/kicad-pcb-demo/appimage/usr/share/kicad
Setup OK
real	0m47.879s
user	0m6.313s
sys	0m21.541s
exit 0
```

Download itself took ~2 s (198.6 MiB at ~77 MB/s); the AppImage
extract + `cp -a` dominated. Tarball size from the release:
`content-length: 208263168` (= 208.3 MB, so README's "208 MB" is right).

## Step 2 — `bash judge/selftest.sh`

```
$ time bash judge/selftest.sh
=== selftest: grade known-good (run 1, seed 42)
... kicad-cli ERC 4s / DRC 4s / netlist 2s / gerbers 2s / drill 2s ...
  G1_erc: PASS {"erc_errors": 0, "erc_warnings": 19, "error_types": {},
    "warning_types": {"lib_symbol_issues": 19},
    "warning_types_not_allowed": {}, "warnings_allowlist": ["lib_symbol_issues"]}
  G2_drc: PASS {"drc_unconnected_items": 0, "drc_violations": 0, "violation_types": {}}
  G3_netlist: PASS {"floating_pins": 0, "only_in_pcb": [], "only_in_sch": [],
    "pcb_nets": ["CTRL","DIS","GND","LED","OUT","TRIG","VCC"],
    "sch_nets":  ["CTRL","DIS","GND","LED","OUT","TRIG","VCC"], "unrouted_items": 0}
  G4_outline: PASS {"closed": true, "edge_cuts_items": 4, "open_endpoints": 0}
  G5_gerber: PASS {"B.Cu": {"apertures": 4, "ops": 35}, "B.Mask": {"apertures": 2, "ops": 2},
    "B.Silkscreen": {"apertures": 1, "ops": 186}, "Edge.Cuts": {"apertures": 1, "ops": 8},
    "F.Cu": {"apertures": 9, "ops": 85}, "F.Mask": {"apertures": 7, "ops": 22},
    "F.Silkscreen": {"apertures": 2, "ops": 352},
    "extents_mm": {"board": [100.0,-130.0,140.0,-100.0], "gerber": [100.0,-130.0,140.0,-100.0],
                   "max_delta_mm": 0.0, "tol_mm": 0.1}}
  G6_drill: PASS {"drill_files": 1, "drill_hits": 11, "tools": 2}
  overall: PASS
=== selftest: grade known-good (run 2, determinism)
    determinism: identical verdict JSON (excluding timing)
=== selftest: mutants
erc_unconnected_pin / erc_power_short / erc_off_grid /
netlist_mismatch / drc_unconnected / drc_short /
outline_open / drill_no_tools
8 mutants written to /tmp/tmp.HcH0DxPuHt/mutants
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
real	2m3.567s
exit 0
```

Kill rate 8/8 = 100 % (SPEC requires >= 90 %), and the per-mutant
failed-gate lists are exactly RECEIPT run 1's lists.

## Step 3 — `bash judge/grade.sh examples/good/555-blinker --json /tmp/v.json`

```
$ time bash judge/grade.sh examples/good/555-blinker --json /tmp/v1.json
== kicad-cli: ERC
You have run CvPcb for the first time using the new footprint library table method for finding footprints.
CvPcb has either copied the default table or created an empty table in your home folder.
You must first configure the library table to include all footprint libraries not included with KiCad.
See the "Footprint Library Table" section of the CvPcb documentation for more information. Found 19 violations
Saved ERC Report to /tmp/tmp.8ZaQPuu47l/erc.json
    (2s) rc=0
== kicad-cli: DRC
Found 0 violations
Found 0 unconnected items
    (1s) rc=0
== kicad-cli: schematic netlist          (1s) rc=0
== kicad-cli: gerbers                     (1s) rc=0   (7 layers plotted)
== kicad-cli: drill                       (1s) rc=0
== oracle
  G1_erc: PASS {"erc_errors": 0, "erc_warnings": 19,
    "warning_types": {"lib_symbol_issues": 19}, "warning_types_not_allowed": {}}
  G2_drc: PASS {"drc_unconnected_items": 0, "drc_violations": 0}
  G3_netlist: PASS {"unrouted_items": 0, "floating_pins": 0,
    "pcb_nets": ["CTRL","DIS","GND","LED","OUT","TRIG","VCC"],
    "sch_nets":  ["CTRL","DIS","GND","LED","OUT","TRIG","VCC"]}
  G4_outline: PASS {"closed": true, "edge_cuts_items": 4, "open_endpoints": 0}
  G5_gerber: PASS {7/7 layers, apertures>=1 + ops>=1:
    F.Cu ap=9 ops=85, B.Cu ap=4 ops=35, F.Silkscreen ap=2 ops=352,
    B.Silkscreen ap=1 ops=186, F.Mask ap=7 ops=22, B.Mask ap=2 ops=2,
    Edge.Cuts ap=1 ops=8;
    "extents_mm": {"gerber": [100.0,-130.0,140.0,-100.0],
                   "board":  [100.0,-130.0,140.0,-100.0],
                   "max_delta_mm": 0.0, "tol_mm": 0.1}}
  G6_drill: PASS {"drill_files": 1, "drill_hits": 11, "tools": 2}
  overall: PASS
real	0m6.238s
exit 0
```

Verdict JSON: `"overall_pass": true`, `"seed": 0`,
`"timing": {"wall_seconds": 6.073}`. Board extents 100→140 mm /
-130→-100 mm = 40 x 30 mm (README constraint: <= 50 x 50 mm).

## Step 4 — determinism: `grade.sh` twice, same seed

```
$ bash judge/grade.sh examples/good/555-blinker --seed 42 --json /tmp/v2a.json; echo $?
0
$ time bash judge/grade.sh examples/good/555-blinker --seed 42 --json /tmp/v2b.json; echo $?
0
real	0m12.164s

identical (excl timing): True
timing A: {'wall_seconds': 10.689}
timing B: {'wall_seconds': 11.818}
seeds: 42 42      overall_pass: True

$ diff <(json.tool v2a.json) <(json.tool v2b.json)
129c129
<         "wall_seconds": 10.689
---
>         "wall_seconds": 11.818
```

**Identical except the `timing` key** (as `selftest.sh` requires and as
SPEC.md/RECEIPT claim). Seed 0 vs seed 42 verdicts are also identical
apart from the `seed` field, i.e. the seed stamps the JSON but changes
no gate number.

## Step 5 — media rebuild (`media/make_media.sh`)

`media/data/` was already present (committed), so I ran only
`media/make_media.sh` — the README's Layout lists it as the
regeneration script, and re-running `make_data.sh` would have replaced
the committed data files.

```
$ time bash media/make_media.sh
kicad-cli: /home/user/.local/kicad-pcb-demo/bin/kicad-cli (9.0.9)
ffmpeg version 5.1.9-0+deb12u1
[notice] A new release of pip is available: 25.0.1 -> 26.2.1
== rendering figures + frames
== kicad-cli renders
  + kicad-cli pcb render 555-blinker.kicad_pcb --side top --width 1600 --height 900 --quality high --background opaque -o good_3d.png
  + kicad-cli pcb export svg ... --layers F.Cu,B.Cu,F.Silkscreen,Edge.Cuts --page-size-mode 1 ...
  + (10 more 2-D SVG renders: good, drc_short, drc_unconnected, drill_no_tools,
     erc_off_grid, erc_power_short, erc_unconnected_pin, netlist_mismatch, outline_open)
== rasterise / == figures / == frames
rendered result.png, loop.png, 11 frames
== encoding demo.mp4 (11 frames)
demo.mp4: 1920x1080 30 fps 46.0 s 0.87 MB
== manifest
MANIFEST.json: 7 outputs, 51 data files
media done
real	8m29.127s
exit 0
```

Hash comparison of the rebuilt outputs against the committed
`media/MANIFEST.json`:

| file | committed sha256 | rebuilt sha256 | result |
|---|---|---|---|
| result.png | `ecfca18c803937c931f53e5ddaedd0af79cfaf37a65daacd8cb8c0862d0aed02` | `d4b3c78d28216a8fc4295fc9b3ac3a2ffb945a4b070464ba8ca1cb11b926dbf2` | **DIFFERS** |
| loop.png | `ad08b23dd94d55405ad6b32e1d2600bb2392eef6fd9f392da6ae01f446f32f99` | `ad08b23dd94d55405ad6b32e1d2600bb2392eef6fd9f392da6ae01f446f32f99` | **MATCH (byte-identical)** |
| demo.mp4 | `e0bceac4ae9099e5d150b2faa26bee0089b1751fb40f28b615c38516ec82d437` | `a718d5e7abd0a16548606d20f1a2a382e514dc91dc33218691ea7b6fc59d4c7a` | **DIFFERS** |
| make_data.sh | `87384983…` | `87384983…` | MATCH (input, untouched) |
| make_media.sh | `a56ad479…` | `a56ad479…` | MATCH (input, untouched) |
| render.py | `e334b9e5…` | `e334b9e5…` | MATCH (input, untouched) |
| REVIEW.md | `e8604321…` | `e8604321…` | MATCH (input, untouched) |

`media/MANIFEST.json` as rewritten by the rebuild differs from the
committed manifest in exactly the two sha256 lines above (verified with
`diff`); all 51 `source_data_sha256` entries are unchanged.

### Do the underlying data files match? — yes

* All 51 files under `media/data/` (9 verdict JSONs, 18 raw ERC/DRC
  reports, 24 mutant project files) still hash to the manifest's
  `source_data_sha256` values: `51 match, 0 differ`.
* The committed verdict data equals my own fresh judge output:
  `media/data/good.json` == my `/tmp/v1.json` with `seed`/`timing`
  removed → `True`.
* Pixel analysis of `result.png` (2400x1200): 9,027 differing pixels
  (0.313 %), bounding box x 268–931, y 380–889 — entirely inside the
  left-hand 3-D render. The right half (the verdict/numbers panel) has
  **0** differing pixels.
* `demo.mp4`: both files are 1920x1080, 30 fps, 1381 frames, 46.034 s.
  Comparing one frame per source segment, **10 of 11 source frames are
  pixel-identical**; only the intro frame `f00` differs (57,620 px,
  2.78 %) — and `f00` is the frame that embeds the 3-D render.
* Root cause of both differences: `kicad-cli pcb render` (the ray-traced
  3-D view) is **not bit-reproducible**. Three runs of the identical
  command gave three different hashes and different render times:

```
64adc0ac0377c4876e0b04eb6630c33d7b2dc1adaeb08b5f6c50217dac626431  /tmp/r1.png   (Rendering time 47.149 s)
99923948ceaf45bdae974b521fa67061eb320dbc342713a1c5f8ffe111b2420d  /tmp/r2.png   (Rendering time 30.121 s)
86cbcb8ec0d6d2c2eda1c0d491d31b238bb9793f9c7b266118827df5200c9f99  media/master/good_3d.png
```

  Everything that comes from the judge (all numbers, all verdicts, the
  whole `loop.png` kill matrix) reproduces bit-for-bit.

After comparing, `media/result.png`, `media/loop.png`, `media/demo.mp4`
and `media/MANIFEST.json` were restored from the backup and the
gitignored build trees `media/master/`, `media/.venv/` were removed;
`git status` is clean apart from this file.

## Comparison with RECEIPT.md

Per item: my value vs RECEIPT value, with the SPEC tolerance where the
SPEC states one.

| item | RECEIPT | this reproduction | verdict |
|---|---|---|---|
| tool version `kicad-cli` | 9.0.9 | 9.0.9 | **match** (pinned sha256 `a54c3ff9…61e540`, `sha256sum -c` OK) |
| `python3` | 3.12.15 `/usr/local/bin/python3` | 3.12.15 `/usr/local/bin/python3` | **match** |
| `overall_pass` | true | true | **match** |
| `erc_errors` | 0 | 0 | **match** (SPEC: must be 0) |
| `erc_warnings` | 19 (all `lib_symbol_issues`) | 19 (all `lib_symbol_issues`) | **match** (SPEC: exactly 19) |
| `drc_violations` | 0 | 0 | **match** |
| `drc_unconnected_items` | 0 | 0 | **match** |
| `unrouted_items` | 0 | 0 | **match** |
| `open_endpoints` / Edge.Cuts segments | 0 / 4 | 0 / 4 | **match** |
| sch nets = pcb nets | 7 = 7 (`CTRL,DIS,GND,LED,OUT,TRIG,VCC`) | 7 = 7 (same names) | **match** |
| gerber-vs-board `max_delta_mm` | 0.0 | 0.0 | **match** (SPEC: <= 0.1 mm) |
| `drill_files` / `tools` / `drill_hits` | 1 / 2 / 11 | 1 / 2 / 11 | **match** (SPEC: 11 / 2) |
| per-layer gerber apertures/ops | F.Cu 9/85, B.Cu 4/35, F.Silk 2/352, B.Silk 1/186, F.Mask 7/22, B.Mask 2/2, Edge.Cuts 1/8 | identical | **match** (SPEC allows +-20 % for a regenerated artifact) |
| mutants killed | 8/8 (100 %) | 8/8 (100 %) | **match** (SPEC: >= 90 %) |
| per-mutant failed gates | drc_short→G2; drc_unconnected→G2,G3; drill_no_tools→G2; erc_off_grid→G1; erc_power_short→G1,G3; erc_unconnected_pin→G1,G3; netlist_mismatch→G3; outline_open→G2,G4 | identical lists | **match** |
| `judge/` checksum unchanged by grading | yes | yes | **match** |
| verdict JSON, same seed twice | identical except `timing` | identical except `timing` | **match** |
| setup exit / wall time | 0 / 19.9 s (run 1), 15.7 s (run 2) | 0 / **47.879 s** | exit **match**; wall time **mismatch** (2.4–3.0x slower). No SPEC tolerance for timing; README's own table says "~18 s". |
| selftest exit / wall time | 0 / 25.2 s (run 1), 26.1 s (run 2) | 0 / **123.567 s** | exit **match**; wall time **mismatch** (~4.8x slower). No SPEC tolerance. |
| grade exit / wall time | 0 / 2.9 s (run 1), 2.8 s (run 2) | 0 / **6.073 s** (11.818 s on a repeat run) | exit **match**; wall time **mismatch** (2.1–4.2x slower). No SPEC tolerance. |
| `loop.png` sha256 | `ad08b23d…` | `ad08b23d…` | **match** |
| `result.png` sha256 | `ecfca18c…` | `d4b3c78d…` | **mismatch**, explained: only the non-deterministic `kicad-cli pcb render` 3-D image differs; verdict panel pixel-identical |
| `demo.mp4` sha256 | `e0bceac4…` | `a718d5e7…` | **mismatch**, explained: only the frame containing the 3-D render differs; 10/11 source frames identical; same container metadata |
| `media/data` sha256s (51) | as in MANIFEST | all 51 match | **match** |
| verdict-seed used | 42 (selftest / make_data) | 42 for the determinism runs; the README's literal grade command produced seed 0 | **match** once the seed is passed; see README issue #4 |

The only substantive deviations are wall-clock times (same nominal
2 vCPU / 4 GB sandbox, but ~2.5–4.8x slower on every KiCad step — e.g.
the ERC step alone took 2–4 s here vs a 2.9 s total grade in the
RECEIPT) and the two media artifacts whose pixels come from a
non-deterministic ray-traced render. Every SPEC.md "Reproduction
tolerance" number — `overall_pass`, `erc_errors: 0`, `erc_warnings:
19`, `drc_violations: 0`, `drc_unconnected_items: 0`,
`unrouted_items: 0`, `open_endpoints: 0`, `max_delta_mm: 0.0`,
`drill_hits: 11`, `tools: 2`, 8/8 mutants killed — reproduces exactly.

## README issues found while reproducing

1. **`python3 run.py` cannot run here.** Exact output:

   ```
   $ python3 cookbook/kicad-pcb/run.py
   sbx CLI not found; see README
   run.py EXIT=1
   ```

   The dependency (`sbx` CLI + `SBX_API_KEY`/`E2B_API_KEY`) is only
   disclosed in the last "Limits" bullet, after the "One-command run"
   section presents `run.py` as the primary path. Additionally, the
   default `--ref main` does not exist in this repo:

   ```
   $ git branch -a
     sbx/demo-kicad-pcb-mediac
   * sbx/demo-kicad-pcb-repro
     remotes/origin/sbx/demo-kicad-pcb-mediac
   ```

   so `git clone -b main` inside the sandbox would fail even with the
   CLI and key present.

2. **Wall-time table reads like a spec, but is environment-specific.**
   README's "Measured wall time (this sandbox, 2 vCPU / 4 GB)" gives
   setup ~18 s, selftest ~26 s, grade ~3 s. On an equally-sized sandbox
   I measured 47.879 s / 123.567 s / 6.073–11.818 s. Nothing in
   README/SPEC says these are indicative only, nor that the numbers came
   from the builder's dev sandbox (RECEIPT.md does say so, but a
   reproducer is told to read README.md alone).

3. **`--seed` is undocumented.** The README's grade command is
   `grade.sh examples/good/555-blinker --json /tmp/v.json`, which
   yields `"seed": 0` (grade.sh's default). The RECEIPT's determinism
   claim and `selftest.sh` both use `--seed 42` (also `media/make_data.sh`).
   The flag is only discoverable by reading `judge/grade.sh`. I used
   seed 42 for the determinism runs (the seed the RECEIPT used); the
   gate numbers are seed-independent.

4. **Media prerequisites are not in the README.** `make_media.sh` needs
   `ffmpeg`/`ffprobe`, a hash-pinned venv (`matplotlib`, `numpy`,
   `pymupdf`, `pillow`, …) and PyPI access, plus the pinned `kicad-cli`
   and a populated `media/data/`. None of this is in README.md; it only
   appears in the script's comment header. A reproducer following the
   README cannot know that `media/data/` must exist (produced by
   `make_data.sh`) before `make_media.sh` will run.

5. **`media/data/*.erc.json` / `*.drc.json` embed a `date` field**, so
   `make_data.sh` can never reproduce the manifest's
   `source_data_sha256` for those 18 files byte-for-byte:

   ```
   fresh run   : date 2026-10-14T16:58:12+0000  sha 0bfb6333…
   committed   : date 2026-10-14T13:54:25+0000  sha aa0103c8…
   ```

   The 9 verdict JSONs and the 24 mutant project files are
   reproducible; the raw reports are not. README does not mention that
   `make_data.sh` output is timestamped.

6. **`judge/setup.sh` rewrites the tracked `judge/VERSIONS.txt`** (it
   writes both `$DEMO_HOME/VERSIONS.txt` and `$SCRIPT_DIR/VERSIONS.txt`).
   In my run the content was byte-identical, so `git status` stayed
   clean, but on a host with a different `python3` path the file would
   dirty the repo — and the README's agent prompt says to clone the repo
   and run `setup.sh`, with no warning. (`selftest.sh`'s judge checksum
   only covers `*.sh`/`*.py`, so it is unaffected.)

7. **Cosmetic:** README says the setup download is "208 MB" while
   curl's progress meter prints `198M` (MiB). Actual size
   208,263,168 bytes confirms README.

Nothing else was unclear or wrong: every step in the README's agent
prompt ran to completion, no step errored, and the two "hidden"
prerequisites I hit (the `sbx` CLI and the media venv/ffmpeg) are the
only ones a fresh-sandbox reproducer must discover outside README.md.

## Reproduction steps (verbatim)

```bash
cd cookbook/kicad-pcb
time bash judge/setup.sh
bash judge/grade.sh examples/good/555-blinker --json /tmp/v1.json
bash judge/grade.sh examples/good/555-blinker --seed 42 --json /tmp/v2a.json
bash judge/grade.sh examples/good/555-blinker --seed 42 --json /tmp/v2b.json
time bash judge/selftest.sh
time bash media/make_media.sh      # media/ outputs restored afterwards
```
